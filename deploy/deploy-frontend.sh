#!/bin/bash
# 前端部署脚本（本地手动兜底）。
#
# 正常路径是 GitHub Actions：.github/workflows/deploy-frontend.yml
#
# 用法：
#   API_BASE=https://<后端云托管域名>/api ./deploy-frontend.sh
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

TCB_ENV_ID="${TCB_ENV_ID:-pm-assistant-d2g7eu0dk3a821546}"
API_BASE="${API_BASE:-}"
if [ -z "$API_BASE" ]; then
  echo "请通过 API_BASE 指定后端地址，例如：" >&2
  echo "  API_BASE=https://pm-assistant-api-326600-10-1504037600.sh.run.tcloudbase.com/api $0" >&2
  exit 1
fi

cd "$PROJECT_DIR/frontend"
[ -d node_modules ] || npm ci

echo "[1/2] 构建前端（VITE_API_BASE=$API_BASE）"
VITE_API_BASE="$API_BASE" npm run build

# ⚠️ 不使用 --prune：静态托管根目录下还放着 cloud-admin/index.html 与
#    身份认证内置页 __auth/**，它们不属于前端构建产物，--prune 会把它们删掉。
echo "[2/2] 部署到静态托管 env=$TCB_ENV_ID"
tcb hosting deploy ./dist --env-id "$TCB_ENV_ID" --verify
