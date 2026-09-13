"""配置层：读取 .env，解析路径，暴露全局配置对象。

安全约定（对齐 02_千问API与env配置/千问API配置说明.md）：
- API Key 仅存于本地 .env，由程序读取，绝不硬编码/打印/落库。
- 相对路径以课程资料根目录（base_dir）为基准解析。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 目录定位：backend/ -> pm-assistant/
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
# 数据根目录（课程资料：知识库/约束库/输入包/.env 所在）。
# 代码独立存放后 parent.parent 不再是课程资料目录，可用 PM_ASSISTANT_BASE_DIR 显式指定；
# 默认仍为 parent.parent（保持代码内嵌于课程资料目录时的向后兼容）。
_BASE_OVERRIDE = os.environ.get("PM_ASSISTANT_BASE_DIR")
BASE_DIR = Path(_BASE_OVERRIDE).resolve() if _BASE_OVERRIDE else BACKEND_DIR.parent.parent

# .env 位置：优先 BASE_DIR/.env（新结构），回退旧结构 02_千问API与env配置/.env
_ENV_OVERRIDE = os.environ.get("PM_ASSISTANT_ENV")
if _ENV_OVERRIDE:
    ENV_FILE = Path(_ENV_OVERRIDE)
else:
    _new_env = BASE_DIR / ".env"
    _old_env = BASE_DIR / "02_千问API与env配置" / ".env"
    ENV_FILE = _new_env if _new_env.exists() else _old_env

load_dotenv(ENV_FILE)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _resolve(rel_path: str) -> Path:
    p = Path(rel_path)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


class Config:
    # ---- LLM ----
    api_key = _get("DASHSCOPE_API_KEY")
    base_url = _get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = _get("QWEN_MODEL", "qwen-plus")
    temperature = float(_get("AGENT_TEMPERATURE", "0.2"))
    max_output_tokens = int(_get("AGENT_MAX_OUTPUT_TOKENS", "12000"))

    # ---- 行为开关 ----
    enable_source_trace = _get("AGENT_ENABLE_SOURCE_TRACE", "true").lower() == "true"
    require_human_approval = _get("AGENT_REQUIRE_HUMAN_APPROVAL", "true").lower() == "true"

    # ---- 目录与文件 ----
    knowledge_dir = _resolve(_get("AGENT_KNOWLEDGE_DIR", "./03_本地知识库"))
    constraint_dir = _resolve(_get("AGENT_CONSTRAINT_DIR", "./04_文件处理约束库"))
    memory_file = _resolve(_get("AGENT_MEMORY_FILE", "./05_当前任务记忆体/current_task_memory.json"))
    input_dir = _resolve(_get("AGENT_INPUT_DIR", "./06_项目输入资料包"))
    output_dir = _resolve(_get("AGENT_OUTPUT_DIR", "./results"))
    log_dir = _resolve(_get("AGENT_LOG_DIR", "./logs"))

    # ---- 本地数据 ----
    _data_override = _get("AGENT_DATA_DIR", "")
    data_dir = _resolve(_data_override) if _data_override else (BACKEND_DIR / "data")
    # 数据库：优先沿用已有库文件（保留历史数据），否则用数据目录
    _legacy_db = BACKEND_DIR / "data" / "pm_assistant.db"
    db_path = _legacy_db if _legacy_db.exists() else (data_dir / "pm_assistant.db")


def ensure_dirs() -> None:
    """确保运行时目录存在。"""
    for d in (Config.data_dir, Config.output_dir, Config.log_dir):
        d.mkdir(parents=True, exist_ok=True)


def has_api_key() -> bool:
    return bool(Config.api_key)


ensure_dirs()
