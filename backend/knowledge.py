"""知识库与约束库加载：把目录下的 .md 文件读入内存供 Agent 使用。"""
from pathlib import Path

from config import Config


def _load_dir(directory: Path) -> dict[str, str]:
    """加载目录下所有 .md 文件，返回 {文件名: 内容}。"""
    result: dict[str, str] = {}
    if not directory.exists():
        return result
    for f in sorted(directory.glob("*.md")):
        try:
            result[f.name] = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return result


def load_knowledge() -> dict[str, str]:
    """企业知识库（03_本地知识库）。"""
    return _load_dir(Config.knowledge_dir)


def load_constraints() -> dict[str, str]:
    """文件处理约束库（04_文件处理约束库）。"""
    return _load_dir(Config.constraint_dir)


def knowledge_text() -> str:
    """知识库拼接文本，用于注入系统提示。"""
    kb = load_knowledge()
    parts = []
    for name, content in kb.items():
        parts.append(f"# {name}\n{content}")
    return "\n\n".join(parts)


def constraints_text() -> str:
    """约束库拼接文本，用于注入系统提示。"""
    cb = load_constraints()
    parts = []
    for name, content in cb.items():
        parts.append(f"# {name}\n{content}")
    return "\n\n".join(parts)
