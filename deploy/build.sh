#!/bin/bash
# 云托管部署脚本（本地手动兜底）。
#
# 构建上下文 = **仓库根目录**，Dockerfile = 仓库根 `Dockerfile`。
# 正常路径是 GitHub Actions：.github/workflows/deploy-backend.yml
# 本脚本用于 CI 不可用时的本地应急部署。
#
# 用法：
#   ./build.sh              # 从仓库根构建并部署到云托管
#   ./build.sh --env-only   # 只把工作区 .env 的 LLM 配置注入服务环境变量（不重新构建镜像）
#
# 环境变量：
#   TCB_ENV_ID   目标环境 ID（默认 pm-assistant-d2g7eu0dk3a821546）
#   SERVICE_NAME 云托管服务名（默认 pm-assistant-api）
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

TCB_ENV_ID="${TCB_ENV_ID:-pm-assistant-d2g7eu0dk3a821546}"
SERVICE_NAME="${SERVICE_NAME:-pm-assistant-api}"
PORT="${PORT:-8080}"

if [ "${1:-}" = "--env-only" ]; then
  exec python3 "$DEPLOY_DIR/set-env-params.py"
fi

echo "[1/2] 校验构建依赖 ..."
for p in Dockerfile backend/requirements.txt assets/kb assets/dataset assets/plan-dataset; do
  if [ ! -e "$PROJECT_DIR/$p" ]; then
    echo "      缺少 $p，无法构建" >&2
    exit 1
  fi
done
echo "      OK（构建上下文：$PROJECT_DIR）"

# 安全校验：构建上下文里不得出现任何 .env
if find "$PROJECT_DIR/backend" "$PROJECT_DIR/assets" -name '*.env' -print -quit | grep -q .; then
  echo "      发现 .env，已中止。请先清理后再构建。" >&2
  find "$PROJECT_DIR/backend" "$PROJECT_DIR/assets" -name '*.env' >&2
  exit 1
fi

echo "[2/2] 部署到云托管：service=$SERVICE_NAME env=$TCB_ENV_ID port=$PORT"
cd "$PROJECT_DIR"
# 说明：不传 --envParams（本 CLI 版本未注册该参数，且环境变量为全量覆盖语义）。
#       LLM 相关环境变量请在云托管控制台维护，或用 ./build.sh --env-only 注入。
tcb cloudrun deploy \
  --env-id "$TCB_ENV_ID" \
  --service-name "$SERVICE_NAME" \
  --port "$PORT" \
  --open-access-types PUBLIC \
  --source "$PROJECT_DIR" \
  --force \
  --wait

echo "完成。若 AI 问答不可用，执行 ./build.sh --env-only 重新注入 LLM 环境变量。"
