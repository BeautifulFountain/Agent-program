from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

from backend.config import settings
from backend.agent_logic import agent_logic, extract_approval_options
from backend.database import db
from backend.engine import run_manager, select_best_result
from backend.llm import llm
from backend.routing import recommend_agents
from backend.schemas import Agent, AgentCreate, ApiResponse, ApprovalRequest, AssistantChatRequest, DispatchRecommendationRequest, FinalReworkRequest, KnowledgeDocumentCreate, KnowledgeSearchRequest, RunCreate, Workflow, WorkflowCreate, utc_now
from backend.seed import seed_defaults

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.initialize()
    seed_defaults(db)
    yield


app = FastAPI(title="AgentFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def startup() -> None:
    """Initialize storage explicitly for scripts and direct tests."""
    db.initialize()
    seed_defaults(db)


def ok(data=None, message="ok") -> ApiResponse:
    return ApiResponse(data=data, message=message)


def build_assistant_context() -> str:
    agents = db.list("agents")
    runs = db.list("runs")
    active = [agent["name"] for agent in agents if agent.get("status") == "active"]
    recent = [{"id": run["id"], "task": run["task"][:100], "status": run["status"], "score": run.get("score"), "progress": run.get("progress"), "loops": run.get("loop_count", 0)} for run in runs[:8]]
    return json.dumps({
        "active_agents": active,
        "agent_count": len(active),
        "run_count": len(runs),
        "recent_runs": recent,
        "workflow": "需求分析与人工确认 → 研究规划 → 文献/数据并行 → 报告撰写 → 事实核验 → 质量评审 → 不达标自动返工",
    }, ensure_ascii=False)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="http://127.0.0.1:5173", status_code=307)


@app.get("/api/health", response_model=ApiResponse)
async def health() -> ApiResponse:
    return ok({"status": "healthy", "environment": settings.app_env, "llm_mode": "mock" if llm.mock else "deepseek"})


@app.get("/api/agents", response_model=ApiResponse)
async def list_agents() -> ApiResponse:
    return ok(db.list("agents"))


@app.post("/api/dispatch/recommend", response_model=ApiResponse)
async def recommend_dispatch(payload: DispatchRecommendationRequest) -> ApiResponse:
    available = {agent["id"] for agent in db.list("agents") if agent.get("status") == "active"}
    return ok(recommend_agents(payload.task, available), "已生成离线动态调度建议")


@app.get("/api/knowledge", response_model=ApiResponse)
async def list_knowledge() -> ApiResponse:
    return ok(agent_logic.knowledge.list_documents())


@app.post("/api/knowledge", response_model=ApiResponse, status_code=201)
async def create_knowledge(payload: KnowledgeDocumentCreate) -> ApiResponse:
    try:
        document = agent_logic.knowledge.add_document(
            payload.filename,
            payload.content,
            {"title": payload.title, "organization": payload.organization, "published_at": payload.published_at, "url": payload.url},
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ok(document, "知识文档已加入本地知识库")


@app.post("/api/knowledge/search", response_model=ApiResponse)
async def search_knowledge(payload: KnowledgeSearchRequest) -> ApiResponse:
    return ok(agent_logic.knowledge.search(payload.query, payload.limit))


@app.get("/api/knowledge/{document_id}", response_model=ApiResponse)
async def get_knowledge(document_id: str) -> ApiResponse:
    try:
        return ok(agent_logic.knowledge.read_document(document_id))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/knowledge/{document_id}", response_model=ApiResponse)
async def delete_knowledge(document_id: str) -> ApiResponse:
    try:
        deleted = agent_logic.knowledge.delete_document(document_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "知识文档不存在")
    return ok({"id": document_id}, "知识文档已删除")


@app.post("/api/agents", response_model=ApiResponse, status_code=201)
async def create_agent(payload: AgentCreate) -> ApiResponse:
    now = utc_now()
    agent = Agent(id=uuid4().hex[:10], **payload.model_dump(), created_at=now, updated_at=now)
    db.upsert("agents", agent.id, agent.model_dump())
    return ok(agent.model_dump(), "Agent已创建")


@app.put("/api/agents/{agent_id}", response_model=ApiResponse)
async def update_agent(agent_id: str, payload: AgentCreate) -> ApiResponse:
    current = db.get("agents", agent_id)
    if not current:
        raise HTTPException(404, "Agent不存在")
    agent = Agent(id=agent_id, version=current["version"] + 1, created_at=current["created_at"], updated_at=utc_now(), **payload.model_dump())
    db.upsert("agents", agent_id, agent.model_dump())
    return ok(agent.model_dump(), "Agent已更新")


@app.delete("/api/agents/{agent_id}", response_model=ApiResponse)
async def delete_agent(agent_id: str) -> ApiResponse:
    for workflow in db.list("workflows"):
        if any(node.get("agent_id") == agent_id for node in workflow.get("nodes", [])):
            raise HTTPException(409, "该Agent仍被工作流使用，请先调整工作流")
    if not db.delete("agents", agent_id):
        raise HTTPException(404, "Agent不存在")
    return ok({"id": agent_id}, "Agent已删除")


@app.get("/api/workflows", response_model=ApiResponse)
async def list_workflows() -> ApiResponse:
    return ok(db.list("workflows"))


@app.get("/api/workflows/{workflow_id}", response_model=ApiResponse)
async def get_workflow(workflow_id: str) -> ApiResponse:
    workflow = db.get("workflows", workflow_id)
    if not workflow:
        raise HTTPException(404, "工作流不存在")
    return ok(workflow)


@app.post("/api/workflows", response_model=ApiResponse, status_code=201)
async def create_workflow(payload: WorkflowCreate) -> ApiResponse:
    workflow = Workflow(id=uuid4().hex[:10], **payload.model_dump())
    db.upsert("workflows", workflow.id, workflow.model_dump())
    return ok(workflow.model_dump(), "工作流已创建")


@app.put("/api/workflows/{workflow_id}", response_model=ApiResponse)
async def update_workflow(workflow_id: str, payload: WorkflowCreate) -> ApiResponse:
    current = db.get("workflows", workflow_id)
    if not current:
        raise HTTPException(404, "工作流不存在")
    workflow = Workflow(id=workflow_id, version=current["version"] + 1, created_at=current["created_at"], updated_at=utc_now(), **payload.model_dump())
    db.upsert("workflows", workflow_id, workflow.model_dump())
    return ok(workflow.model_dump(), "工作流已更新")


@app.get("/api/runs", response_model=ApiResponse)
async def list_runs() -> ApiResponse:
    runs = db.list("runs")
    for run in runs:
        if run.get("status") in {"needs_review", "waiting_final_acceptance"}:
            run["status"] = "completed"
            db.upsert("runs", run["id"], run)
    return ok(runs)


@app.post("/api/runs", response_model=ApiResponse, status_code=202)
async def create_run(payload: RunCreate) -> ApiResponse:
    workflow = db.get("workflows", payload.workflow_id)
    if not workflow:
        raise HTTPException(404, "工作流不存在")
    selected = set(payload.agent_ids)
    if selected:
        required = {"requirements", "writer", "reviewer"}
        missing = required - selected
        if missing:
            raise HTTPException(422, f"缺少必要Agent：{', '.join(sorted(missing))}")
        known = {agent["id"] for agent in db.list("agents") if agent.get("status") == "active"}
        unknown = selected - known
        if unknown:
            raise HTTPException(422, f"Agent不存在或未启用：{', '.join(sorted(unknown))}")
        workflow = deepcopy(workflow)
        workflow["nodes"] = [node for node in workflow["nodes"] if node["agent_id"] in selected]
        existing_agent_ids = {node["agent_id"] for node in workflow["nodes"]}
        extras = [agent for agent in db.list("agents") if agent["id"] in selected - existing_agent_ids]
        for index, agent in enumerate(extras):
            workflow["nodes"].append({
                "id": f"custom-{agent['id']}", "label": agent["name"], "agent_id": agent["id"],
                "kind": "agent", "dependencies": ["requirements"], "retry_limit": 1,
                "timeout_seconds": 90, "requires_approval": False,
                "position": {"x": 500, "y": 420 + index * 120},
            })
        kept = {node["id"] for node in workflow["nodes"]}
        for node in workflow["nodes"]:
            node["dependencies"] = [dep for dep in node["dependencies"] if dep in kept]
            if node["id"] in {"literature", "analyst"} and not node["dependencies"]:
                node["dependencies"] = ["requirements"]
        writer = next(node for node in workflow["nodes"] if node["id"] == "writer")
        contributors = [node["id"] for node in workflow["nodes"] if node["id"] not in {"requirements", "writer", "fact-checker", "reviewer"}]
        writer["dependencies"] = contributors or ["requirements"]
        reviewer = next(node for node in workflow["nodes"] if node["id"] == "reviewer")
        reviewer["dependencies"] = ["fact-checker"] if "fact-checker" in kept else ["writer"]
    return ok(run_manager.create(payload.task, workflow, payload.output_format), "任务已进入调度队列")


@app.get("/api/runs/{run_id}", response_model=ApiResponse)
async def get_run(run_id: str) -> ApiResponse:
    run = db.get("runs", run_id)
    if not run:
        raise HTTPException(404, "任务不存在")
    if run.get("status") == "waiting_approval" and run.get("approval") and not run["approval"].get("options"):
        requirement = next((item for item in reversed(run.get("node_runs", [])) if item.get("node_id") == "requirements"), None)
        run["approval"]["options"] = extract_approval_options((requirement or {}).get("output") or "", run["task"])
        db.upsert("runs", run_id, run)
    if run.get("status") in {"completed", "needs_review"} and select_best_result(run):
        db.upsert("runs", run_id, run)
    if run.get("status") in {"needs_review", "waiting_final_acceptance"}:
        run["status"] = "completed"
        db.upsert("runs", run_id, run)
    return ok(run)


@app.delete("/api/runs/{run_id}", response_model=ApiResponse)
async def delete_run(run_id: str) -> ApiResponse:
    run = db.get("runs", run_id)
    if not run:
        raise HTTPException(404, "任务不存在")
    if run.get("status") in {"queued", "running", "waiting_approval", "reworking"}:
        raise HTTPException(409, "运行中的任务不能删除，请先取消任务")
    run_manager.tasks.pop(run_id, None)
    if not db.delete_run(run_id):
        raise HTTPException(404, "任务不存在")
    return ok({"id": run_id}, "任务及其事件记录已删除")


@app.post("/api/runs/{run_id}/cancel", response_model=ApiResponse)
async def cancel_run(run_id: str) -> ApiResponse:
    if not db.get("runs", run_id):
        raise HTTPException(404, "任务不存在")
    return ok({"cancelled": run_manager.cancel(run_id)}, "取消请求已提交")


@app.post("/api/runs/{run_id}/approve", response_model=ApiResponse)
async def approve_run(run_id: str, payload: ApprovalRequest) -> ApiResponse:
    try:
        run = run_manager.approve(run_id, payload.feedback)
    except ValueError as exc:
        raise HTTPException(409 if db.get("runs", run_id) else 404, str(exc)) from exc
    return ok(run, "人工意见已确认，任务继续执行")


@app.post("/api/runs/{run_id}/request-rework", response_model=ApiResponse)
async def request_run_rework(run_id: str, payload: FinalReworkRequest) -> ApiResponse:
    try:
        run = run_manager.request_final_rework(run_id, payload.feedback, payload.agent_ids)
    except ValueError as exc:
        raise HTTPException(409 if db.get("runs", run_id) else 404, str(exc)) from exc
    return ok(run, "人工修改意见已提交，任务开始定向返工")
@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request):
    if not db.get("runs", run_id):
        raise HTTPException(404, "任务不存在")

    async def generate():
        last_id = 0
        while not await request.is_disconnected():
            events = db.events(run_id, last_id)
            for event in events:
                last_id = event["event_id"]
                yield f"id: {last_id}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            run = db.get("runs", run_id)
            if run and run["status"] in {"completed", "failed", "cancelled", "needs_review", "waiting_final_acceptance"} and not events:
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/llm/test", response_model=ApiResponse)
async def test_llm() -> ApiResponse:
    if settings.app_env == "production":
        raise HTTPException(404, "接口不存在")
    text, tokens = await llm.complete("你是连通性测试助手。", "请仅回复：连接成功")
    return ok({"reply": text, "tokens": tokens, "mode": "mock" if llm.mock else "deepseek"})


@app.post("/api/assistant/chat", response_model=ApiResponse)
async def assistant_chat(payload: AssistantChatRequest) -> ApiResponse:
    history = "\n".join(f"{item.role}: {item.content}" for item in payload.history[-8:])
    prompt = (
        f"当前页面：{payload.page}\n平台实时摘要：{build_assistant_context()}\n"
        f"最近对话：\n{history or '无'}\n用户问题：{payload.message}\n"
        "先判断用户是在普通聊天，还是询问AgentFlow平台。普通聊天自然回答，不要强行提及平台；"
        "涉及平台时再使用实时摘要，引用任务使用任务名称或ID。请直接给出清晰、有帮助的中文回答，无法确定的信息要明确说明。"
    )
    system = (
        "你是友好、可靠的通用AI智能伙伴，同时也是AgentFlow平台助手。你可以进行日常对话、知识问答、学习辅导、"
        "写作润色、头脑风暴和代码解释；当用户询问平台时，你熟悉Agent、任务、工作流、人工确认、质量评审和自动返工。"
        "你能解释全局状态、指导用户操作、帮助拆解科研任务，但不能声称已执行未发生的操作，不能泄露密钥，"
        "也不能绕过用户确认直接删除任务或启动高成本流程。"
    )
    reply, tokens = await llm.complete(system, prompt)
    return ok({"reply": reply, "tokens": tokens, "mode": "mock" if llm.mock else "deepseek"})

