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


def resolve(coroutine):
    """Resolve endpoint coroutines that do not require an active I/O loop.

    The managed Windows test environment blocks asyncio's internal socketpair,
    so API unit tests deliberately use deterministic, no-I/O collaborators.
    """
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("测试协程执行了未隔离的异步 I/O")
from backend.schemas import (
    AgentCreate,
    AssistantChatRequest,
    DispatchRecommendationRequest,
    KnowledgeDocumentCreate,
    KnowledgeSearchRequest,
)


def test_health_and_seed_data():
    startup()
    health_response = resolve(health())
    assert health_response.data["status"] == "healthy"
    agents_response = resolve(list_agents())
    assert len(agents_response.data) >= 5


def test_create_agent_validation():
    with pytest.raises(ValidationError):
        AgentCreate(name="x", role="r", system_prompt="short")


def test_root_redirects_to_frontend():
    response = resolve(root())
    assert response.status_code == 307
    assert response.headers["location"] == "http://127.0.0.1:5173"


def test_global_assistant_uses_platform_context(monkeypatch):
    from backend.main import llm

    async def fake_complete(*_args, **_kwargs):
        return "平台助手测试回复", 12

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "mock", True)
    startup()
    context = build_assistant_context()
    assert "active_agents" in context
    response = resolve(assistant_chat(AssistantChatRequest(message="当前平台有哪些Agent？", page="/agents")))
    assert response.data["reply"]
    assert response.data["mode"] == "mock"


def test_global_assistant_routes_images_to_vision_model(monkeypatch):
    from backend.main import llm

    async def fake_complete_with_images(_system, _prompt, images):
        assert len(images) == 1
        assert images[0].startswith("data:image/png;base64,")
        return "图片识别测试回复", 18

    monkeypatch.setattr(llm, "complete_with_images", fake_complete_with_images)
    payload = AssistantChatRequest(
        message="这张图片是什么？",
        page="/",
        images=[{"name": "test.png", "data_url": "data:image/png;base64,aGVsbG8="}],
    )
    response = resolve(assistant_chat(payload))
    assert response.data["reply"] == "图片识别测试回复"
    assert response.data["mode"] == "vision"


def test_global_assistant_rejects_too_many_images():
    image = {"name": "test.png", "data_url": "data:image/png;base64,aGVsbG8="}
    with pytest.raises(ValidationError):
        AssistantChatRequest(message="分析图片", images=[image, image, image, image])


def test_knowledge_api_round_trip(tmp_path, monkeypatch):
    from backend.main import agent_logic

    original_root = agent_logic.knowledge.root
    monkeypatch.setattr(agent_logic.knowledge, "root", tmp_path / "knowledge")
    try:
        created = resolve(create_knowledge(KnowledgeDocumentCreate(
            filename="sampling.md",
            title="抽样设计测试资料",
            organization="测试实验室",
            published_at="2026-11-16",
            url="https://example.com/sampling",
            content="# 分层抽样\n\n分层变量、抽样框与各层样本量必须被记录。",
        ))).data
        assert created["title"] == "抽样设计测试资料"
        assert len(resolve(list_knowledge()).data) == 1
        matches = resolve(search_knowledge(KnowledgeSearchRequest(query="分层抽样样本量", limit=5))).data
        assert matches and matches[0]["title"] == "抽样设计测试资料"
        assert resolve(get_knowledge(created["id"])).data["url"] == "https://example.com/sampling"
        assert resolve(delete_knowledge(created["id"])).data["id"] == created["id"]
        assert resolve(list_knowledge()).data == []
    finally:
        monkeypatch.setattr(agent_logic.knowledge, "root", original_root)


def test_dynamic_dispatch_api_uses_task_characteristics():
    startup()
    result = resolve(recommend_dispatch(DispatchRecommendationRequest(
        task="设计高校学生AI使用情况问卷与可复现统计分析方案，明确变量、样本和数据清洗方法"
    ))).data
    assert result["llm_called"] is False
    assert {"requirements", "analyst", "writer", "reviewer"} <= set(result["agent_ids"])
    assert result["reasons"]["analyst"]

