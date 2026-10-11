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
│   ├── parsers.py           # md/pdf/docx/xlsx/csv 解析（含表格列级解析 parse_table）
│   ├── knowledge.py         # 知识库 + 约束库加载
│   ├── memory.py            # 三层记忆（工作/任务/长期）+ 记忆治理
│   ├── agent.py             # 找核写追 + 四道门 + 授权停下
│   ├── datasmart.py         # 数据智能引擎（清洗/EVM 指标/快照预测/预警/建议）
│   ├── planning.py          # 计划与资源调度引擎（材料效力/输入检查/WBS/依赖/日历+CPM 排程/资源负荷/关键路径/版本与情景/证据与自动停止）
│   ├── doc_gen.py           # Word 生成
│   ├── deliverables.py      # 成果输出（F-39 干系人简报 / F-40 多成果模板）
│   └── routers/             # 项目/分析/看板/聊天/文档/数据智能/成果/记忆/计划路由
└── frontend/                # React 前端
    └── src/
        ├── App.jsx          # 应用外壳
        └── components/      # 导航/项目列表/模态框/看板/聊天/数据智能/计划与资源智能调度
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

## 云上部署（腾讯云 CloudBase）

采用**前后端分离**部署形态：

| 部分 | 承载 | 地址 |
|---|---|---|
| 前端 | 静态托管（CDN） | https://pm-assistant-d2g7eu0dk3a821546-1504037600.tcloudbaseapp.com/ |
| 后端 | 云托管 CloudRun（容器，端口 8080，公网访问） | https://pm-assistant-api-326600-10-1504037600.sh.run.tcloudbase.com |

- 环境 ID：`pm-assistant-d2g7eu0dk3a821546`（国内站，地域 `ap-shanghai`）
- 后端构建上下文：`deploy/`（Dockerfile + 由 `deploy/build.sh` 暂存的 `backend/`、`kb/`、`dataset/`、`dataset3/`，后四者不入仓；`dataset3` 为课程3 计划材料包，容器内以 `AGENT_PLAN_DATASET=/app/dataset3` 指向）
- 部署脚本：
  ```bash
  ./deploy/build.sh --deploy          # 后端：暂存上下文 → 云托管部署（密钥从工作区 .env 读取）
  API_BASE=https://<云托管域名>/api ./deploy/deploy-frontend.sh   # 前端：构建 → 静态托管
  ```
- 前端 API 地址由构建期变量 `VITE_API_BASE` 注入（未设置时默认同源 `/api`，本地开发不受影响）。

**云上限制（重要）**：容器文件系统是临时的——SQLite 数据库、用户创建的「项目文件夹路径」指向、`results/` 下生成的 Word 在实例重启/重调度后会丢失；能浏览的只有镜像内路径（`/app/kb`、`/app/dataset`、`/app/dataset3`）。需要持久化时应改用云数据库 + 云存储（见「后续可做」）。

## 功能清单

- **项目全局管理**：项目增删改查、数量统计、本地文件夹选择
- **文件自动识别**：API 自主区分项目文件类型（标书/合同/计划/团队/干系人/财务/风险），无需人工告知
- **项目看板**：四类信息可视化（项目 / 人员 / 财务 / 干系人）+ 冲突/行动项/来源文件
- **智能聊天**：接入 API，基于项目事实回答，标注来源、有据可查
- **文档生成**：Word 综合整理报告，可下载
- **成果输出**：周报 / 风险清单 / 成本说明 / RACI 职责表 / 会议纪要 / 干系人简报（6 类模板）+ 干系人分层简报（6 类切面），统一事实底稿、人工确认后外发
- **数据智能与决策**：七类数据源接入 → 清洗标准化 → EVM 指标（PV/EV/AC/SPI/CPI/EAC…）→ 八类看板 → 趋势预测 → 风险预警 → 决策建议
- **计划与资源智能调度**（课程3）：计划材料只读接入 → 文件效力八级与效力四问 → 输入检查七问 → 统一 WBS 与稳定 ID → 依赖与五类约束 → 工作日历 + 确定性排程（CPM：开始/完成/总时差/关键路径/里程碑偏差）→ 十类视图联动（WBS/看板/甘特/资源负荷/关键路径/冲突预警/版本比较/输入与效力/建议与确认/证据与停止）→ 资源可用性与冲突预警六要素 → 计划 V1 冻结与事件派生 V2 / S1·S2·S3 方案比较 → 建议六要素与五类人工确认关卡
- **三层记忆**：工作记忆 / 任务记忆 / 长期记忆，杜绝幻视与胡乱回答；长期记忆支持**记忆治理**（可更新 / 可纠错 / 可失效，失效记忆不参与召回，全程审计）

## 核心机制

- **找、核、写、追**：查找证据 → 核对事实 → 生成输出 → 追踪行动项
- **证据链**：文件 → 证据 → 事实 → 判断 → 行动 → 记忆沉淀
- **四道门**：事实门 → 结构门 → 可用性门 → 风险门
- **授权-停下**：缺关键材料 / 结论不可验证 / 权限不足 / 未确认时主动停下，不编造

## 安全约定

- API Key 仅存于本地 `.env`，绝不硬编码 / 打印 / 落库 / 上传
- 云上部署时密钥经**云托管服务环境变量**（CloudRun `EnvParams`）注入，不打进镜像；`deploy/build.sh` 只提取 LLM 相关键，不注入本机绝对路径类变量
- 敏感信息（身份证、手机号、银行卡、Key）在输出前自动隐藏，不写入记忆
- `AGENT_REQUIRE_HUMAN_APPROVAL=true`：Agent 只准备草稿与整理结果，不自动外发 / 审批
- 财务 / 合同 / 人事结论一律标记「需人工复核」

## 后续可做

- 数据持久化：SQLite → CloudBase 云数据库；生成的 Word → 云存储
- 云端项目导入：改为上传数据包（对象存储）而非浏览服务器磁盘路径
- 接入 CloudBase 身份认证，替换当前无鉴权的单机形态
