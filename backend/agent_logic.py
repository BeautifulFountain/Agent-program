from __future__ import annotations

import json
from dataclasses import dataclass

from backend.tools import CalculatorTool, LocalKnowledgeTool


@dataclass(frozen=True)
class AgentProtocol:
    objective: str
    input_contract: str
    output_contract: str
    checks: tuple[str, ...]


PROTOCOLS: dict[str, AgentProtocol] = {
    "requirements": AgentProtocol(
        "把宽泛任务转化为可确认、可验收的研究需求。",
        "读取原始任务，不假设用户未提供的范围、样本或数据来源。",
        "必须包含：问题定义、研究范围、约束、交付标准、待人工确认问题。最后追加一个```approval_options代码块，内容为JSON数组；每项包含id、question、type(single/multiple)、options字符串数组，提供2至4个可直接勾选的合理选项。",
        ("显式列出歧义", "不得伪造数据", "确认项必须可由用户直接回答"),
    ),
    "planner": AgentProtocol(
        "把已确认需求拆成带依赖、产物和验收条件的执行计划。",
        "必须使用人工确认意见与需求分析结果。",
        "输出任务清单；每项包含负责人、输入、产物、依赖、验收条件和风险。",
        ("依赖无环", "可并行任务需明确标记", "每项任务必须可验证"),
    ),
    "literature": AgentProtocol(
        "结合本地知识库证据形成可追溯的文献与知识综述。",
        "读取研究计划和检索工具返回的资料片段。",
        "输出证据表、共识、分歧、研究空白、资料局限；引用必须标注来源文件。",
        ("无来源内容标记为待核验", "不得虚构文献", "区分事实与推断"),
    ),
    "analyst": AgentProtocol(
        "设计可复现的数据指标、统计方法和计算步骤。",
        "读取研究计划、样本约束与计算工具结果。",
        "输出指标字典、数据要求、分析步骤、公式/伪代码、结果解释边界。",
        ("变量定义一致", "统计方法与数据类型匹配", "不得把示例数值写成真实结果"),
    ),
    "writer": AgentProtocol(
        "整合全部有效中间成果形成结构完整的研究报告。",
        "只使用前序成果、人工确认意见和已标注证据。",
        "以Markdown输出：摘要、背景、方法、发现、讨论、风险局限、建议、参考来源。",
        ("不得遗漏人工约束", "不得把待核验内容写成确定事实", "章节结论需可追溯"),
    ),
    "fact-checker": AgentProtocol(
        "逐项核验报告的事实、逻辑、来源和约束一致性。",
        "读取报告与所有上游证据。",
        "输出核验表：声明、核验状态、证据、风险级别、修改建议。",
        ("覆盖关键结论", "标出无证据声明", "检查数字和术语前后一致"),
    ),
    "reviewer": AgentProtocol(
        "依据统一量表对完整成果做独立质量评审。",
        "读取报告、核验结果、需求与人工确认意见。",
        "仅输出JSON：score、dimensions、issues、suggestions。dimensions至少含完整性、逻辑性、可验证性、约束符合度。",
        ("总分0到100", "问题必须具体可定位", "建议必须能驱动下一轮返工"),
    ),
}


class AgentLogic:
    def __init__(self) -> None:
        self.knowledge = LocalKnowledgeTool()
        self.calculator = CalculatorTool()

    def prepare(self, agent_id: str, task: str, base_prompt: str) -> tuple[str, list[dict]]:
        protocol = PROTOCOLS.get(agent_id)
        tool_calls: list[dict] = []
        tool_context = ""
        if agent_id == "literature":
            matches = self.knowledge.search(task, limit=5)
            tool_calls.append({"tool": "local_knowledge", "query": task, "result_count": len(matches)})
            tool_context = "\n\n[本地知识库检索结果]\n" + (json.dumps(matches, ensure_ascii=False) if matches else "未检索到匹配资料；必须明确说明资料不足，不得虚构来源。")
        elif agent_id == "analyst":
            threshold_ratio = self.calculator.calculate("80 / 100")
            tool_calls.append({"tool": "calculator", "expression": "80 / 100", "result": threshold_ratio})
            tool_context = f"\n\n[结构化计算工具]\n质量阈值比例={threshold_ratio}。这只是平台参数，不是研究数据；需要真实数值时必须给出公式和数据需求。"
        if not protocol:
            return base_prompt + "\n请严格依据你的角色、能力标签和工具完成任务，并清楚标注假设与局限。", tool_calls
        checks = "；".join(protocol.checks)
        prompt = (
            f"{base_prompt}{tool_context}\n\n"
            f"[本节点专属执行协议]\n目标：{protocol.objective}\n输入规范：{protocol.input_contract}\n"
            f"输出规范：{protocol.output_contract}\n完成前自检：{checks}\n"
            "必须遵守以上协议；不要越权代替其他Agent，也不要省略规定字段。"
        )
        return prompt, tool_calls


agent_logic = AgentLogic()


def extract_approval_options(output: str, task: str) -> list[dict]:
    """Read model-proposed confirmation choices, with safe task-aware fallbacks."""
    marker = "```approval_options"
    if marker in output:
        raw = output.split(marker, 1)[1].split("```", 1)[0].strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                clean = []
                for index, item in enumerate(parsed[:6]):
                    options = [str(value)[:120] for value in item.get("options", [])[:5] if str(value).strip()]
                    if item.get("question") and len(options) >= 2:
                        clean.append({"id": str(item.get("id") or f"q{index + 1}"), "question": str(item["question"])[:160], "type": "multiple" if item.get("type") == "multiple" else "single", "options": options})
                if clean:
                    return clean
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    subject = task[:32].rstrip("，。； ")
    return [
        {"id": "scope", "question": "本次研究对象和范围如何界定？", "type": "single", "options": ["聚焦一个典型群体或单位", "覆盖多个群体并进行对比", "采用公开资料开展宏观研究"]},
        {"id": "indicators", "question": "优先分析哪些维度？（可多选）", "type": "multiple", "options": ["使用或应用现状", "效率与质量", "风险与局限", "改进建议与实施路径"]},
        {"id": "evidence", "question": f"围绕“{subject}”采用什么证据边界？", "type": "single", "options": ["仅使用本地知识库与已提供资料", "允许提出数据采集方案但不虚构结果", "结合公开资料并明确标注待核验来源"]},
    ]
