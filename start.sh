#!/bin/bash
# 项目管理智能助手 - 一键启动脚本
set -e

# 定位脚本目录（代码目录）并计算课程资料根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PM_ASSISTANT_BASE_DIR="$SCRIPT_DIR/../课时1课程资料"

cd "$SCRIPT_DIR"

# 1. 后端虚拟环境
cd backend
if [ ! -d ".venv" ]; then
  echo "[1/3] 创建后端虚拟环境并安装依赖..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
else
  echo "[1/3] 后端虚拟环境已就绪"
fi

# 2. 前端构建
cd ../frontend
if [ ! -d "dist" ]; then
  echo "[2/3] 安装前端依赖并构建..."
  npm install --no-audit --no-fund
  npm run build
else
  echo "[2/3] 前端已构建（如需重新构建请删除 dist 目录）"
fi

# 3. 启动后端（单端口 8000）
cd ../backend
echo "[3/3] 启动服务：http://127.0.0.1:8000"
./.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
