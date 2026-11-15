import asyncio

import pytest

from backend.database import Database, db
from backend.engine import normalize_validation, run_manager
from backend.schemas import WorkflowCreate, WorkflowNode
from backend.seed import seed_defaults
from backend.tools import CalculatorTool


def test_workflow_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        WorkflowCreate(name="测试", nodes=[], quality_threshold=120)


def test_parallel_nodes_share_dependency():
    workflow = WorkflowCreate(name="并行测试", nodes=[
        WorkflowNode(id="plan", label="规划", agent_id="planner"),
        WorkflowNode(id="a", label="文献", agent_id="literature", dependencies=["plan"]),
        WorkflowNode(id="b", label="数据", agent_id="analyst", dependencies=["plan"]),
    ])
    ready_after_plan = {node.id for node in workflow.nodes if set(node.dependencies) <= {"plan"}}
    assert {"a", "b"} <= ready_after_plan


def test_calculator_is_safe_and_works():
    tool = CalculatorTool()
    assert tool.calculate("(12 + 8) * 2") == 40
    with pytest.raises(ValueError):
        tool.calculate("__import__('os').system('whoami')")


def test_database_round_trip(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    database.initialize()
    database.upsert("agents", "a1", {"id": "a1", "name": "agent", "created_at": "1", "updated_at": "1"})
    assert database.get("agents", "a1")["name"] == "agent"


def test_full_research_loop_reaches_threshold():
    async def scenario():
        db.initialize()
        seed_defaults(db)
        workflow = db.get("workflows", "research-demo")
        run = run_manager.create("分析人工智能辅助高校科研管理的应用价值与风险，并形成研究报告", workflow)
        await run_manager.tasks[run["id"]]
        return db.get("runs", run["id"])

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert result["score"] >= 80
    assert result["loop_count"] == 1
    assert len(result["node_runs"]) == 10


def test_validation_normalizes_deepseek_field_variants():
    result = normalize_validation({
        "score": 82,
        "dimension_scores": {"完整性": 85},
        "issues": ["缺少来源"],
        "improvement_suggestions": ["补充引用"],
    })
    assert result == {
        "score": 82,
        "dimensions": {"完整性": 85},
        "issues": ["缺少来源"],
        "suggestions": ["补充引用"],
    }

