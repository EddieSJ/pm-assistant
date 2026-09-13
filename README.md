# 项目管理智能助手（私人本地 Agent Web 平台）

为项目经理打造的**私人智能体项目管理助手**：通过外部 env 接入大模型 API，自动识别项目文件夹中的各类文档，提取关键信息，落到本地记忆体，实现「有据可依、有理有据、有记忆有标准」的项目管理中枢。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + Vite 5 |
| 后端 | Python FastAPI |
| 数据库 | SQLite（本地） |
| 大模型 | 阿里云百炼 DashScope 千问（OpenAI 兼容） |
| 文件解析 | .md / .pdf / .docx / .xlsx |

## 目录结构

```
pm-assistant/
├── backend/                 # FastAPI 后端
│   ├── main.py              # 入口（托管前端 + API）
│   ├── config.py            # 读取 .env，解析路径
│   ├── db.py                # SQLite 建表
│   ├── llm_client.py        # 千问调用（含流式）
│   ├── parsers.py           # md/pdf/docx/xlsx 解析
│   ├── knowledge.py         # 知识库 + 约束库加载
│   ├── memory.py            # 三层记忆（工作/任务/长期）
│   ├── agent.py             # 找核写追 + 四道门 + 授权停下
│   ├── doc_gen.py           # Word 生成
│   └── routers/             # 项目/分析/看板/聊天/文档路由
└── frontend/                # React 前端
    └── src/
        ├── App.jsx          # 应用外壳
        └── components/      # 导航/项目列表/模态框/看板/聊天
```

> **代码与课程资料已分离**：本项目代码独立存放（`pm-assistant/`），课程资料（`.env`、`03_本地知识库`、`04_文件处理约束库`、`05_当前任务记忆体`、`06_项目输入资料包`、`results`、`logs`）位于上一级 `课时1课程资料/` 目录。运行时通过环境变量 `PM_ASSISTANT_BASE_DIR` 指定课程资料根目录；`start.sh` 会自动计算注入，手动启动时需自行 `export`（见下方步骤 3）。

## 快速启动

```bash
# 1. 后端（首次需建虚拟环境装依赖）
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 2. 前端构建（首次需 npm install）
cd ../frontend
npm install
npm run build

# 3. 启动（单端口 8000，托管前端 + API）
cd ../backend
export PM_ASSISTANT_BASE_DIR="$(cd .. && pwd)/课时1课程资料"
./.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

访问 **http://127.0.0.1:8000**

也可一键启动：`./start.sh`

## 功能清单

- **项目全局管理**：项目增删改查、数量统计、本地文件夹选择
- **文件自动识别**：API 自主区分项目文件类型（标书/合同/计划/团队/干系人/财务/风险），无需人工告知
- **项目看板**：四类信息可视化（项目 / 人员 / 财务 / 干系人）+ 冲突/行动项/来源文件
- **智能聊天**：接入 API，基于项目事实回答，标注来源、有据可查
- **文档生成**：Word 综合整理报告，可下载
- **三层记忆**：工作记忆 / 任务记忆 / 长期记忆，杜绝幻视与胡乱回答

## 核心机制

- **找、核、写、追**：查找证据 → 核对事实 → 生成输出 → 追踪行动项
- **证据链**：文件 → 证据 → 事实 → 判断 → 行动 → 记忆沉淀
- **四道门**：事实门 → 结构门 → 可用性门 → 风险门
- **授权-停下**：缺关键材料 / 结论不可验证 / 权限不足 / 未确认时主动停下，不编造

## 安全约定

- API Key 仅存于本地 `.env`，绝不硬编码 / 打印 / 落库 / 上传
- 敏感信息（身份证、手机号、银行卡、Key）在输出前自动隐藏，不写入记忆
- `AGENT_REQUIRE_HUMAN_APPROVAL=true`：Agent 只准备草稿与整理结果，不自动外发 / 审批
- 财务 / 合同 / 人事结论一律标记「需人工复核」
