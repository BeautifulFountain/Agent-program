import asyncio

import pytest
from pydantic import ValidationError

from backend.main import (
    assistant_chat,
    build_assistant_context,
    create_knowledge,
    delete_knowledge,
    get_knowledge,
    health,
    list_agents,
    list_knowledge,
    recommend_dispatch,
    root,
    search_knowledge,
    startup,
)
from backend.schemas import (
    AgentCreate,
    AssistantChatRequest,
    DispatchRecommendationRequest,
    KnowledgeDocumentCreate,
    KnowledgeSearchRequest,
)


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


def test_knowledge_api_round_trip(tmp_path, monkeypatch):
    from backend.main import agent_logic

    original_root = agent_logic.knowledge.root
    monkeypatch.setattr(agent_logic.knowledge, "root", tmp_path / "knowledge")
    try:
        created = asyncio.run(create_knowledge(KnowledgeDocumentCreate(
            filename="sampling.md",
            title="抽样设计测试资料",
            organization="测试实验室",
            published_at="2026-11-16",
            url="https://example.com/sampling",
            content="# 分层抽样\n\n分层变量、抽样框与各层样本量必须被记录。",
        ))).data
        assert created["title"] == "抽样设计测试资料"
        assert len(asyncio.run(list_knowledge()).data) == 1
        matches = asyncio.run(search_knowledge(KnowledgeSearchRequest(query="分层抽样样本量", limit=5))).data
        assert matches and matches[0]["title"] == "抽样设计测试资料"
        assert asyncio.run(get_knowledge(created["id"])).data["url"] == "https://example.com/sampling"
        assert asyncio.run(delete_knowledge(created["id"])).data["id"] == created["id"]
        assert asyncio.run(list_knowledge()).data == []
    finally:
        monkeypatch.setattr(agent_logic.knowledge, "root", original_root)


def test_dynamic_dispatch_api_uses_task_characteristics():
    startup()
    result = asyncio.run(recommend_dispatch(DispatchRecommendationRequest(
        task="设计高校学生AI使用情况问卷与可复现统计分析方案，明确变量、样本和数据清洗方法"
    ))).data
    assert result["llm_called"] is False
    assert {"requirements", "analyst", "writer", "reviewer"} <= set(result["agent_ids"])
    assert result["reasons"]["analyst"]

