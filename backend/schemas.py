from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiResponse(BaseModel):
    data: Any = None
    error_code: str | None = None
    message: str = "ok"
    trace_id: str = Field(default_factory=lambda: uuid4().hex)


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: str = Field(min_length=2, max_length=120)
    system_prompt: str = Field(min_length=10)
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    model: str = "deepseek-chat"
    status: Literal["active", "disabled"] = "active"


class Agent(AgentCreate):
    id: str
    version: int = 1
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class WorkflowNode(BaseModel):
    id: str
    label: str
    agent_id: str
    kind: Literal["agent", "validator"] = "agent"
    dependencies: list[str] = Field(default_factory=list)
    retry_limit: int = Field(default=1, ge=0, le=5)
    timeout_seconds: int = Field(default=90, ge=5, le=600)
    requires_approval: bool = False
    position: dict[str, float] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = ""
    nodes: list[WorkflowNode]
    quality_threshold: int = Field(default=80, ge=0, le=100)
    max_loop_count: int = Field(default=3, ge=0, le=10)


class Workflow(WorkflowCreate):
    id: str
    version: int = 1
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class RunCreate(BaseModel):
    task: str = Field(min_length=10, max_length=6000)
    workflow_id: str = "research-demo"
    agent_ids: list[str] = Field(default_factory=list)
    output_format: Literal["markdown", "document"] = "markdown"


class ApprovalRequest(BaseModel):
    feedback: str = Field(min_length=2, max_length=4000)


class RunSummary(BaseModel):
    id: str
    task: str
    workflow_id: str
    status: str
    progress: int = 0
    score: int | None = None
    loop_count: int = 0
    token_usage: int = 0
    started_at: str
    finished_at: str | None = None

