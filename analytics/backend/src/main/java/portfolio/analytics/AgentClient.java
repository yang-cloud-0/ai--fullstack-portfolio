package portfolio.analytics;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class AgentClient {
    record Plan(String status, String metric, String month, String region, String reason, String version) {}
    record Request(String question) {}

    private final RestClient client;

    AgentClient(@Value("${analytics.agent-url}") String agentUrl) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1500);
        factory.setReadTimeout(8500);
        client = RestClient.builder().baseUrl(agentUrl).requestFactory(factory).build();
    }

    Plan analyze(String question, String traceId) {
        return client.post().uri("/analyze").header("X-Trace-Id", traceId)
            .body(new Request(question)).retrieve().body(Plan.class);
    }
}
