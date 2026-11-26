# 查询计划服务

在当前目录用 Python 3.11+ 安装 `requirements.txt`，执行 `python -m uvicorn main:app --port 8001`。测试时额外安装 pytest，再执行 `python -m pytest -q`。

默认通过模拟电商指标目录进行规则解析。设置 `MODEL_CHAT_COMPLETIONS_URL`、`MODEL_NAME`、`MODEL_API_KEY` 后，由 OpenAI 兼容接口生成解释。模型超时或返回格式错误时使用目录定义。年月、区域和查询指标由程序校验，歧义问题进入澄清分支。

区域和月份已明确、指标仍未命中时，模型可通过 `suggest_metric` 提议一个目录内的指标。工具参数由程序重新验证，模型建议只用于补充澄清提示。用户明确确认指标后才会查询数据库。展示时将目录定义和模型说明分别标明。
