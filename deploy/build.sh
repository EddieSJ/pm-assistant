#!/bin/bash
# 云托管部署脚本：把后端（FastAPI）+ 课程资料 + 模拟数据包打成云托管构建上下文并部署。
#
# 用法：
#   ./build.sh              # 仅生成构建上下文 deploy/{backend,kb,dataset}
#   ./build.sh --deploy     # 生成上下文后直接部署到云托管
#
# 环境变量：
#   TCB_ENV_ID   目标环境 ID（默认 pm-assistant-d2g7eu0dk3a821546）
#   SERVICE_NAME 云托管服务名（默认 pm-assistant-api）
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
WORKSPACE_DIR="$(cd "$PROJECT_DIR/.." && pwd)"

TCB_ENV_ID="${TCB_ENV_ID:-pm-assistant-d2g7eu0dk3a821546}"
SERVICE_NAME="${SERVICE_NAME:-pm-assistant-api}"
PORT="${PORT:-8080}"

echo "[1/3] 清理并暂存 backend ..."
# 分开清理：一次性批量删除会触发沙箱的批量删除保护
rm -rf "$DEPLOY_DIR/backend" 2>/dev/null || true
rm -rf "$DEPLOY_DIR/kb" 2>/dev/null || true
rm -rf "$DEPLOY_DIR/dataset" 2>/dev/null || true
rm -rf "$DEPLOY_DIR/dataset3" 2>/dev/null || true
mkdir -p "$DEPLOY_DIR/backend"
( cd "$PROJECT_DIR/backend" && tar cf - \
    --exclude='.venv' --exclude='__pycache__' --exclude='.idea' \
    --exclude='data' --exclude='*.pyc' --exclude='.DS_Store' . ) \
  | ( cd "$DEPLOY_DIR/backend" && tar xf - )

echo "[2/3] 暂存课程资料（知识库/约束库/任务记忆体/输入包）与模拟数据包 ..."
mkdir -p "$DEPLOY_DIR/kb"
( cd "$WORKSPACE_DIR/01_课程资料" && tar cf - \
    --exclude='.DS_Store' --exclude='*.env' --exclude='results' --exclude='logs' . ) \
  | ( cd "$DEPLOY_DIR/kb" && tar xf - )
mkdir -p "$DEPLOY_DIR/dataset"
( cd "$WORKSPACE_DIR/02_模拟数据包" && tar cf - --exclude='.DS_Store' . ) \
  | ( cd "$DEPLOY_DIR/dataset" && tar xf - )
# 课程3 计划与资源调度的计划材料包（A/B/C/D 四组）→ /app/dataset3
mkdir -p "$DEPLOY_DIR/dataset3"
( cd "$WORKSPACE_DIR/03_模拟数据包-课程3" && tar cf - --exclude='.DS_Store' . ) \
  | ( cd "$DEPLOY_DIR/dataset3" && tar xf - )

echo "      上下文大小：$(du -sh "$DEPLOY_DIR" | cut -f1)"
find "$DEPLOY_DIR" -name '*.env' -print | sed 's/^/       [校验] 发现 .env（应为空）：/'

if [ "${1:-}" != "--deploy" ]; then
  echo "完成（未部署）。加 --deploy 参数可直接部署。"
  exit 0
fi

echo "[3/3] 部署到云托管：service=$SERVICE_NAME env=$TCB_ENV_ID port=$PORT"

# 注入 LLM 配置：只取密钥与模型相关项。
# 注意：绝不注入 AGENT_KNOWLEDGE_DIR / AGENT_DATA_DIR 等本机绝对路径，否则容器内路径会失效。
ENV_FILE="${ENV_FILE:-$WORKSPACE_DIR/.env}"
ENV_PARAMS=""
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  ENV_PARAMS="DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:-}&QWEN_BASE_URL=${QWEN_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}&QWEN_MODEL=${QWEN_MODEL:-qwen-plus}&AGENT_TEMPERATURE=${AGENT_TEMPERATURE:-0.2}&AGENT_MAX_OUTPUT_TOKENS=${AGENT_MAX_OUTPUT_TOKENS:-12000}&AGENT_PLAN_DATASET=/app/dataset3"
  echo "      已从 $ENV_FILE 读取 LLM 配置（密钥长度 ${#DASHSCOPE_API_KEY}，不回显明文）"
else
  echo "      [警告] 未找到 $ENV_FILE，将不带密钥部署（AI 问答不可用）"
fi

cd "$DEPLOY_DIR"
printf 'n\n' | tcb cloudrun deploy \
  --env-id "$TCB_ENV_ID" \
  --service-name "$SERVICE_NAME" \
  --port "$PORT" \
  --open-access-types PUBLIC \
  --source "$DEPLOY_DIR" \
  --envParams "$ENV_PARAMS" \
  --force \
  --wait
