from __future__ import annotations

import json
import re
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
        "输出证据表、共识、分歧、当前检索资料未覆盖的问题、资料局限；每条引用必须原样标注资料标题、发布机构和完整原始URL。",
        ("不得把本地未检出等同于学术研究空白", "无来源内容标记为待核验", "不得虚构文献", "区分事实与推断", "摘要不能替代原文合规判断"),
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
        "输出精简核验表：最多6个会影响结论、合规或任务验收的问题；每项包含位置、风险级别、证据和一条可直接执行的修改建议。低价值措辞偏好不列入。",
        ("优先阻断性问题", "标出无证据声明", "检查数字和术语前后一致", "总输出不超过1200字"),
    ),
    "reviewer": AgentProtocol(
        "依据统一量表对完整成果做独立质量评审。",
        "读取报告、核验结果、需求与人工确认意见。",
        "仅输出JSON：score、dimensions、issues、suggestions。dimensions至少含完整性、逻辑性、可验证性、约束符合度；issues和suggestions分别最多6项，只保留影响验收的关键问题。",
        ("总分0到100", "问题必须具体可定位", "建议必须能驱动下一轮返工", "不得用大量低风险项淹没关键缺陷"),
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
            tool_calls.append({"tool": "local_knowledge", "query": task, "result_count": len(matches), "results": matches})
            tool_context = "\n\n[本地知识库检索结果]\n" + (json.dumps(matches, ensure_ascii=False) if matches else "未检索到匹配资料；必须明确说明资料不足，不得虚构来源。")
        elif agent_id == "fact-checker":
            matches = self.knowledge.search(task, limit=5)
            tool_calls.append({"tool": "local_knowledge_recheck", "query": task, "result_count": len(matches), "results": matches})
            tool_context = (
                "\n\n[事实核验独立检索结果]\n"
                + (json.dumps(matches, ensure_ascii=False) if matches else "独立复检未命中资料；不得把未命中写成事实错误，只能标记证据不足。")
                + "\n请将报告声明与本次独立检索结果逐项对照，不得仅复述文献Agent的判断。"
            )
        elif agent_id == "analyst":
            threshold_ratio = self.calculator.calculate("80 / 100")
            tool_calls.append({"tool": "calculator", "expression": "80 / 100", "result": threshold_ratio})
            tool_context = f"\n\n[结构化计算工具]\n质量阈值比例={threshold_ratio}。这只是平台参数，不是研究数据；需要真实数值时必须给出公式和数据需求。"
        elif agent_id == "writer":
            length_match = re.search(r"(?:约|控制在|不超过|不少于)?\s*(\d{3,5})\s*字", task)
            if length_match:
                target = int(length_match.group(1))
                lower = max(200, int(target * 0.9))
                upper = int(target * 1.1)
                tool_context = (
                    f"\n\n[硬性交付约束]\n目标篇幅为约{target}字，正文必须控制在{lower}至{upper}字。"
                    "优先合并重复章节和免责声明，不得通过附录、说明或重复总结变相超长。"
                    "输出前自行估算篇幅；只输出最终Markdown正文，不要输出写作过程、自检说明或额外解释。"
                )
        if not protocol:
            return base_prompt + "\n请严格依据你的角色、能力标签和工具完成任务，并清楚标注假设与局限。", tool_calls
        checks = "；".join(protocol.checks)
        prompt = (
            f"{base_prompt}{tool_context}\n\n"
            f"[本节点专属执行协议]\n目标：{protocol.objective}\n输入规范：{protocol.input_contract}\n"
            f"输出规范：{protocol.output_contract}\n完成前自检：{checks}\n"
            "必须遵守以上协议；不要越权代替其他Agent，也不要省略规定字段。"
        )
        if agent_id == "writer":
            prompt += (
                "\n报告中的术语必须统一；每项核心结论需与人工确认范围对应。"
                "对无直接来源支撑的一般性判断使用审慎限定，不得把建议、假设或示例写成已验证事实。"
                "返工时逐条落实评审意见，同时删除造成同类问题的旧表述。"
            )
            if "上一版完整报告" in base_prompt:
                prompt += (
                    "\n本次为受约束修订：优先处理高风险和中风险意见；通过替换、删除或压缩原文完成修订，"
                    "不得用不断追加段落的方式修补。修订后的篇幅仍必须满足原始任务字数范围。"
                )
        elif agent_id == "literature":
            prompt += (
                "\n检索范围仅代表当前本地知识库；若未命中资料，只能写‘当前检索资料未覆盖’，"
                "禁止写成‘研究空白’或‘尚无研究’。引用URL必须逐字复制工具结果，不得缩写为网站首页、"
                "补造条款号或改写链接。"
            )
            if any(term in task for term in ("数据分析方案", "变量定义", "数据清洗", "描述统计", "组间比较", "统计方法")):
                prompt += (
                    "\n当前任务的核心是统计方法设计。政策法规资料只能说明数据处理边界，不能作为抽样、"
                    "检验方法或效应量选择的证据。若知识库没有方法学资料，明确写‘当前知识库未提供方法学证据’，"
                    "不要为了形成引用而加入与分析方法无关的政策来源。"
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
