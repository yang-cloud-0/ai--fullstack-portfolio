package portfolio.analytics;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class QueryService {
    static final Set<String> TERMINAL = Set.of("SUCCEEDED", "CLARIFY", "FAILED");
    private static final Logger LOG = LoggerFactory.getLogger(QueryService.class);

    record RunView(String id, String status, String message, JsonNode result) {}

    private final RunMapper runs;
    private final AgentClient agent;
    private final MetricService metrics;
    private final ExecutorService queryExecutor;
    private final ObjectMapper json;

    QueryService(RunMapper runs, AgentClient agent, MetricService metrics,
                 ExecutorService queryExecutor, ObjectMapper json) {
        this.runs = runs;
        this.agent = agent;
        this.metrics = metrics;
        this.queryExecutor = queryExecutor;
        this.json = json;
    }

    @EventListener(ApplicationReadyEvent.class)
    void recoverInterrupted() {
        // 演示环境只运行一个后端进程，重启后明确标记被中断的任务。
        runs.recoverInterrupted();
    }

    RunView create(String key, String question) {
        String normalizedQuestion = question.strip();
        String id = UUID.randomUUID().toString();
        try {
            runs.insert(id, key, normalizedQuestion);
        } catch (DuplicateKeyException exception) {
            var existing = runs.findByKey(key);
            if (existing == null) {
                throw exception;
            }
            if (!existing.question().equals(normalizedQuestion)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "该幂等键已用于另一个问题");
            }
            return view(existing);
        }
        try {
            queryExecutor.execute(() -> execute(id, normalizedQuestion));
        } catch (RejectedExecutionException exception) {
            runs.finish(id, "FAILED", null, "当前查询较多，请稍后重新发起");
        }
        return view(require(id));
    }

    RunMapper.Row require(String id) {
        var row = runs.find(id);
        if (row == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "查询任务不存在");
        }
        return row;
    }

    RunView view(RunMapper.Row row) {
        try {
            JsonNode result = row.resultJson() == null ? null : json.readTree(row.resultJson());
            return new RunView(row.id(), row.status(), row.message(), result);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("已保存的查询结果无法解析", exception);
        }
    }

    private void execute(String id, String question) {
        long start = System.nanoTime();
        if (runs.start(id) == 0) {
            return;
        }
        try {
            var plan = agent.analyze(question, id);
            if (plan == null) {
                throw new IllegalStateException("查询计划为空");
            }
            switch (plan.status()) {
                case "ready" -> runs.finish(id, "SUCCEEDED",
                    json.writeValueAsString(metrics.query(plan)), null);
                case "clarify" -> runs.finish(id, "CLARIFY", null, plan.reason());
                default -> runs.finish(id, "FAILED", null, "分析暂不可用，请稍后重新发起");
            }
        } catch (RuntimeException | JsonProcessingException exception) {
            LOG.warn("查询失败 traceId={} 类型={}", id, exception.getClass().getSimpleName());
            runs.finish(id, "FAILED", null, "无法完成分析，请稍后重新发起或向数据同事确认");
        } finally {
            LOG.info("查询处理结束 traceId={} durationMs={}", id, (System.nanoTime() - start) / 1_000_000);
        }
    }
}
