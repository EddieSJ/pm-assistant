# 项目管理智能助手 —— 后端（FastAPI）镜像
#
# 构建上下文 = **仓库根目录**（不是 deploy/）。
# CloudBase 云托管「通过 Git 仓库部署」时的构建参数：
#     目标目录   = .
#     Dockerfile = Dockerfile
# 本地等价命令：docker build -t pm-assistant-api .

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

# 2) 应用代码
COPY backend/ /app/backend/

# 3) 静态资产：课程资料（知识库/约束库/任务记忆体/输入包）、模拟数据包、课程3 计划数据包
#    这些目录由仓库内的 assets/ 提供，云端构建机无需访问仓库之外的任何文件。
COPY assets/kb/           /app/kb/
COPY assets/dataset/      /app/dataset/
COPY assets/plan-dataset/ /app/dataset3/

# 4) 运行：云托管要求监听注入的 PORT，且必须绑 0.0.0.0
WORKDIR /app/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
