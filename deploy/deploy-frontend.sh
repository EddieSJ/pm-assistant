#!/bin/bash
# 前端部署脚本：构建 Vite 产物并发布到 CloudBase 静态托管。
#
# 用法：
#   API_BASE=https://<后端云托管域名>/api ./deploy-frontend.sh
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

TCB_ENV_ID="${TCB_ENV_ID:-pm-assistant-d2g7eu0dk3a821546}"
API_BASE="${API_BASE:-}"
if [ -z "$API_BASE" ]; then
  echo "请通过 API_BASE 指定后端地址，例如："
  echo "  API_BASE=https://pm-assistant-api-xxxx.ap-shanghai.app.tcloudbase.com/api $0"
  exit 1
fi

cd "$PROJECT_DIR/frontend"
[ -d node_modules ] || npm install --no-audit --no-fund

echo "[1/2] 构建前端（VITE_API_BASE=$API_BASE）"
VITE_API_BASE="$API_BASE" npm run build

echo "[2/2] 部署到静态托管 env=$TCB_ENV_ID"
printf 'n\n' | tcb hosting deploy ./dist --env-id "$TCB_ENV_ID" --prune
