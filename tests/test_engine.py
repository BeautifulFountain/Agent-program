import asyncio

import pytest

from backend.database import Database, db
from backend.engine import normalize_validation, run_manager, select_best_result
from backend.agent_logic import agent_logic, extract_approval_options
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


def test_agents_have_distinct_protocols_and_tools():
    requirements_prompt, requirement_tools = agent_logic.prepare("requirements", "统计大学生使用AI的情况", "基础输入")
    analyst_prompt, analyst_tools = agent_logic.prepare("analyst", "统计大学生使用AI的情况", "基础输入")
    assert "approval_options" in requirements_prompt
    assert "指标字典" in analyst_prompt
    assert requirement_tools == []
    assert analyst_tools[0]["tool"] == "calculator"


def test_writer_enforces_requested_length_and_revision_rules():
    prompt, _ = agent_logic.prepare("writer", "撰写一份约1000字研究简报", "基础输入")
    assert "900至1100字" in prompt
    assert "只输出最终Markdown正文" in prompt
    assert "逐条落实评审意见" in prompt


def test_approval_options_parse_and_fallback():
    output = '```approval_options\n[{"id":"scope","question":"范围？","type":"single","options":["本校","全国"]}]\n```'
    parsed = extract_approval_options(output, "测试任务")
    assert parsed[0]["options"] == ["本校", "全国"]
    assert len(extract_approval_options("普通文本", "测试任务")) >= 3


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
        waiting = db.get("runs", run["id"])
        assert waiting["status"] == "waiting_approval"
        assert len(waiting["node_runs"]) == 1
        assert len(waiting["approval"]["options"]) >= 3
        run_manager.approve(run["id"], "研究范围限定为本科生，统计使用率、频率和主要场景。")
        await run_manager.tasks[run["id"]]
        return db.get("runs", run["id"])

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert result["score"] >= 80
    assert result["loop_count"] == 1
    assert len(result["node_runs"]) == 10
    assert result["approval"]["status"] == "approved"
    assert "本科生" in result["human_feedback"]


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
        "dimension_comments": {},
        "issues": ["缺少来源"],
        "suggestions": ["补充引用"],
    }


def test_validation_normalizes_dimension_objects():
    result = normalize_validation({
        "score": 72,
        "dimensions": {"事实准确性": {"score": 68, "comment": "引用仍需核对"}},
    })
    assert result["dimensions"] == {"事实准确性": 68}
    assert result["dimension_comments"] == {"事实准确性": "引用仍需核对"}


def test_validation_normalizes_structured_issues():
    result = normalize_validation({
        "score": 75,
        "issues": [{
            "id": "R1",
            "severity": "中风险",
            "description": "缺少来源",
            "suggestion": "补充引用",
        }],
    })
    assert result["issues"] == ["[中风险] 缺少来源；建议：补充引用"]


def test_validation_normalizes_deepseek_problem_and_action_fields():
    result = normalize_validation({
        "score": 88,
        "issues": [{"location": "背景第3句", "problem": "缺少法规名称", "severity": "中"}],
        "suggestions": [{"target": "背景第3句", "action": "补充可核验法规名称"}],
    })
    assert result["issues"] == ["[中] 背景第3句：缺少法规名称"]
    assert result["suggestions"] == ["背景第3句：补充可核验法规名称"]


def test_best_result_selects_matching_writer_version():
    run = {
        "score": 62,
        "final_output": "第四版报告",
        "node_runs": [
            {"node_id": "writer", "status": "completed", "loop": 0, "output": "第一版报告"},
            {"node_id": "reviewer", "status": "completed", "loop": 0, "output": '{"score":78,"dimensions":{"完整性":80}}'},
            {"node_id": "writer", "status": "completed", "loop": 3, "output": "第四版报告"},
            {"node_id": "reviewer", "status": "completed", "loop": 3, "output": '{"score":62,"dimensions":{"完整性":60}}'},
        ],
    }
    assert select_best_result(run) is True
    assert run["score"] == 78
    assert run["latest_score"] == 62
    assert run["selected_loop"] == 0
    assert run["final_output"] == "第一版报告"

