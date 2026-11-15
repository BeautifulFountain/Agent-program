# AgentFlow 多智能体编排平台

AgentFlow 是一个面向复杂科研任务的多智能体编排、调度、执行与验证平台。项目以轻量 DAG 调度器为核心，展示多个 Agent 的依赖调度、并行研究、结果核验以及低质量结果的自动返工闭环。

## 已实现能力

- 7 个内置科研 Agent：需求、规划、文献、数据、写作、事实核验、质量评审
- Agent 注册、查询、修改和版本管理 API
- 基于依赖就绪状态的 DAG 动态调度，文献与数据节点并行执行
- 节点超时、失败重试、任务取消和最大循环保护
- 规则约束与评审 Agent 结合的结构化质量评分
- 低于阈值时执行“写作 → 核验 → 评审”定向返工
- SQLite 保存工作流快照、节点输入输出、耗时、评分、Token 与错误
- SSE 运行事件接口以及前端实时轮询展示
- DeepSeek OpenAI 兼容接口与无密钥 Mock 演示模式
- React Flow 工作流图、控制台、Agent管理、任务发起和运行详情页

## 系统架构

```text
React + TypeScript
       │ REST / SSE
       ▼
FastAPI API 层
       │
       ├── Agent Registry
       ├── DAG Scheduler ── 并行 / 重试 / 超时 / 取消
       ├── Validation Loop ── 评分 / 反馈 / 定向返工
       ├── LLM Adapter ── DeepSeek / Mock
       └── SQLite Audit Store
```

## 快速开始

### 1. 后端

```powershell
cd D:\agent_program
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如需调用真实 DeepSeek API，编辑 `.env`：

```env
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_MOCK=false
```

密钥不得提交到代码仓库。启动后端：

```powershell
.\start-backend.ps1
```

API 文档位于 `http://127.0.0.1:8000/docs`。

### 2. 前端

新开一个 PowerShell：

```powershell
cd D:\agent_program\frontend
pnpm install
pnpm run dev
```

浏览器访问 `http://127.0.0.1:5173`。

## 测试和构建

```powershell
python -m pytest -q
cd frontend
pnpm run build
```

自动化测试默认使用 Mock LLM，不会产生 API 费用。Mock 模式第一轮返回 72 分并触发返工，第二轮返回 88 分，用于稳定演示 Self-Loop。

## 主要接口

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 服务与模型模式状态 |
| `GET/POST /api/agents` | Agent 查询和创建 |
| `PUT/DELETE /api/agents/{id}` | Agent 更新和删除 |
| `GET/POST /api/workflows` | 工作流查询和创建 |
| `PUT /api/workflows/{id}` | 工作流版本更新 |
| `POST /api/runs` | 创建任务并启动调度 |
| `GET /api/runs/{id}` | 查询完整运行快照 |
| `POST /api/runs/{id}/cancel` | 取消运行 |
| `GET /api/runs/{id}/events` | SSE 运行事件 |
| `POST /api/llm/test` | 开发环境模型连通测试 |

所有标准接口返回 `data`、`error_code`、`message` 和 `trace_id`。

## 安全与费用控制

- API Key 仅通过 `.env` 注入，`.env` 已加入 `.gitignore`。
- 模型异常信息在返回前脱敏，生产环境关闭连通测试接口。
- 单节点默认最多重试 1 次，工作流最多返工 3 轮。
- 每次运行记录累计 Token，便于设置预算告警。
- 计算工具使用受限 AST，不执行任意 Python 代码。

## 当前边界

- 工作流画布当前用于可视化，编辑保存接口已具备，拖拽持久化将在下一迭代接入。
- 本地知识库首版支持 Markdown/TXT 关键词检索，尚未引入向量数据库。
- 单机 SQLite 适合比赛原型；生产集群需迁移到 PostgreSQL 和任务队列。

