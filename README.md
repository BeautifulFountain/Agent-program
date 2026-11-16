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
- 中文分词与分段召回的本地知识库，返回标题、机构、日期、原始链接和证据片段
- 知识库管理页面支持 Markdown/TXT 上传、预览、删除和独立检索测试，内置 16 份治理与研究方法资料
- 动态 Agent 推荐根据任务特征选择协作角色，并同步生成运行流程快照
- 事实核验 Agent 使用原始任务独立复检知识库证据，核验与评审反馈均限制为最多 6 项
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

需要不消耗 API 余额地验证完整流程时，运行 `.\start-backend.ps1 -Mock`。若默认端口被占用，可显式指定端口，例如 `.\start-backend.ps1 -Mock -Port 8010`。

API 文档位于 `http://127.0.0.1:8000/docs`。

### 2. 前端

新开一个 PowerShell：

```powershell
cd D:\agent_program\frontend
pnpm install
cd ..
.\start-frontend.ps1
```

浏览器访问 `http://127.0.0.1:5173`。

若默认端口被占用，可使用 `.\start-frontend.ps1 -Port 5180`。启动脚本启用严格端口检查，不会悄悄切换到另一个地址。

### 3. 在 VS Code 中运行

打开命令面板 `Ctrl+Shift+P`，选择“任务：运行任务”，然后选择：

- `AgentFlow: 全部启动`
- `AgentFlow: 后端测试`
- `AgentFlow: 前端 Lint`
- `AgentFlow: 前端构建`

项目已固定使用 `.venv` Python解释器。首次打开时可安装工作区推荐的Python、Pylance和ESLint扩展。

## 测试和构建

```powershell
python -m pytest -q
cd frontend
pnpm run build
```

三类复杂场景各重复 3 次的隔离 Mock 稳定性基准：

```powershell
cd D:\agent_program
python scripts\run_mock_benchmark.py
```

该脚本使用临时 SQLite 数据库，不会污染页面任务，也不会消耗 API 余额。结果写入 `docs/mock-benchmark-report.md` 和 `docs/mock-benchmark-results.json`。

真实 DeepSeek 回归测试（会消耗API额度）：

```powershell
python -m scripts.real_workflow_smoke
python -m scripts.real_knowledge_smoke
python -m scripts.real_benchmark
python -m scripts.real_benchmark_suite analysis
python -m scripts.real_benchmark_suite integrity
```

三类真实任务的对比结果与限制见 `docs/benchmark-suite-report.md`，结构化原始指标见 `docs/benchmark-suite-results.json`。

自动化测试默认使用 Mock LLM，不会产生 API 费用。Mock 模式第一轮返回 72 分并触发返工，第二轮返回 88 分，用于稳定演示 Self-Loop。

## 主要接口

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 服务与模型模式状态 |
| `GET/POST /api/agents` | Agent 查询和创建 |
| `PUT/DELETE /api/agents/{id}` | Agent 更新和删除 |
| `GET/POST /api/workflows` | 工作流查询和创建 |
| `PUT /api/workflows/{id}` | 工作流版本更新 |
| `POST /api/dispatch/recommend` | 按任务特征动态推荐 Agent |
| `GET/POST /api/knowledge` | 知识资料查询和新增 |
| `POST /api/knowledge/search` | 独立检索测试 |
| `GET/DELETE /api/knowledge/{id}` | 资料预览和删除 |
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
- 本地知识库支持 Markdown/TXT 中文分词、分段评分和来源元数据；当前未引入大型向量数据库，适合比赛原型和小型资料集。
- 单机 SQLite 适合比赛原型；生产集群需迁移到 PostgreSQL 和任务队列。

