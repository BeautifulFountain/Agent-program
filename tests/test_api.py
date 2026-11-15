import asyncio

import pytest
from pydantic import ValidationError

from backend.main import assistant_chat, build_assistant_context, health, list_agents, root, startup
from backend.schemas import AgentCreate, AssistantChatRequest


def test_health_and_seed_data():
    startup()
    health_response = asyncio.run(health())
    assert health_response.data["status"] == "healthy"
    agents_response = asyncio.run(list_agents())
    assert len(agents_response.data) >= 5


def test_create_agent_validation():
    with pytest.raises(ValidationError):
        AgentCreate(name="x", role="r", system_prompt="short")


def test_root_redirects_to_frontend():
    response = asyncio.run(root())
    assert response.status_code == 307
    assert response.headers["location"] == "http://127.0.0.1:5173"


def test_global_assistant_uses_platform_context():
    startup()
    context = build_assistant_context()
    assert "active_agents" in context
    response = asyncio.run(assistant_chat(AssistantChatRequest(message="当前平台有哪些Agent？", page="/agents")))
    assert response.data["reply"]
    assert response.data["mode"] == "mock"

