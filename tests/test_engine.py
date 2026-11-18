import asyncio
import sys

import pytest

from backend.database import Database, db
from backend.engine import automatic_rework_required, clean_report_output, enforce_deliverable_validation, evaluate_deliverable, normalize_validation, rework_agent_ids, run_manager, select_best_result
from backend.agent_logic import agent_logic, extract_approval_options
from backend.schemas import WorkflowCreate, WorkflowNode
from backend.seed import seed_defaults
from backend.tools import CalculatorTool, LocalKnowledgeTool
from backend.report_export import build_report_docx
from backend.external_knowledge import ExternalKnowledgeService, ExternalRecord, _openalex_abstract


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


def test_chinese_knowledge_retrieval_returns_chunk_metadata(tmp_path):
    (tmp_path / "policy.md").write_text(
        "---\ntitle: 数据安全政策\norganization: 测试机构\npublished_at: 2026-01-01\nurl: https://example.com/policy\n---\n\n# 数据分类分级\n科研数据应分类分级并进行访问控制。",
        encoding="utf-8",
    )
    result = LocalKnowledgeTool(str(tmp_path)).search("高校科研数据安全与分类分级", limit=3)
    assert result
    assert result[0]["title"] == "数据安全政策"
    assert result[0]["url"] == "https://example.com/policy"
    assert "分类分级" in result[0]["snippet"]


def test_knowledge_documents_can_be_added_previewed_searched_and_deleted(tmp_path):
    tool = LocalKnowledgeTool(str(tmp_path / "knowledge"))
    created = tool.add_document(
        "research-note.md",
        "# 研究方法\n\n分层抽样应记录分层变量、抽样框和各层样本量。",
        {"title": "抽样方法说明", "organization": "测试实验室", "published_at": "2026-11-16", "url": "https://example.com/method"},
    )
    assert created["title"] == "抽样方法说明"
    documents = tool.list_documents()
    assert len(documents) == 1 and documents[0]["editable"] is True
    assert tool.search("分层抽样和样本量", limit=3)[0]["title"] == "抽样方法说明"
    assert tool.delete_document(created["id"]) is True
    assert tool.list_documents() == []


def test_builtin_knowledge_document_can_be_deleted_from_management(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "protected.md").write_text("# 内置资料\n\n受保护内容", encoding="utf-8")
    tool = LocalKnowledgeTool(str(root))
    document_id = tool.list_documents()[0]["id"]
    assert tool.delete_document(document_id) is True
    assert tool.list_documents() == []


def test_knowledge_retrieval_rejects_unrelated_generic_hit(tmp_path):
    (tmp_path / "policy.md").write_text("# 人工智能治理\n\n人工智能系统需要风险管理。", encoding="utf-8")
    tool = LocalKnowledgeTool(str(tmp_path))
    assert tool.search("研究医学影像分割中的卷积神经网络标注一致性和Dice系数", limit=3) == []


def test_external_evidence_is_deduplicated_by_stable_identity(tmp_path):
    tool = LocalKnowledgeTool(str(tmp_path / "knowledge"))
    record = ExternalRecord(
        provider="OpenAlex", title="可追溯科研文献", summary="这是可检索摘要。",
        url="https://doi.org/10.1000/example", doi="10.1000/example", authors="张三", published_at="2026-01-01",
    )
    first, first_created = tool.add_external_document(record.provider, record.identity, record.title, record.markdown(), {"url": record.url, "published_at": record.published_at})
    second, second_created = tool.add_external_document(record.provider, record.identity, record.title, record.markdown(), {"url": record.url, "published_at": record.published_at})
    assert first_created is True and second_created is False
    assert first["id"] == second["id"] and len(tool.list_documents()) == 1
    assert _openalex_abstract({"科研": [1], "智能": [0]}) == "智能 科研"


def test_literature_review_search_focus_and_relevance_filter():
    task = "分析大语言模型在文献数据检索、主题归纳、研究空白识别和综述写作中的价值与局限"
    query = ExternalKnowledgeService.focus_query(task)
    assert "systematic literature review" in query
    assert len(ExternalKnowledgeService.focus_queries(task)) == 2
    assert ExternalKnowledgeService.relevant_to_task(task, "Large language models for systematic literature reviews") is True
    assert ExternalKnowledgeService.relevant_to_task(task, "PRISMA 2020 statement for systematic reviews") is True
    assert ExternalKnowledgeService.relevant_to_task(task, 'Review for "Large language models for literature reviews"') is False
    assert ExternalKnowledgeService.relevant_to_task(task, "大语言模型在文本情感分析中的应用研究") is False
    assert ExternalKnowledgeService.relevant_to_task(task, "AI大模型在景区中的应用研究") is False


def test_generic_search_plan_normalizes_concept_groups():
    task = "研究计算机视觉在工业缺陷检测中的方法"
    searches = ExternalKnowledgeService.normalize_searches({"searches": [{
        "query": "computer vision industrial defect detection review",
        "must_include_groups": [["computer vision", "visual inspection"], ["defect detection", "defect inspection"]],
    }]}, task)
    assert len(searches) == 1
    assert ExternalKnowledgeService.relevant_to_search(
        "Computer vision for industrial defect detection: a review", "", searches[0]
    ) is True
    assert ExternalKnowledgeService.relevant_to_search(
        "Computer vision for medical image segmentation", "", searches[0]
    ) is False


def test_literature_async_prepare_records_external_ingestion(monkeypatch):
    async def fake_plan(_: str):
        return ([{"query": "artificial intelligence research governance", "must_include_groups": []}], 10)
    async def fake_search(_: str, _searches):
        return {"providers": ["OpenAlex"], "found": 2, "imported": [{"id": "x", "provider": "OpenAlex", "title": "论文", "url": "https://example.com"}], "duplicates": 1, "errors": []}
    monkeypatch.setattr(agent_logic, "plan_searches", fake_plan)
    monkeypatch.setattr(agent_logic.external, "search_and_ingest", fake_search)
    coroutine = agent_logic.prepare_async("literature", "人工智能科研治理", "基础输入")
    try:
        coroutine.send(None)
    except StopIteration as completed:
        prompt, calls = completed.value
    else:
        raise AssertionError("测试协程执行了未隔离的异步 I/O")
    assert calls[0]["tool"] == "external_knowledge_search"
    assert calls[0]["result_count"] == 1
    assert "新增入库1条" in prompt


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
    assert "可直接交付的科研报告" in prompt
    assert "全文只说明一次" in prompt


def test_requirements_only_asks_unresolved_questions():
    prompt, _ = agent_logic.prepare("requirements", "撰写约5000字科研方法报告，引用可核验学术资料", "基础输入")
    assert "不得重复询问" in prompt
    assert "最多3组" in prompt
    assert "按原要求执行，不增加额外限制" in prompt


def test_literature_forbids_claiming_local_retrieval_gap_is_research_gap():
    prompt, _ = agent_logic.prepare("literature", "高校科研管理合规", "基础输入")
    assert "不得把本地未检出等同于学术研究空白" in prompt
    assert "禁止写成‘研究空白’" in prompt
    assert "引用URL必须逐字复制工具结果" in prompt


def test_methodology_task_keeps_policy_sources_out_of_method_evidence():
    prompt, _ = agent_logic.prepare("literature", "设计数据分析方案，包括变量定义、数据清洗和统计方法", "基础输入")
    assert "政策法规资料只能说明数据处理边界" in prompt
    assert "当前知识库未提供方法学证据" in prompt


def test_fact_checker_and_reviewer_have_feedback_budgets():
    fact_prompt, fact_tools = agent_logic.prepare("fact-checker", "高校科研数据安全治理", "基础输入")
    review_prompt, _ = agent_logic.prepare("reviewer", "研究任务", "基础输入")
    assert "最多6个" in fact_prompt
    assert "不超过1200字" in fact_prompt
    assert "事实核验独立检索结果" in fact_prompt
    assert fact_tools[0]["tool"] == "local_knowledge_recheck"
    assert "分别最多6项" in review_prompt
    assert "沿用与上一轮完全相同的量表" in review_prompt


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


@pytest.mark.skipif(sys.platform == "win32", reason="完整异步集成测试需要允许本地 socketpair 的运行环境")
def test_full_research_loop_applies_delivery_gate():
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
    reviewer_scores = [
        item["score"] for item in result["node_runs"]
        if item["node_id"] == "reviewer" and item.get("score") is not None
    ]
    assert max(reviewer_scores) >= 80
    # The mock reviewer reaches its nominal threshold, but its deliberately short
    # draft has no usable references. The deterministic delivery gate must retain
    # the lower audited score instead of reporting a false pass.
    assert result["score"] == 69
    assert result["validation"]["critical_flags"]["missing_required_deliverable"] is True
    assert result["loop_count"] == result["workflow_snapshot"]["max_loop_count"]
    assert len(result["node_runs"]) >= 18
    assert sum(item["node_id"] == "writer" for item in result["node_runs"]) == result["workflow_snapshot"]["max_loop_count"] + 1
    assert sum(item["node_id"] == "reviewer" for item in result["node_runs"]) == result["workflow_snapshot"]["max_loop_count"] + 1
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


def test_validation_uses_weighted_rubric_when_all_dimensions_are_present():
    result = normalize_validation({
        "score": 10,
        "dimensions": {
            "完整性": 90,
            "逻辑性": 80,
            "可验证性": 70,
            "约束符合度": 100,
            "表达质量与可交付性": 80,
        },
        "critical_flags": {},
    })
    assert result["score"] == 84
    assert result["score_basis"] == "weighted_rubric_v1"
    assert result["critical_flags"] == {
        "fabricated_data": False,
        "unverifiable_core_citations": False,
        "missing_required_deliverable": False,
        "violated_explicit_constraints": False,
    }


def test_validation_applies_critical_score_caps():
    dimensions = {
        "完整性": 95,
        "逻辑性": 95,
        "可验证性": 95,
        "约束符合度": 95,
        "表达质量与可交付性": 95,
    }
    fabricated = normalize_validation({
        "score": 95, "dimensions": dimensions,
        "critical_flags": {"fabricated_data": True},
    })
    constraint_failure = normalize_validation({
        "score": 95, "dimensions": dimensions,
        "critical_flags": {"violated_explicit_constraints": True},
    })
    assert fabricated["score"] == 59
    assert constraint_failure["score"] == 79


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


def test_word_export_contains_only_formal_report_content():
    from io import BytesIO
    from docx import Document

    content = build_report_docx(
        "# 高校科研人工智能应用研究报告\n\n## 摘要\n\n本文分析应用价值与风险。\n\n**关键词：** 人工智能；科研管理\n\n## 一、研究背景\n\n这是报告正文。\n\n## 参考来源\n\n- 科技伦理审查办法（https://example.com/source）",
        "备用标题",
    )
    assert content[:2] == b"PK"
    document = Document(BytesIO(content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "高校科研人工智能应用研究报告" in text
    assert "摘要" in text and "关键词" in text and "参考来源" in text
    assert "工具调用审计" not in text and "执行时间线" not in text
    assert "#" not in text and "**" not in text
    assert all(not "".join(p.text for p in section.header.paragraphs).strip() for section in document.sections)
    footer_xml = "".join(section.footer._element.xml for section in document.sections)
    assert "PAGE" in footer_xml and "NUMPAGES" not in footer_xml
    assert document.paragraphs[0].alignment == 1
    assert "w:pBdr" not in document.paragraphs[0]._p.xml
    abstract_paragraph = next(paragraph for paragraph in document.paragraphs if paragraph.text == "摘要")
    assert abstract_paragraph.alignment == 1


def test_report_cleanup_removes_process_labels():
    value = clean_report_output("# 正式报告（设计稿，未实施，无真实数据）\n\n生成说明：这是模型生成过程。\n\n## 摘要\n\n专业正文。")
    assert "设计稿" not in value and "无真实数据" not in value and "生成说明" not in value
    assert "正式报告" in value and "专业正文" in value


def test_report_cleanup_removes_fake_reference_narrative():
    value = clean_report_output(
        "# 正式报告\n\n## 结论\n\n研究结论。\n\n## 参考来源\n\n"
        "本报告的引用策略遵循人工确认意见。后续版本将补充代表性文献。"
    )
    assert "参考来源" not in value
    assert "后续版本" not in value


def test_report_cleanup_keeps_only_numbered_formal_references():
    value = clean_report_output(
        "# 报告\n\n## 参考来源\n\n1. Author. Valid paper[J]. Journal, 2024. https://example.com/a\n"
        "- 本报告仅依据摘要信息，后续版本将继续核验。"
    )
    assert "## 参考文献" in value
    assert "[1] Author. Valid paper[J]. Journal, 2024. https://example.com/a" in value
    assert "摘要信息" not in value


def test_deterministic_gate_caps_zero_citation_report():
    run = {"task": "研究任务", "node_runs": [{"tool_calls": [{"tool": "local_knowledge", "results": [{
        "source": "a.md", "chunk": "1", "title": "资料A", "url": "https://example.com/a"
    }]}]}]}
    validation = {"score": 92, "issues": [], "suggestions": [], "critical_flags": {}}
    result = enforce_deliverable_validation(run, validation, "# 报告\n\n## 摘要\n\n没有引用。")
    assert result["score"] == 69
    assert result["critical_flags"]["unverifiable_core_citations"] is True
    assert any("未实际使用" in item for item in result["issues"])


def test_review_feedback_routes_to_responsible_upstream_agents():
    validation = {
        "issues": ["引用来源与主题不相关", "统计方法和样本定义不清"],
        "suggestions": ["重新检索文献并补充变量定义"],
    }
    selected = rework_agent_ids(validation, {"planner", "literature", "analyst", "writer"})
    assert "literature" in selected
    assert "analyst" in selected


def test_automatic_rework_runs_until_threshold_or_loop_budget_is_exhausted():
    assert automatic_rework_required(69, 80, 0, 3) is True
    assert automatic_rework_required(69, 80, 1, 3) is True
    assert automatic_rework_required(60, 80, 2, 3) is True
    assert automatic_rework_required(60, 80, 3, 3) is False
    assert automatic_rework_required(80, 80, 1, 3) is False


def test_delivery_metrics_are_deterministic():
    run = {
        "task": "撰写一份约1000字报告，覆盖数据安全与风险",
        "final_output": "# 数据安全研究报告\n\n## 摘要\n\n" + "数据安全与风险分析。" * 100 + "\n来源：https://example.com/a",
        "node_runs": [{"tool_calls": [{"tool": "local_knowledge", "results": [{
            "source": "a.md", "chunk": "1", "title": "资料A", "url": "https://example.com/a"
        }]}]}],
    }
    metrics = evaluate_deliverable(run)
    assert metrics["citation_coverage"] == {"cited": 1, "retrieved": 1, "percent": 100}
    assert metrics["constraint_compliance"]["total"] >= 5
    assert metrics["constraint_compliance"]["percent"] > 0



