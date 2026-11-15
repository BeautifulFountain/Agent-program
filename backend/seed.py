from __future__ import annotations

from backend.config import settings
from backend.database import Database
from backend.schemas import Agent, Workflow, WorkflowNode


AGENTS = [
    ("requirements", "需求分析 Agent", "研究需求分析师", "你是需求分析师。澄清研究问题、范围、约束与交付标准。", ["需求理解", "问题定义"]),
    ("planner", "任务规划 Agent", "研究项目经理", "你是研究项目经理。将复杂任务拆分为可执行、可验证的研究计划。", ["任务规划", "依赖分析"]),
    ("literature", "文献研究 Agent", "文献研究员", "你是文献研究员。总结已有知识、证据脉络与研究空白，明确资料局限。", ["文献检索", "知识归纳"]),
    ("analyst", "数据分析 Agent", "数据分析师", "你是数据分析师。定义指标、分析框架与可复现的计算路径。", ["数据分析", "指标设计"]),
    ("writer", "报告撰写 Agent", "学术写作专家", "你是学术写作专家。整合前序成果，形成结构严谨、表达清晰的研究报告。", ["报告生成", "内容整合"]),
    ("fact-checker", "事实核验 Agent", "事实核验员", "你是事实核验员。检查事实、逻辑、来源与论证一致性，指出风险。", ["事实核验", "逻辑检查"]),
    ("reviewer", "质量评审 Agent", "质量评审专家", "你是质量评审专家。以JSON输出0到100分、维度评分、问题与改进建议。", ["质量评审", "结果验证"]),
]


def seed_defaults(db: Database) -> None:
    if not db.list("agents"):
        for agent_id, name, role, prompt, capabilities in AGENTS:
            agent = Agent(
                id=agent_id, name=name, role=role, system_prompt=prompt,
                capabilities=capabilities, tools=["local_knowledge"], model=settings.llm_model,
            )
            db.upsert("agents", agent.id, agent.model_dump())
    if not db.get("workflows", "research-demo"):
        positions = [(40, 180), (260, 180), (500, 80), (500, 280), (740, 180), (980, 100), (980, 270)]
        specs = [
            ("requirements", []), ("planner", ["requirements"]),
            ("literature", ["planner"]), ("analyst", ["planner"]),
            ("writer", ["literature", "analyst"]), ("fact-checker", ["writer"]),
            ("reviewer", ["fact-checker"]),
        ]
        nodes = [WorkflowNode(
            id=key, label=next(a[1] for a in AGENTS if a[0] == key), agent_id=key,
            kind="validator" if key == "reviewer" else "agent", dependencies=deps,
            position={"x": positions[i][0], "y": positions[i][1]},
        ) for i, (key, deps) in enumerate(specs)]
        workflow = Workflow(
            id="research-demo", name="科研任务协作与质量闭环", description="规划、并行研究、撰写、核验与自动返工",
            nodes=nodes, quality_threshold=settings.quality_threshold, max_loop_count=settings.max_loop_count,
        )
        db.upsert("workflows", workflow.id, workflow.model_dump())

