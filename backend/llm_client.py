"""LLM 客户端：调用阿里云百炼 DashScope 千问（OpenAI 兼容接口）。

安全：API Key 仅从环境读取，绝不打日志；异常向上抛出由上层处理。
"""
import json
import httpx

from config import Config


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {Config.api_key}",
        "Content-Type": "application/json",
    }


def chat(messages: list[dict], temperature: float | None = None,
         max_tokens: int | None = None, response_format: dict | None = None) -> str:
    """非流式对话，返回助手文本。"""
    url = Config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": Config.model,
        "messages": messages,
        "temperature": Config.temperature if temperature is None else temperature,
        "max_tokens": Config.max_output_tokens if max_tokens is None else max_tokens,
        "stream": False,
    }
    if response_format:
        payload["response_format"] = response_format

    with httpx.Client(timeout=180) as client:
        resp = client.post(url, headers=_headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def chat_stream(messages: list[dict], temperature: float | None = None,
                max_tokens: int | None = None):
    """流式对话，逐块 yield 文本增量。"""
    url = Config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": Config.model,
        "messages": messages,
        "temperature": Config.temperature if temperature is None else temperature,
        "max_tokens": Config.max_output_tokens if max_tokens is None else max_tokens,
        "stream": True,
    }
    with httpx.Client(timeout=180) as client:
        with client.stream("POST", url, headers=_headers(), json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def extract_json(text: str) -> dict | list | None:
    """从 LLM 返回文本中稳健地提取 JSON（剥除可能的代码围栏/前后缀）。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None
