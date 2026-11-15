import asyncio

import pytest
from pydantic import ValidationError

from backend.main import health, list_agents, startup
from backend.schemas import AgentCreate


def test_health_and_seed_data():
    startup()
    health_response = asyncio.run(health())
    assert health_response.data["status"] == "healthy"
    agents_response = asyncio.run(list_agents())
    assert len(agents_response.data) >= 5


def test_create_agent_validation():
    with pytest.raises(ValidationError):
        AgentCreate(name="x", role="r", system_prompt="short")

