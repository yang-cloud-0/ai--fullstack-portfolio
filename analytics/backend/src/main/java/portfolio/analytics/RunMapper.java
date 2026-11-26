package portfolio.analytics;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
interface RunMapper {
    record Row(String id, String requestKey, String question, String status, boolean started,
               String resultJson, String message) {}

    @Insert("""
        INSERT INTO query_run (id, request_key, question, status)
        VALUES (#{id}, #{key}, #{question}, 'QUEUED')
        """)
    void insert(@Param("id") String id, @Param("key") String key, @Param("question") String question);

    @Select("SELECT * FROM query_run WHERE id = #{id}")
    Row find(String id);

    @Select("SELECT * FROM query_run WHERE request_key = #{key}")
    Row findByKey(String key);

    @Update("UPDATE query_run SET status = 'RUNNING', started = TRUE WHERE id = #{id} AND status = 'QUEUED'")
    int start(String id);

    @Update("""
        UPDATE query_run SET status = #{status}, result_json = #{result}, message = #{message}
        WHERE id = #{id} AND status IN ('QUEUED', 'RUNNING')
        """)
    void finish(@Param("id") String id, @Param("status") String status,
                @Param("result") String result, @Param("message") String message);

    @Update("""
        UPDATE query_run SET status = 'FAILED', message = '服务重启打断了查询，请重新发起'
        WHERE status IN ('QUEUED', 'RUNNING')
        """)
    void recoverInterrupted();
}
