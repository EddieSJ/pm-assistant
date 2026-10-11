#!/usr/bin/env python3
"""把工作区 .env 中的 LLM 配置注入云托管服务环境变量（不重新构建镜像）。

背景：本机 tcb CLI（3.8.6）的 `cloudrun deploy` 未注册 `--envParams`，
`cloudrun service:config` 也未注册，因此改用云 API：
  tcbr UpdateCloudRunServer + DeployInfo(复用当前线上镜像) + Items[Key=EnvParam]

用法：
  python3 deploy/set-env-params.py            # 注入
  python3 deploy/set-env-params.py --dry-run  # 只看会注入哪些键

安全：只读取并注入 LLM 相关键；脚本不回显密钥明文，也不会写入镜像。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DEPLOY_DIR.parent
WORKSPACE_DIR = PROJECT_DIR.parent

ENV_ID = "pm-assistant-d2g7eu0dk3a821546"
SERVER = "pm-assistant-api"

# 只注入这些键（LLM 相关）。绝不注入本机绝对路径类变量（AGENT_*_DIR 等）。
INJECT_KEYS = [
    "DASHSCOPE_API_KEY",
    "QWEN_BASE_URL",
    "QWEN_MODEL",
    "AGENT_TEMPERATURE",
    "AGENT_MAX_OUTPUT_TOKENS",
    "AGENT_ENABLE_SOURCE_TRACE",
    "AGENT_REQUIRE_HUMAN_APPROVAL",
]
DEFAULTS = {
    "QWEN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "QWEN_MODEL": "qwen-plus",
    "AGENT_TEMPERATURE": "0.2",
    "AGENT_MAX_OUTPUT_TOKENS": "12000",
    "AGENT_ENABLE_SOURCE_TRACE": "true",
    "AGENT_REQUIRE_HUMAN_APPROVAL": "true",
}


def tcb_api(action: str, body: dict) -> dict:
    r = subprocess.run(
        ["tcb", "api", "tcbr", action, "--api-version", "2022-02-17",
         "--body", json.dumps(body, ensure_ascii=False), "--json"],
        capture_output=True, text=True, input="n\n",
    )
    out = r.stdout
    i = out.find("{")
    if i < 0:
        raise RuntimeError(f"{action} 无 JSON 输出：{out[-300:]}{r.stderr[-300:]}")
    return json.loads(out[i:])


def read_env_file() -> dict:
    env: dict[str, str] = {}
    p = WORKSPACE_DIR / ".env"
    if not p.exists():
        print(f"ERROR: 未找到 {p}")
        sys.exit(1)
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--env-id", default=ENV_ID)
    ap.add_argument("--service-name", default=SERVER)
    args = ap.parse_args()

    detail = tcb_api("DescribeCloudRunServerDetail",
                     {"EnvId": args.env_id, "ServerName": args.service_name})["data"]
    versions = detail.get("OnlineVersionInfos") or []
    if not versions:
        print("ERROR: 服务当前没有线上版本，请先执行 deploy/build.sh --deploy")
        return 1
    image = versions[0]["ImageUrl"]
    print("线上版本:", versions[0]["VersionName"])
    print("复用镜像:", image)

    raw = read_env_file()
    if not raw.get("DASHSCOPE_API_KEY"):
        print("ERROR: .env 中未找到 DASHSCOPE_API_KEY")
        return 1
    want = {k: raw.get(k, DEFAULTS.get(k, "")) for k in INJECT_KEYS}
    print("将注入键:", ", ".join(k for k in want if want[k]))
    print("密钥长度:", len(want["DASHSCOPE_API_KEY"]), "（不回显明文）")

    if args.dry_run:
        print("dry-run：未提交。")
        return 0

    body = {
        "EnvId": args.env_id,
        "ServerName": args.service_name,
        "DeployInfo": {
            "DeployType": "image",
            "ImageUrl": image,
            "ReleaseType": "FULL",
            "DeployRemark": "inject-llm-env-params",
        },
        "Items": [{"Key": "EnvParam", "Value": json.dumps(want, ensure_ascii=False)}],
    }
    res = tcb_api("UpdateCloudRunServer", body)
    print("提交结果:", json.dumps(res, ensure_ascii=False))
    print("约 1 分钟后用 /api/health 确认 has_api_key=true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
