from backend.routing import recommend_agents


AVAILABLE = {"requirements", "planner", "literature", "analyst", "writer", "fact-checker", "reviewer"}


def test_statistics_task_skips_unneeded_literature_agent():
    result = recommend_agents("设计调查数据统计方案，明确变量、样本和计算方法", AVAILABLE)
    assert result["agent_ids"] == ["requirements", "planner", "analyst", "writer", "reviewer"]
    assert result["llm_called"] is False


def test_policy_risk_report_uses_evidence_and_fact_checking():
    result = recommend_agents("撰写高校人工智能政策风险报告并列出法规来源", AVAILABLE)
    assert {"literature", "fact-checker", "writer", "reviewer"} <= set(result["agent_ids"])


def test_simple_writing_keeps_only_required_agents():
    result = recommend_agents("撰写一份简短的课程说明文字", AVAILABLE)
    assert result["agent_ids"] == ["requirements", "writer", "reviewer"]
