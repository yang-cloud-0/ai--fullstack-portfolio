"""从显式传入的 TOML 文件或用户配置目录选择模型。"""

import tomllib
from pathlib import Path

from .providers import ProviderConfig


def load_config(path: Path, name: str | None) -> ProviderConfig:
    with path.open("rb") as file:
        settings = tomllib.load(file)
    model_name = name or settings.get("default")
    providers = settings.get("providers")
    if not isinstance(providers, dict) or model_name not in providers:
        raise ValueError("未找到请求的模型配置，请核对 default 和 providers")
    selected = providers[model_name]
    if not isinstance(selected, dict) or selected.get("protocol") not in {"openai", "anthropic"}:
        raise ValueError("protocol 须为 openai 或 anthropic")
    for field in ("endpoint", "model"):
        if not isinstance(selected.get(field), str) or not selected[field].strip():
            raise ValueError(f"配置缺少 {field}")
    key_env = selected.get("api_key_env", "")
    if not isinstance(key_env, str):
        raise ValueError("api_key_env 应填写环境变量名")
    return ProviderConfig(selected["protocol"], selected["endpoint"], selected["model"], key_env)
