# AI 全栈项目集

两个用 AI 辅助实现的个人练习项目。数据与模型回放均为演示样例，问题、方案和验收过程收录在 [中文验收记录](docs/verification.md)。

| 项目 | 可以演示的内容 | 主要技术 |
| --- | --- | --- |
| [电商经营问数助手](#电商经营问数助手) | 同一批订单按两种口径得到 3 与 5，异步处理、断线续传、Redis 停服回退 | Spring Boot、MyBatis、MySQL、Redis、FastAPI、LangGraph、Vue 3 |
| [MewCode 多协议终端助手](mewcode/README.md) | 两种流式协议回放、终端多轮对话、错误分类、断流后历史不变 | Python、HTTPX、SSE、Textual、pytest |

## 电商经营问数助手

Vue 页面提交问题。Java 为任务分配 ID 并保存状态，Python 召回指标定义、生成结构化查询计划，Java 校验计划后用 MyBatis 执行绑定参数的聚合查询。任务进度通过 SSE 返回页面，刷新时沿用原任务。代码演示单实例流程，数据库与 Redis 仅在容器内部网络可见。

### Docker Compose 运行

在仓库根目录执行：

```sh
docker compose up --build -d
docker compose ps
```

待各服务启动后，访问 `http://127.0.0.1:5173`。查询「2026-11 华东成交单量」得到 3 笔，查询「2026-11 华东订单总数」得到 5 笔。查询「华东的订单怎样」时，系统要求补年月与明确指标。停止服务用 `docker compose down`。

默认使用样例数据、规则检索和目录说明。配置下列环境变量后再启动，可通过兼容接口验证模型说明与工具建议。

| 环境变量 | 含义 |
| --- | --- |
| `MODEL_CHAT_COMPLETIONS_URL` | OpenAI 兼容接口的完整 URL |
| `MODEL_NAME` | 已开通的模型名称 |
| `MODEL_API_KEY` | 模型访问密钥 |
| `ANALYTICS_DB_PASSWORD` | 自定义本地演示数据库密码 |

指标不明确时，模型只能建议目录中的指标。用户重新提交并明确指标后，后端才执行查询。模型说明和权威目录定义在页面分开显示。

### 不依赖 Docker 的本地路径

分别打开三个终端：

1. 在 `analytics/agent` 安装 `requirements.txt`，执行 `python -m uvicorn main:app --port 8001`。
2. 在 `analytics/backend` 使用 JDK 21 和 Maven，执行 `mvn spring-boot:run`。默认使用兼容模式 H2，关闭 Redis。
3. 在 `analytics/web` 使用 Node.js 22，执行 `npm ci` 和 `npm run dev`。

浏览器打开 `http://localhost:5173`。执行下列命令可验证实际接口。需要先安装 Python 的 HTTPX。

```sh
python analytics/scripts/smoke.py
python analytics/scripts/smoke.py --base-url http://127.0.0.1:5173 --expect-redis
```

第一条走直接启动的 Java 服务。第二条走容器前端代理，并额外验证缓存命中。

## MewCode 多协议终端助手

在 `mewcode` 目录执行 `python -m pip install -e ".[test]"`，运行 `mewcode --demo openai` 打开 Textual 界面，也可以用 `mewcode --demo anthropic --prompt "介绍一下 SSE"` 回放第二种协议。两种演示都不消耗模型调用额度。更多见 [模型配置和验证方法](mewcode/README.md)。
