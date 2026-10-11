# 【已弃用 · 请勿新增改动】
# 规范镜像定义已迁移到 **仓库根目录的 `Dockerfile`**（构建上下文 = 仓库根），
# 供 GitHub Actions / 云托管 Git 部署使用。
# 本文件仅保留给「旧版上下文装配流程」使用：它依赖 deploy/{backend,kb,dataset,dataset3}
# 这些由旧版 build.sh 生成的副本，而新版 build.sh 已改为直接使用仓库根，不再生成它们。
# 因此本文件随时可能失效，如需清理可直接删除。
#
# 项目管理智能助手 —— 后端（FastAPI）镜像
# 构建上下文：pm-assistant/deploy/
# 由 deploy/build.sh 生成上下文（backend/ kb/ dataset/），勿直接构建仓库根目录。

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PM_ASSISTANT_BASE_DIR=/app/kb \
    AGENT_PLAN_DATASET=/app/dataset3 \
    PORT=8080

WORKDIR /app

# 1) Python 依赖（先装依赖，利用层缓存）
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 2) 应用代码 + 课程资料（知识库/约束库/任务记忆体/输入包）+ 模拟数据包（课程2 / 课程3）
COPY backend/  /app/backend/
COPY kb/       /app/kb/
COPY dataset/  /app/dataset/
COPY dataset3/ /app/dataset3/

# 3) 运行：云托管要求监听注入的 PORT，且必须绑 0.0.0.0
WORKDIR /app/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
