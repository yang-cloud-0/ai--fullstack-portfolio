package portfolio.analytics;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Map;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
class MetricService {
    private static final Logger LOG = LoggerFactory.getLogger(MetricService.class);
    private static final Map<String, Metric> METRICS = Map.of(
        "order_count", new Metric("订单总数", "笔"),
        "paid_orders", new Metric("支付订单数", "笔"),
        "net_revenue", new Metric("净销售额", "元"),
        "refund_amount", new Metric("退款总额", "元")
    );
    private static final Set<String> REGIONS = Set.of("华东", "华北", "华南", "全国");
    private static final String DATASET_VERSION = "demo-orders-v1";

    record Metric(String name, String unit) {}
    record Result(String metric, String label, String month, String region,
                  BigDecimal value, String unit, String source, String reason) {}

    private final MetricMapper mapper;
    private final StringRedisTemplate redis;
    private final boolean cacheEnabled;

    MetricService(MetricMapper mapper, StringRedisTemplate redis,
                  @Value("${analytics.redis.enabled}") boolean cacheEnabled) {
        this.mapper = mapper;
        this.redis = redis;
        this.cacheEnabled = cacheEnabled;
    }

    Result query(AgentClient.Plan plan) {
        if (!"v1".equals(plan.version()) || plan.metric() == null || !METRICS.containsKey(plan.metric())
                || plan.month() == null || !plan.month().matches("20[0-9]{2}-(0[1-9]|1[0-2])")
                || plan.region() == null || !REGIONS.contains(plan.region())) {
            throw new IllegalArgumentException("查询计划含有不支持的指标或筛选条件");
        }

        Metric metric = METRICS.get(plan.metric());
        String key = String.join(":", "analytics", DATASET_VERSION, plan.version(), plan.metric(),
            plan.month(), plan.region());
        BigDecimal value = readCache(key);
        String source = "database";
        if (value == null) {
            value = mapper.aggregate(plan.metric(), plan.month(), plan.region());
            storeCache(key, value);
        } else {
            source = "cache";
        }
        return new Result(plan.metric(), metric.name(), plan.month(), plan.region(), value,
            metric.unit(), source, plan.reason());
    }

    private BigDecimal readCache(String key) {
        if (!cacheEnabled) {
            return null;
        }
        try {
            String value = redis.opsForValue().get(key);
            return value == null ? null : new BigDecimal(value);
        } catch (DataAccessException | NumberFormatException exception) {
            LOG.warn("读取指标缓存失败，继续查询数据库，类型={}", exception.getClass().getSimpleName());
            return null;
        }
    }

    private void storeCache(String key, BigDecimal value) {
        if (cacheEnabled) {
            try {
                redis.opsForValue().set(key, value.toPlainString(), Duration.ofMinutes(3));
            } catch (DataAccessException exception) {
                LOG.warn("写入指标缓存失败，类型={}", exception.getClass().getSimpleName());
            }
        }
    }
}
