package portfolio.analytics;

import java.io.IOException;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
class QueryEvents {
    private final QueryService service;
    private final ThreadPoolExecutor streams = new ThreadPoolExecutor(
        0, 12, 30, TimeUnit.SECONDS, new SynchronousQueue<>()
    );

    QueryEvents(QueryService service) {
        this.service = service;
    }

    @GetMapping(value = "/api/runs/{id}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> stream(@PathVariable String id,
        @RequestHeader(value = "Last-Event-ID", required = false) Integer lastEvent,
        @RequestParam(defaultValue = "0") int after) {
        var row = service.require(id);
        int cursor = lastEvent == null ? after : lastEvent;
        if (cursor < 0 || cursor > 3 || (cursor == 3 && !QueryService.TERMINAL.contains(row.status()))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "事件游标不合法");
        }
        if (cursor == 3) {
            return ResponseEntity.noContent().build();
        }
        var emitter = new SseEmitter(65_000L);
        try {
            streams.execute(() -> replay(emitter, id, cursor));
        } catch (RejectedExecutionException exception) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "订阅数已满，请稍后重连");
        }
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .header("Cache-Control", "no-cache")
            .header("X-Accel-Buffering", "no")
            .body(emitter);
    }

    private void replay(SseEmitter emitter, String id, int cursor) {
        long timeout = System.nanoTime() + TimeUnit.SECONDS.toNanos(55);
        long nextHeartbeat = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        try {
            if (cursor < 1) {
                send(emitter, 1, new QueryService.RunView(id, "QUEUED", null, null));
                cursor = 1;
            }
            while (System.nanoTime() < timeout) {
                var row = service.require(id);
                if (cursor < 2 && row.started()) {
                    send(emitter, 2, new QueryService.RunView(id, "RUNNING", null, null));
                    cursor = 2;
                }
                if (QueryService.TERMINAL.contains(row.status())) {
                    send(emitter, 3, service.view(row));
                    break;
                }
                if (System.nanoTime() >= nextHeartbeat) {
                    emitter.send(SseEmitter.event().comment("heartbeat"));
                    nextHeartbeat = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
                }
                Thread.sleep(200);
            }
            emitter.complete();
        } catch (IOException | IllegalStateException exception) {
            // 浏览器刷新后通常由此结束旧订阅，新订阅独立读取任务状态。
            emitter.completeWithError(exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            emitter.complete();
        } catch (RuntimeException exception) {
            emitter.completeWithError(exception);
        }
    }

    private void send(SseEmitter emitter, int sequence, QueryService.RunView view) throws IOException {
        emitter.send(SseEmitter.event().id(Integer.toString(sequence)).name("run")
            .data(view, MediaType.APPLICATION_JSON));
    }

    @PreDestroy
    void stop() {
        streams.shutdownNow();
    }
}
