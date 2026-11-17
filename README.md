# AgentFlow 科研多智能体协作平台

AgentFlow 是一个面向科研报告与复杂研究任务的多智能体协作平台。平台将需求分析、任务规划、文献研究、数据分析、报告撰写、事实核验和质量评审组织成可追踪的工作流，并通过动态调度与 Self-Loop 自动返工形成完整闭环。

项目适合作为多 Agent 工程实践、科研辅助系统原型和工作流编排课程项目使用。

## 核心能力

- **Agent 团队定义**：内置需求分析、任务规划、文献研究、数据分析、报告撰写、事实核验和质量评审 7 类 Agent，支持页面管理与版本更新。
- **动态工作流编排**：根据所选 Agent 自动生成依赖关系，支持串行、并行和依赖就绪调度，并提供可视化工作流图。
- **人工确认与任务控制**：需求确认支持自定义意见优先，运行中可暂停、继续、取消，暂停任务可在控制台删除。
- **知识库集成**：支持 Markdown/TXT 批量上传、预览、检索测试、单条与批量删除；展示命中文献和证据片段。
- **外部学术检索**：接入 OpenAlex、Crossref、arXiv，可选接入 Brave Search；检索结果去重后自动收录到本地知识库。
- **结果验证与反馈优化**：事实核验重新读取原始证据，质量评审输出结构化评分；低于阈值时按评审意见触发定向返工。
- **交付指标**：展示质量评分、引用覆盖率、约束满足率、Self-Loop 次数、Token 和执行耗时。
- **专业报告导出**：最终成果可下载 Markdown 与 Word，Word 按研究报告结构排版。
- **全局智能伙伴**：支持日常对话、平台状态问答、任务协助，以及粘贴/选择图片后调用兼容视觉模型理解图片。
- **完整审计记录**：SQLite 保存工作流快照、节点输入输出、工具调用、证据、评分、Token、耗时和异常信息。

## 工作流程

```text
需求分析 → 人工确认 → 任务规划
                     ├─ 文献研究 ─┐
                     └─ 数据分析 ─┤（可并行）
                                  ↓
                              报告撰写
                                  ↓
                              事实核验
                                  ↓
                              质量评审
                         达标 ────┴──── 未达标
                          ↓                 ↓
                       最终验收       按反馈定向返工
```

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 19、TypeScript、Vite、React Flow |
| 后端 | Python 3.11+、FastAPI、Pydantic |
| 模型 | OpenAI 兼容接口，默认配置为 DeepSeek Chat |
| 存储 | SQLite、本地 Markdown/TXT 知识库 |
| 检索 | 本地分词与分段召回、OpenAlex、Crossref、arXiv、可选 Brave Search |
| 导出 | python-docx、Markdown |

更详细的模块关系见 [系统架构](docs/architecture.md)。

## 快速部署

### 方式一：Docker Compose（推荐）

需要安装 Docker Desktop 或 Docker Engine + Compose。

```bash
git clone https://github.com/BeautifulFountain/Agent-program.git
cd Agent-program
cp .env.example .env
```

编辑 `.env`，至少配置真实模型密钥并关闭 Mock：

```env
LLM_API_KEY=你的模型密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_MOCK=false
```

启动：

```bash
docker compose up -d --build
```

访问平台 <http://127.0.0.1:5173>，API 文档位于 <http://127.0.0.1:8000/docs>。停止服务使用 `docker compose down`。数据库和动态收录的外部知识资料保存在 Docker 命名卷中，重新构建镜像不会丢失。

### 方式二：本地开发运行

需要 Python 3.11+、Node.js 20+ 和 pnpm 9+。

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\start-backend.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

新开终端启动前端：

```bash
cd frontend
pnpm install
pnpm dev
```

访问 <http://127.0.0.1:5173>。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | 公开部署建议设为 `production` |
| `DATABASE_PATH` | `agentflow.db` | SQLite 数据库路径 |
| `LLM_API_KEY` | 空 | OpenAI 兼容模型密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | 文本模型接口地址 |
| `LLM_MODEL` | `deepseek-chat` | 文本模型名称 |
| `LLM_MOCK` | `true` | 是否使用演示模型；真实运行设为 `false` |
| `VISION_API_KEY` | 空 | 可选视觉模型密钥；为空时复用文本密钥 |
| `VISION_BASE_URL` | 空 | 可选视觉模型地址；为空时复用文本地址 |
| `VISION_MODEL` | 空 | 支持 OpenAI `image_url` 消息的视觉模型 |
| `QUALITY_THRESHOLD` | `80` | 质量评审通过阈值 |
| `MAX_LOOP_COUNT` | `3` | 自动返工最大轮数 |
| `EXTERNAL_SEARCH_ENABLED` | `true` | 是否开启外部知识检索 |
| `EXTERNAL_SEARCH_LIMIT` | `6` | 每个外部来源的结果上限 |
| `OPENALEX_API_KEY` | 空 | 可选 OpenAlex API Key |
| `CROSSREF_MAILTO` | 空 | 建议填写 Crossref 联系邮箱 |
| `BRAVE_SEARCH_API_KEY` | 空 | 可选通用网页搜索密钥 |

OpenAlex、Crossref 和 arXiv 无密钥也能进行基础查询。通用网页检索需要 Brave Search Key。智能伙伴单次最多接收 3 张图片，每张不超过 5MB；未配置 `VISION_MODEL` 时会明确提示，不会伪造识别结果。

## 项目目录

```text
agentflow/
├─ backend/                 FastAPI、调度引擎、Agent 与知识检索
├─ frontend/                React 前端
├─ knowledge/               内置和动态收录的知识资料
├─ docs/                    架构、演示和项目说明
├─ scripts/                 知识库扩充与真实模型验收脚本
├─ tests/                   后端自动化测试
├─ .env.example             环境变量模板
├─ docker-compose.yml       容器化部署入口
├─ Dockerfile               后端镜像
└─ requirements.txt         Python 依赖
```

## 验证项目

自动化测试不会调用真实模型，不消耗模型额度：

```bash
python -m pytest -q
cd frontend
pnpm lint
pnpm build
```

固定演示任务：

> 撰写一份约 5000 字的科研方法报告，分析大语言模型在文献数据库检索、主题归纳、研究空白识别和综述写作中的应用价值与局限，并提出一套可复现的人机协作文献综述流程。要求说明检索策略、来源筛选、引用核验、幻觉控制和人工复核机制，引用可核验的经典综述与学术资料。

真实模型验收会产生 API 费用：

```bash
python scripts/run_fixed_demo.py
```

## 主要接口

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 服务、模型和知识库状态 |
| `GET/POST /api/agents` | Agent 查询和创建 |
| `PUT/DELETE /api/agents/{id}` | Agent 更新和删除 |
| `GET/POST /api/workflows` | 工作流查询和创建 |
| `POST /api/dispatch/recommend` | 动态推荐 Agent |
| `GET/POST /api/knowledge` | 知识资料查询和新增 |
| `POST /api/knowledge/search` | 独立检索测试 |
| `GET/DELETE /api/knowledge/{id}` | 资料预览和删除 |
| `POST /api/runs` | 创建任务并启动调度 |
| `GET /api/runs/{id}` | 获取完整运行快照 |
| `POST /api/runs/{id}/pause` | 暂停任务 |
| `POST /api/runs/{id}/resume` | 继续任务 |
| `POST /api/runs/{id}/cancel` | 取消任务 |
| `GET /api/runs/{id}/events` | SSE 运行事件 |
| `GET /api/runs/{id}/report.docx` | 下载 Word 报告 |
| `POST /api/assistant/chat` | 智能伙伴问答与图片理解 |

标准接口返回 `data`、`error_code`、`message` 和 `trace_id`。

## 数据、安全与边界

- `.env`、数据库、虚拟环境、依赖目录和构建产物均被 Git 忽略；模型密钥只从环境变量读取。
- 外部资料按 DOI 或 URL 去重，保留来源、作者、时间、链接和证据片段。
- 生成内容仅供辅助研究，重要结论与引用必须人工复核。
- 工作流页面支持展示运行图和节点状态，目前不提供任意拖拽后的持久化重排。
- 本地检索采用轻量分词与分段召回，尚未集成专用向量数据库。
- SQLite 适合演示和中小规模单实例部署；多实例部署建议迁移 PostgreSQL 与任务队列。
- 页面新增 Agent 可参与注册和推荐；定制完整执行逻辑仍需增加后端处理器或工具。

安全问题参阅 [SECURITY.md](SECURITY.md)，参与开发参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目采用 [MIT License](LICENSE)。
