package portfolio.analytics;

import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class QueryServiceTest {
    @Autowired QueryService service;
    @Autowired MetricService metrics;
    @MockitoBean AgentClient agent;

    @Test
    void separatesPaidAndTotalOrdersAndUsesNetRatherThanGrossRevenue() {
        assertThat(metrics.query(plan("order_count")).value()).isEqualByComparingTo("5");
        assertThat(metrics.query(plan("paid_orders")).value()).isEqualByComparingTo("3");
        assertThat(metrics.query(plan("net_revenue")).value()).isEqualByComparingTo("449");
    }

    @Test
    void invalidPlanNeverReachesQuery() {
        assertThatThrownBy(() -> metrics.query(plan("unrecognized")))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void concurrentIdempotentSubmissionsStartAgentOnce() throws Exception {
        String key = UUID.randomUUID().toString();
        String question = "2026-11 华东成交单量";
        when(agent.analyze(eq(question), anyString())).thenReturn(plan("paid_orders"));
        var callers = Executors.newFixedThreadPool(2);
        try {
            Callable<QueryService.RunView> call = () -> service.create(key, question);
            var first = callers.submit(call);
            var second = callers.submit(call);
            String id = first.get(5, TimeUnit.SECONDS).id();
            assertThat(second.get(5, TimeUnit.SECONDS).id()).isEqualTo(id);
            await().untilAsserted(() -> assertThat(service.require(id).status()).isEqualTo("SUCCEEDED"));
            verify(agent, times(1)).analyze(question, id);
            assertThatThrownBy(() -> service.create(key, "另一条问题"))
                .isInstanceOfSatisfying(ResponseStatusException.class, exception ->
                    assertThat(exception.getStatusCode().value()).isEqualTo(409));
        } finally {
            callers.shutdownNow();
        }
    }

    @Test
    void upstreamFailurePersistsFailedWithoutAnAnswer() {
        String question = "模拟上游连接失败";
        when(agent.analyze(eq(question), anyString())).thenThrow(new IllegalStateException("服务不可用"));
        var created = service.create(UUID.randomUUID().toString(), question);
        await().untilAsserted(() -> {
            var finished = service.view(service.require(created.id()));
            assertThat(finished.status()).isEqualTo("FAILED");
            assertThat(finished.result()).isNull();
        });
    }

    private AgentClient.Plan plan(String metric) {
        return new AgentClient.Plan("ready", metric, "2026-11", "华东", "口径说明", "v1");
    }
}
