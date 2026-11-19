from __future__ import annotations

import json
import re
from dataclasses import dataclass

from backend.tools import CalculatorTool, LocalKnowledgeTool
from backend.external_knowledge import ExternalKnowledgeService


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
        (
            "必须包含：问题定义、研究范围、约束、交付标准、待人工确认问题。先提取原始任务中已经明确的要求，"
            "不得重复询问，也不得擅自增加学科范围、引用格式、文献数量、数据来源或附加交付物。"
            "只对会实质影响执行且原任务尚未说明的歧义提问，最多3组；任务已经足够明确时应提供“按原要求执行，不增加额外限制”。"
            "最后追加一个```approval_options代码块，内容为JSON数组；每项包含id、question、type(single/multiple)、"
            "options字符串数组，提供2至4个可直接勾选的合理选项。"
        ),
        ("显式列出真正未决的歧义", "已明确要求不得重复确认", "不得伪造数据", "确认项必须可由用户直接回答", "自定义人工意见优先级最高"),
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
        "面向科研人员和管理者，整合有效证据形成可独立阅读、论证完整的专业研究报告。",
        "只使用前序成果、人工确认意见和已标注证据。",
        "以Markdown输出正式研究报告：准确具体的一级标题、摘要、关键词、研究背景、研究方法、核心分析、讨论、结论与建议、参考来源。摘要必须直接概括研究目的、方法、主要认识和结论；正文以连贯论述为主。只输出报告正文，不得输出写作说明、执行过程、自检记录、Agent分工或评审过程。",
        ("不得遗漏人工约束", "不得把待核验内容写成确定事实", "章节结论需可追溯", "标题摘要结论可直接用于正式交付"),
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
        (
            "仅输出JSON：score、dimensions、critical_flags、issues、suggestions。"
            "dimensions必须使用以下五个精确名称并分别给出0到100分：完整性（权重20%）、逻辑性（20%）、"
            "可验证性（25%）、约束符合度（20%）、表达质量与可交付性（15%）。score必须先按加权公式计算："
            "完整性×0.20+逻辑性×0.20+可验证性×0.25+约束符合度×0.20+表达质量与可交付性×0.15，并四舍五入为整数。"
            "评分锚点：90至100可直接交付；80至89达到标准但有少量改进空间；70至79需要返工；"
            "60至69存在重大缺陷；0至59不具备交付条件。critical_flags必须包含四个布尔字段："
            "fabricated_data、unverifiable_core_citations、missing_required_deliverable、violated_explicit_constraints。"
            "若fabricated_data为true，总分最高59；若unverifiable_core_citations或missing_required_deliverable为true，总分最高69；"
            "若violated_explicit_constraints为true，总分最高79。issues和suggestions分别最多6项，只保留影响验收的关键问题。"
            "返工稿必须沿用与上一轮完全相同的量表和严格度；已修复的问题应得到正向反映，不得为了制造反馈而新增低价值扣分项。"
        ),
        (
            "五个维度必须齐全且使用精确名称", "总分必须符合固定权重与严重问题封顶规则",
            "问题必须具体可定位", "建议必须能驱动下一轮返工", "不得用大量低风险项淹没关键缺陷",
            "只有出现新的实质性错误时分数才可下降并须说明原因",
        ),
    ),
}


class AgentLogic:
    def __init__(self) -> None:
        self.knowledge = LocalKnowledgeTool()
        self.calculator = CalculatorTool()
        self.external = ExternalKnowledgeService(self.knowledge)
        self.search_plans: dict[str, list[dict]] = {}

    async def plan_searches(self, task: str) -> tuple[list[dict], int]:
        """Create task-specific scholarly queries and machine-checkable relevance groups."""
        try:
            from backend.llm import llm
            system = (
                "你是学术数据库检索规划器。仅输出JSON，不回答研究问题。根据任务生成2至4条中英文检索式。"
                "中文任务至少包含1条中文检索式和1条英文同义检索式；不得因文献语言不同而改变相关性标准。"
                "每条检索式必须包含query和must_include_groups；must_include_groups是二维字符串数组，"
                "每组表示同义概念，候选文献必须在标题或摘要中命中每一组中的至少一个词。"
                "不同检索式可分别覆盖核心主题、研究方法或权威标准。不得写作者、年份或不存在的论文题名。"
            )
            prompt = f"研究任务：{task}\n输出格式：{{\"searches\":[{{\"query\":\"...\",\"must_include_groups\":[[\"中文词\",\"English synonym\"],[\"核心概念\"]]}}]}}"
            raw, tokens = await llm.complete(system, prompt, json_mode=True)
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                start, end = raw.find("{"), raw.rfind("}")
                value = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
            return self.external.normalize_searches(value, task), tokens
        except Exception:
            return self.external.default_searches(task), 0

    def task_matches(self, task: str, limit: int = 8) -> tuple[str, list[dict]]:
        searches = self.search_plans.get(task) or self.external.default_searches(task)
        accepted: dict[str, dict] = {}
        for search in searches:
            candidates = self.knowledge.search(search["query"], limit=15)
            for item in candidates:
                if self.external.relevant_to_search(item.get("title", ""), item.get("snippet", ""), search):
                    accepted[f"{item.get('source')}:{item.get('chunk')}"] = item
        ranked = sorted(accepted.values(), key=lambda item: int(item.get("score", 0)), reverse=True)
        return " | ".join(search["query"] for search in searches), ranked[:limit]

    async def content_relevant_matches(self, task_context: str, matches: list[dict]) -> tuple[list[dict], int]:
        """Rerank local chunks against confirmed requirements; reject relevance scores below 50."""
        if not matches:
            return [], 0
        try:
            from backend.llm import llm
            system = (
                "你是科研证据内容相关性审核器。仅输出JSON。根据题名和证据片段判断其内容是否能支持任务。"
                "不能只看关键词重合；研究对象、核心问题和任务要求必须对应。每项输出index、score、reason、"
                "supported_claims、limitations。score为0到100，低于50代表不应进入本任务证据集。"
            )
            candidates = [
                {"index": index, "title": item.get("title"), "content": item.get("snippet", "")[:1600]}
                for index, item in enumerate(matches)
            ]
            raw, tokens = await llm.complete(
                system,
                f"任务与确认要求：\n{task_context[:6000]}\n\n候选证据：\n{json.dumps(candidates, ensure_ascii=False)}"
                "\n输出格式：{\"results\":[{\"index\":0,\"score\":80,\"reason\":\"...\","
                "\"supported_claims\":[\"...\"],\"limitations\":[\"...\"]}]}",
                json_mode=True,
            )
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                start, end = raw.find("{"), raw.rfind("}")
                value = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
            assessments = {
                int(item.get("index")): item for item in value.get("results", value.get("assessments", []))
                if isinstance(item, dict) and str(item.get("index", "")).isdigit()
            }
            accepted = []
            for index, item in enumerate(matches):
                assessment = assessments.get(index, {})
                score = max(0, min(100, int(assessment.get("score") or 0)))
                if score < 50:
                    continue
                accepted.append({
                    **item,
                    "relevance_score": score,
                    "relevance_reason": str(assessment.get("reason") or "").strip(),
                    "supported_claims": assessment.get("supported_claims") or [],
                    "limitations": assessment.get("limitations") or [],
                })
            return accepted, tokens
        except Exception:
            return matches, 0

    async def prepare_async(
        self, agent_id: str, task: str, base_prompt: str, research_context: str = "",
    ) -> tuple[str, list[dict]]:
        """Enrich the literature node with durable external evidence before local retrieval."""
        external_call = None
        if agent_id == "literature":
            evidence_task = research_context.strip() or task
            searches, planning_tokens = await self.plan_searches(evidence_task)
            self.search_plans[task] = searches
            external_call = await self.external.search_and_ingest(evidence_task, searches)
            external_call["planning_tokens"] = planning_tokens + int(external_call.get("relevance_tokens") or 0)
        prompt, tool_calls = self.prepare(agent_id, task, base_prompt)
        if agent_id in {"literature", "fact-checker"}:
            knowledge_tool = "local_knowledge" if agent_id == "literature" else "local_knowledge_recheck"
            call = next((item for item in tool_calls if item.get("tool") == knowledge_tool), None)
            if call is not None:
                original = call.get("results") or []
                filtered, relevance_tokens = await self.content_relevant_matches(research_context or task, original)
                call["results"] = filtered
                call["result_count"] = len(filtered)
                call["discarded_irrelevant"] = len(original) - len(filtered)
                call["token_usage"] = int(call.get("token_usage") or 0) + relevance_tokens
                if original:
                    prompt = prompt.replace(
                        json.dumps(original, ensure_ascii=False),
                        json.dumps(filtered, ensure_ascii=False) if filtered else "未发现内容相关性达到50分的证据；不得虚构来源。",
                    )
        if external_call is not None:
            tool_calls.insert(0, {
                "tool": "external_knowledge_search", "query": task, "search_query": external_call.get("search_query"),
                "providers": external_call.get("providers", []), "found": external_call.get("found", 0),
                "result_count": len(external_call.get("imported", [])), "results": external_call.get("imported", []),
                "duplicates": external_call.get("duplicates", 0), "discarded_irrelevant": external_call.get("discarded_irrelevant", 0),
                "token_usage": external_call.get("planning_tokens", 0),
                "errors": external_call.get("errors", []),
            })
            summary = (
                f"\n\n[外部检索入库审计]\n聚焦检索式：{external_call.get('search_query') or task}；"
                f"已检索：{', '.join(external_call.get('providers', [])) or '未启用'}；"
                f"发现{external_call.get('found', 0)}条，新增入库{len(external_call.get('imported', []))}条，"
                f"去重{external_call.get('duplicates', 0)}条，过滤偏题资料{external_call.get('discarded_irrelevant', 0)}条。"
            )
            if external_call.get("errors"):
                summary += "部分服务不可用：" + "；".join(external_call["errors"])
            prompt += summary
        return prompt, tool_calls

    async def prepare_writer_evidence(self, task: str, research_context: str = "") -> tuple[str, list[dict], int]:
        """Give workflows without a literature node the same traceable evidence contract."""
        evidence_task = research_context.strip() or task
        searches, planning_tokens = await self.plan_searches(evidence_task)
        self.search_plans[task] = searches
        external_call = await self.external.search_and_ingest(evidence_task, searches)
        focused_query, matches = self.task_matches(task)
        matches, relevance_tokens = await self.content_relevant_matches(evidence_task, matches)
        total_tokens = planning_tokens + int(external_call.get("relevance_tokens") or 0) + relevance_tokens
        return focused_query, matches, total_tokens

    def prepare(self, agent_id: str, task: str, base_prompt: str) -> tuple[str, list[dict]]:
        protocol = PROTOCOLS.get(agent_id)
        tool_calls: list[dict] = []
        tool_context = ""
        if agent_id == "literature":
            focused_query, matches = self.task_matches(task)
            tool_calls.append({"tool": "local_knowledge", "query": focused_query, "result_count": len(matches), "results": matches})
            tool_context = "\n\n[本地知识库检索结果]\n" + (json.dumps(matches, ensure_ascii=False) if matches else "未检索到匹配资料；必须明确说明资料不足，不得虚构来源。")
        elif agent_id == "fact-checker":
            focused_query, matches = self.task_matches(task)
            tool_calls.append({"tool": "local_knowledge_recheck", "query": focused_query, "result_count": len(matches), "results": matches})
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
                "\n报告必须像可直接交付的科研报告，而不是任务清单、核验记录或风险提示汇编。"
                "以自然段展开证据、分析和论证，避免连续堆砌短句、项目符号和同义提醒；建议应建立在前文分析上。"
                "标题、摘要、关键词和结论中禁止出现‘设计稿’‘未实施’‘无真实数据’‘待确认’‘内部版’等过程标签。"
                "若任务仅要求研究方案，应在研究方法或局限章节用一句专业表述说明实证数据采集不在本研究范围内，全文只说明一次。"
                "不得反复解释缺少数据、资料局限或合规免责声明，不得让这些内容挤占核心分析篇幅。"
                "报告中的术语必须统一；每项核心结论需与人工确认范围对应。"
                "对无直接来源支撑的一般性判断使用审慎限定，不得把建议、假设或示例写成已验证事实。"
                "返工时逐条落实评审意见，同时删除造成同类问题的旧表述。"
                "参考文献必须来自前序证据；有效来源不少于3条时，正文和参考文献必须实际使用至少3条与任务直接相关的来源，"
                "有效来源不足3条时使用全部有效来源。正文采用[1][2]格式标注，文末统一使用“## 参考文献”标题，"
                "每条严格按“[序号] 作者. 题名[文献类型]. 期刊或机构, 年份. DOI或完整URL.”格式独占一段。"
                "禁止在参考文献条目后追加证据等级、摘要级信息、唯一来源、检索说明或核验说明。"
                "禁止列出正文未使用的装饰性文献，也不得省略全部引用。"
                "参考文献章节只能列出真实文献条目，禁止写入检索失败原因、引用策略、人工确认意见、核验过程、"
                "尚待补充事项或‘后续版本将’之类计划。任何用户要求和评审意见都只能转化为报告内容与结构，"
                "不得原样复述为正文，也不得向读者解释系统如何完成任务。"
            )
            if "上一版完整报告" in base_prompt:
                prompt += (
                    "\n本次为受约束修订：优先处理高风险和中风险意见；通过替换、删除或压缩原文完成修订，"
                    "不得用不断追加段落的方式修补，不得增加‘修改说明’或逐条回应评审意见。"
                    "修订后的篇幅仍必须满足原始任务字数范围，并保持摘要、正文和结论相互一致。"
                )
        elif agent_id == "literature":
            prompt += (
                "\n检索范围仅代表当前本地知识库；若未命中资料，只能写‘当前检索资料未覆盖’，"
                "禁止写成‘研究空白’或‘尚无研究’。引用URL必须逐字复制工具结果，不得缩写为网站首页、"
                "补造条款号或改写链接。"
                "只保留能够直接支撑当前研究问题的资料；仅命中宽泛上位主题、却未覆盖任务核心对象与方法的文献必须剔除，"
                "不得为了凑满证据数量加入任何其他领域或其他研究对象的偏题材料。有效来源不足时如实报告数量。"
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
