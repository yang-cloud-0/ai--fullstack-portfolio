package portfolio.analytics;

import java.math.BigDecimal;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
interface MetricMapper {
    // SQL 表达式由服务端预定义，年月与区域使用绑定参数。
    @Select("""
        SELECT COALESCE(SUM(CASE #{metric}
            WHEN 'order_count' THEN 1
            WHEN 'paid_orders' THEN CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END
            WHEN 'net_revenue' THEN CASE WHEN order_status = 'PAID' THEN amount - refund ELSE 0 END
            WHEN 'refund_amount' THEN CASE WHEN order_status = 'PAID' THEN refund ELSE 0 END
        END), 0)
        FROM demo_order
        WHERE period_month = #{month} AND (#{region} = '全国' OR region = #{region})
        """)
    BigDecimal aggregate(@Param("metric") String metric, @Param("month") String month,
                         @Param("region") String region);
}
