from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

from backend.config import settings
from backend.database import db
from backend.engine import run_manager
from backend.llm import llm
from backend.schemas import Agent, AgentCreate, ApiResponse, RunCreate, Workflow, WorkflowCreate, utc_now
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


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="http://127.0.0.1:5173", status_code=307)


@app.get("/api/health", response_model=ApiResponse)
async def health() -> ApiResponse:
    return ok({"status": "healthy", "environment": settings.app_env, "llm_mode": "mock" if llm.mock else "deepseek"})


@app.get("/api/agents", response_model=ApiResponse)
async def list_agents() -> ApiResponse:
    return ok(db.list("agents"))


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
    return ok(db.list("runs"))


@app.post("/api/runs", response_model=ApiResponse, status_code=202)
async def create_run(payload: RunCreate) -> ApiResponse:
    workflow = db.get("workflows", payload.workflow_id)
    if not workflow:
        raise HTTPException(404, "工作流不存在")
    return ok(run_manager.create(payload.task, workflow), "任务已进入调度队列")


@app.get("/api/runs/{run_id}", response_model=ApiResponse)
async def get_run(run_id: str) -> ApiResponse:
    run = db.get("runs", run_id)
    if not run:
        raise HTTPException(404, "任务不存在")
    return ok(run)


@app.post("/api/runs/{run_id}/cancel", response_model=ApiResponse)
async def cancel_run(run_id: str) -> ApiResponse:
    if not db.get("runs", run_id):
        raise HTTPException(404, "任务不存在")
    return ok({"cancelled": run_manager.cancel(run_id)}, "取消请求已提交")


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
            if run and run["status"] in {"completed", "failed", "cancelled", "needs_review"} and not events:
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

