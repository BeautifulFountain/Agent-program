from __future__ import annotations

import asyncio
import json
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from backend.database import db
from backend.agent_logic import agent_logic, extract_approval_options
from backend.llm import llm
from backend.schemas import utc_now


def _safe_json(value: str) -> dict:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            return json.loads(value[start:end + 1])
        raise RuntimeError("评审Agent未返回有效JSON")


REVIEW_DIMENSION_WEIGHTS = {
    "完整性": 0.20,
    "逻辑性": 0.20,
    "可验证性": 0.25,
    "约束符合度": 0.20,
    "表达质量与可交付性": 0.15,
}

REVIEW_DIMENSION_ALIASES = {
    "完整性": ("完整性",),
    "逻辑性": ("逻辑性", "逻辑一致性"),
    "可验证性": ("可验证性", "可验证性与来源", "来源可靠性", "事实准确性"),
    "约束符合度": ("约束符合度", "约束符合性"),
    "表达质量与可交付性": ("表达质量与可交付性", "表达质量", "可交付性", "表达清晰度"),
}

CRITICAL_SCORE_CAPS = {
    "fabricated_data": 59,
    "unverifiable_core_citations": 69,
    "missing_required_deliverable": 69,
    "violated_explicit_constraints": 79,
}


def _canonical_review_dimensions(dimensions: dict[str, int]) -> dict[str, int]:
    canonical: dict[str, int] = {}
    for target, aliases in REVIEW_DIMENSION_ALIASES.items():
        for alias in aliases:
            if alias in dimensions:
                canonical[target] = dimensions[alias]
                break
    return canonical


def _weighted_review_score(dimensions: dict[str, int], flags: dict[str, bool]) -> int | None:
    canonical = _canonical_review_dimensions(dimensions)
    if set(canonical) != set(REVIEW_DIMENSION_WEIGHTS):
        return None
    score = round(sum(canonical[name] * weight for name, weight in REVIEW_DIMENSION_WEIGHTS.items()))
    active_caps = [cap for name, cap in CRITICAL_SCORE_CAPS.items() if flags.get(name, False)]
    return min([score, *active_caps]) if active_caps else score


def normalize_validation(value: dict) -> dict:
    """Normalize common reviewer field variants into the platform contract."""
    dimensions = value.get("dimensions") or value.get("dimension_scores") or {}
    issues = value.get("issues") or value.get("problems") or []
    suggestions = value.get("suggestions") or value.get("improvement_suggestions") or []
    def string_list(items) -> list[str]:
        if isinstance(items, str):
            return [items]
        if not isinstance(items, list):
            return []
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                severity = item.get("severity")
                location = item.get("location") or item.get("target")
                description = (
                    item.get("description") or item.get("issue") or item.get("message")
                    or item.get("problem") or item.get("action") or item.get("comment")
                )
                suggestion = item.get("suggestion")
                text = ""
                if severity:
                    text += f"[{severity}] "
                if location:
                    text += f"{location}："
                if description:
                    text += str(description)
                if suggestion:
                    text += f"；建议：{suggestion}"
                if text:
                    result.append(text)
        return result
    normalized_dimensions: dict[str, int] = {}
    dimension_comments: dict[str, str] = {}
    if isinstance(dimensions, dict):
        for name, item in dimensions.items():
            raw_score = item
            if isinstance(item, dict):
                raw_score = item.get("score", item.get("value", 0))
                if item.get("comment"):
                    dimension_comments[str(name)] = str(item["comment"])
            try:
                normalized_dimensions[str(name)] = max(0, min(100, int(float(raw_score or 0))))
            except (TypeError, ValueError):
                normalized_dimensions[str(name)] = 0
    raw_flags = value.get("critical_flags") or {}
    critical_flags = {
        name: bool(raw_flags.get(name, False)) if isinstance(raw_flags, dict) else False
        for name in CRITICAL_SCORE_CAPS
    }
    model_score = max(0, min(100, int(value.get("score", value.get("total_score", 0)) or 0)))
    weighted_score = _weighted_review_score(normalized_dimensions, critical_flags)
    result = {
        "score": weighted_score if weighted_score is not None else model_score,
        "dimensions": normalized_dimensions,
        "dimension_comments": dimension_comments,
        "issues": string_list(issues),
        "suggestions": string_list(suggestions),
    }
    if weighted_score is not None:
        result["critical_flags"] = critical_flags
        result["score_basis"] = "weighted_rubric_v1"
    return result


def clean_report_output(value: str) -> str:
    """Remove process labels that do not belong in a reader-facing research report."""
    value = re.sub(r"[（(][^（）()]{0,40}(?:设计稿|未实施|无真实数据)[^（）()]{0,40}[）)]", "", value)
    value = re.sub(r"(?m)^\s*(?:特别说明|写作说明|生成说明|自检说明)[:：].*(?:\n|$)", "", value)
    value = re.sub(r"(?m)^\s*(?:[-*]\s*)?(?:本报告为|本文为)?(?:设计稿|未实施版本|无真实数据版本)[，,。；;：:].*(?:\n|$)", "", value)
    value = re.sub(r"(?:本报告|本文)(?:属于|仅为|是)(?:一份)?(?:设计稿|未实施版本)(?:，|,)?", "", value)
    value = re.sub(
        r"(?m)^\s*(?:后续版本|后续工作|下一版本|下一步)(?:将|会|需|需要).*(?:\n|$)", "", value,
    )
    value = re.sub(
        r"(?m)^\s*(?:本报告|本文)(?:的)?(?:引用策略|检索策略|写作策略|修改策略)(?:遵循|依据|采用).*(?:\n|$)", "", value,
    )
    value = re.sub(r"(?m)^##\s*参考来源\s*$", "## 参考文献", value)
    # A references section contains only formal entries. Execution notes belong to the audit UI, never the report.
    reference_match = re.search(r"(?ms)^##\s*参考文献\s*$\n(?P<body>.*?)(?=^##\s|\Z)", value)
    if reference_match:
        body = reference_match.group("body")
        entries = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = re.match(r"^(?:[-*]\s*)?(?:\[(\d+)\]|(\d+)[.、])\s*(.+)$", stripped)
            if not match:
                continue
            content = match.group(3).strip()
            if re.search(r"本报告|本文|检索|核验|摘要级|唯一.*来源|后续版本|证据等级|人工确认", content):
                continue
            entries.append(content)
        if entries:
            normalized = "\n".join(f"[{index}] {content}" for index, content in enumerate(entries, 1))
            value = value[:reference_match.start()] + "## 参考文献\n\n" + normalized + "\n" + value[reference_match.end():]
        else:
            value = value[:reference_match.start()] + value[reference_match.end():]
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def rework_agent_ids(validation: dict, available: set[str]) -> list[str]:
    """Route review findings back to the upstream owners that can actually repair them."""
    feedback = "\n".join([*validation.get("issues", []), *validation.get("suggestions", [])]).lower()
    selected: list[str] = []
    rules = (
        ("planner", ("结构", "任务拆分", "依赖", "范围", "交付物", "完整性")),
        ("literature", ("引用", "文献", "来源", "证据", "doi", "url", "可验证")),
        ("analyst", ("数据", "变量", "样本", "统计", "指标", "方法", "公式", "可复现")),
    )
    for agent_id, terms in rules:
        if agent_id in available and any(term in feedback for term in terms):
            selected.append(agent_id)
    return selected


def automatic_rework_required(score: int, quality_threshold: int, loop_count: int, max_loop_count: int) -> bool:
    """Keep reworking until the quality gate passes or the configured loop budget is exhausted."""
    return score < quality_threshold and loop_count < max_loop_count


def select_best_result(run: dict) -> bool:
    """Select the highest-scoring reviewed draft without deleting the audit trail."""
    reviewer_runs = [
        item for item in run.get("node_runs", [])
        if item.get("node_id") == "reviewer" and item.get("status") == "completed" and item.get("output")
    ]
    candidates: list[tuple[int, int, dict, dict]] = []
    for review in reviewer_runs:
        try:
            validation = normalize_validation(_safe_json(review["output"]))
        except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
            continue
        review_loop = int(review.get("loop", 0))
        matching_writer = next((
            item for item in reversed(run.get("node_runs", []))
            if item.get("node_id") == "writer" and item.get("status") == "completed"
            and int(item.get("loop", 0)) == review_loop and item.get("output")
        ), None)
        if not matching_writer:
            continue
        validation = enforce_deliverable_validation(run, validation, matching_writer["output"])
        candidates.append((int(validation["score"]), review_loop, validation, review))
    if not candidates:
        return False

    best_score, best_loop, best_validation, _ = max(candidates, key=lambda item: (item[0], -item[1]))
    latest_score = max(candidates, key=lambda item: item[1])[0]
    writer_runs = [
        item for item in run.get("node_runs", [])
        if item.get("node_id") == "writer" and item.get("status") == "completed"
        and int(item.get("loop", 0)) == best_loop and item.get("output")
    ]
    if not writer_runs:
        return False

    best_output = clean_report_output(writer_runs[-1]["output"])
    changed = any([
        run.get("score") != best_score,
        run.get("latest_score") != latest_score,
        run.get("selected_loop") != best_loop,
        run.get("final_output") != best_output,
        run.get("validation") != best_validation,
    ])
    run["score"] = best_score
    run["latest_score"] = latest_score
    run["selected_loop"] = best_loop
    run["final_output"] = best_output
    run["validation"] = best_validation
    return changed


def _normalized_title(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").lower())


def _normalized_url(value: str) -> str:
    value = (value or "").strip().lower().rstrip(".,;，。；)]}")
    return re.sub(r"^https?://(?:www\.)?", "", value).rstrip("/")


def _normalized_doi(value: str) -> str:
    match = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", (value or "").lower())
    return match.group(0).rstrip(".,;，。；)]}") if match else ""


def _writer_run_for_metrics(run: dict) -> dict | None:
    selected_loop = run.get("selected_loop")
    candidates = [
        item for item in run.get("node_runs", [])
        if item.get("node_id") == "writer" and item.get("status") == "completed"
    ]
    if selected_loop is not None:
        selected = [item for item in candidates if int(item.get("loop", 0)) == int(selected_loop)]
        if selected:
            return selected[-1]
    return candidates[-1] if candidates else None


def _evidence_is_cited(item: dict, output: str) -> bool:
    lowered = output.lower()
    doi = _normalized_doi(str(item.get("doi") or item.get("url") or ""))
    if doi and doi in lowered:
        return True
    url = _normalized_url(str(item.get("url") or ""))
    if url and url in _normalized_url(output):
        return True
    title = _normalized_title(str(item.get("title") or ""))
    return bool(len(title) >= 8 and title in _normalized_title(output))


def evaluate_deliverable(run: dict) -> dict:
    """Compute deterministic citation and explicit-constraint acceptance metrics."""
    output = run.get("final_output") or ""
    writer_run = _writer_run_for_metrics(run)
    evidence = {
        str(item.get("evidence_id") or f"{item.get('source', '')}:{item.get('chunk', '')}"): item
        for item in ((writer_run or {}).get("evidence_snapshot") or [])
    }
    cited = [item for item in evidence.values() if _evidence_is_cited(item, output)]
    citation_total = len(evidence)

    checks: list[dict[str, object]] = []
    checks.append({"name": "已生成正式成果", "passed": bool(output.strip())})
    checks.append({
        "name": "包含报告标题与正文结构",
        "passed": bool(re.search(r"(?m)^#\s+.+", output) and re.search(r"(?m)^##\s+.+", output)),
    })
    checks.append({
        "name": "未混入过程性说明",
        "passed": not bool(re.search(r"设计稿|未实施|无真实数据|写作说明|自检说明|Agent分工", output)),
    })
    if citation_total >= 3:
        checks.append({"name": "至少实际引用3条有效文献", "passed": len(cited) >= 3})
    task = run.get("task") or ""
    target = re.search(r"约\s*(\d{3,5})\s*字", task)
    if target:
        expected = int(target.group(1))
        visible = len(re.sub(r"\s|[#*`>|_-]", "", output))
        checks.append({"name": f"篇幅约{expected}字", "passed": expected * 0.75 <= visible <= expected * 1.35})
    for term in ("数据安全", "个人信息保护", "学术诚信", "治理建议", "风险", "研究方法", "局限"):
        if term in task:
            checks.append({"name": f"覆盖明确要求：{term}", "passed": term in output})
    satisfied = sum(1 for check in checks if check["passed"])
    return {
        "citation_coverage": {
            "cited": len(cited), "retrieved": citation_total,
            "percent": round(len(cited) / citation_total * 100) if citation_total else 0,
        },
        "constraint_compliance": {
            "satisfied": satisfied, "total": len(checks),
            "percent": round(satisfied / len(checks) * 100) if checks else 0,
            "checks": checks,
        },
    }


def enforce_deliverable_validation(run: dict, validation: dict, output: str) -> dict:
    """Apply deterministic delivery gates so fluent reviewer prose cannot approve a broken report."""
    snapshot = {**run, "final_output": output}
    metrics = evaluate_deliverable(snapshot)
    result = deepcopy(validation)
    result.setdefault("issues", [])
    result.setdefault("suggestions", [])
    result.setdefault("critical_flags", {})
    citation = metrics["citation_coverage"]
    checks = metrics["constraint_compliance"]["checks"]
    process_clean = next((bool(item["passed"]) for item in checks if item["name"] == "未混入过程性说明"), True)
    has_reference_section = bool(re.search(r"(?m)^##\s*(?:参考来源|参考文献)\s*$", output))
    if citation["retrieved"] > 0 and citation["cited"] == 0:
        result["critical_flags"]["unverifiable_core_citations"] = True
        result["score"] = min(int(result.get("score", 0)), 69)
        issue = "[阻断] 正文和参考文献未实际使用任何已检索证据。"
        suggestion = "从上游有效证据中选择与核心论点直接对应的资料，在正文标注并在参考文献中列出准确标题与原始URL。"
        if issue not in result["issues"]:
            result["issues"].insert(0, issue)
        if suggestion not in result["suggestions"]:
            result["suggestions"].insert(0, suggestion)
    elif citation["retrieved"] >= 3 and citation["cited"] < 3:
        result["score"] = min(int(result.get("score", 0)), 79)
        issue = f"[高] 已获得{citation['retrieved']}条有效证据，但报告仅实际引用{citation['cited']}条，未达到至少3条的交付目标。"
        suggestion = "补充与核心论点直接对应的正文标注，并在参考文献中至少列出3条实际使用的有效来源。"
        if issue not in result["issues"]:
            result["issues"].insert(0, issue)
        if suggestion not in result["suggestions"]:
            result["suggestions"].insert(0, suggestion)
    if not process_clean or re.search(r"后续版本|引用策略遵循人工确认|检索所得文献.*无实质对应", output):
        result["critical_flags"]["missing_required_deliverable"] = True
        result["score"] = min(int(result.get("score", 0)), 69)
        issue = "[阻断] 报告正文混入执行说明、失败说明或未来修改计划，不是独立可读的研究成果。"
        if issue not in result["issues"]:
            result["issues"].insert(0, issue)
    if citation["retrieved"] > 0 and not has_reference_section:
        result["critical_flags"]["missing_required_deliverable"] = True
        result["score"] = min(int(result.get("score", 0)), 69)
        issue = "[阻断] 缺少正式参考文献章节。"
        if issue not in result["issues"]:
            result["issues"].append(issue)
    result["deterministic_metrics"] = metrics
    return result


def _latest_literature_evidence(run: dict, loop: int) -> list[dict]:
    candidates = [
        item for item in run.get("node_runs", [])
        if item.get("node_id") == "literature" and item.get("status") == "completed"
        and int(item.get("loop", 0)) <= loop
    ]
    if not candidates:
        return []
    latest = max(candidates, key=lambda item: int(item.get("loop", 0)))
    evidence: list[dict] = []
    for call in latest.get("tool_calls", []):
        if call.get("tool") == "local_knowledge":
            evidence.extend(call.get("results") or [])
    return evidence


def _number_evidence(items: list[dict], limit: int = 8) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = _normalized_doi(str(item.get("doi") or item.get("url") or "")) or _normalized_url(str(item.get("url") or "")) or _normalized_title(str(item.get("title") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        value = deepcopy(item)
        value["evidence_id"] = f"E{len(selected) + 1}"
        value["doi"] = _normalized_doi(str(item.get("doi") or item.get("url") or ""))
        selected.append(value)
        if len(selected) >= limit:
            break
    return selected


class RunManager:
    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancel_flags: set[str] = set()
        self.pause_flags: set[str] = set()

    def create(self, task: str, workflow: dict, output_format: str = "markdown") -> dict:
        run_id = uuid4().hex[:12]
        now = utc_now()
        run = {
            "id": run_id, "task": task, "workflow_id": workflow["id"], "workflow_snapshot": deepcopy(workflow),
            "status": "queued", "progress": 0, "score": None, "loop_count": 0, "token_usage": 0,
            "started_at": now, "finished_at": None, "created_at": now, "updated_at": now,
            "node_runs": [], "final_output": None, "validation": None, "error": None,
            "approval": None, "human_feedback": None,
            "final_acceptance": None, "human_rework_count": 0,
            "selected_loop": None, "latest_score": None,
            "output_format": output_format,
        }
        db.upsert("runs", run_id, run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run_id))
        return run

    async def emit(self, run_id: str, event_type: str, data: dict) -> None:
        db.add_event(run_id, {"type": event_type, "data": data, "created_at": utc_now()})

    def save(self, run: dict) -> None:
        run["updated_at"] = utc_now()
        db.upsert("runs", run["id"], run)

    async def execute(self, run_id: str, resume: bool = False) -> None:
        run = db.get("runs", run_id)
        if not run:
            return
        run["status"] = "running"
        self.save(run)
        await self.emit(run_id, "run.started", {"status": "running"})
        try:
            workflow = run["workflow_snapshot"]
            nodes = {n["id"]: n for n in workflow["nodes"]}
            completed: dict[str, str] = {}
            if resume:
                for node_run in run["node_runs"]:
                    if node_run["status"] == "completed" and node_run.get("output"):
                        completed[node_run["node_id"]] = node_run["output"]
            pending = set(nodes) - completed.keys()
            while pending:
                self._assert_not_cancelled(run_id)
                ready = [nodes[node_id] for node_id in pending if set(nodes[node_id]["dependencies"]) <= completed.keys()]
                if not ready:
                    raise RuntimeError("工作流存在循环依赖或缺失节点")
                results = await asyncio.gather(*(self._execute_node(run, node, completed) for node in ready))
                for node, output in zip(ready, results):
                    completed[node["id"]] = output
                    pending.remove(node["id"])
                run["progress"] = int(len(completed) / len(nodes) * 90)
                self.save(run)
                approval_node = next((node for node in ready if node.get("requires_approval")), None)
                if approval_node and not run.get("approval"):
                    run["status"] = "waiting_approval"
                    run["approval"] = {
                        "node_id": approval_node["id"],
                        "status": "pending",
                        "requested_at": utc_now(),
                        "feedback": None,
                        "options": extract_approval_options(completed[approval_node["id"]], run["task"]),
                    }
                    self.save(run)
                    await self.emit(run_id, "run.waiting_approval", {"node_id": approval_node["id"]})
                    return

            validation = enforce_deliverable_validation(
                run, normalize_validation(_safe_json(completed["reviewer"])), completed.get("writer", ""),
            )
            run["validation"] = validation
            run["score"] = int(validation.get("score", 0))
            while automatic_rework_required(
                run["score"], workflow["quality_threshold"], run["loop_count"], workflow["max_loop_count"]
            ):
                self._assert_not_cancelled(run_id)
                previous_score = int(run["score"])
                run["loop_count"] += 1
                await self.emit(run_id, "run.rework", {"loop_count": run["loop_count"], "issues": validation.get("issues", [])})
                feedback = (
                    f"上一轮统一量表评分：{previous_score}分。只修复下列影响验收的关键问题，"
                    "不得扩展无关主题、增加重复免责声明或把核验过程写入报告正文。\n"
                    + "\n".join([*validation.get("issues", []), *validation.get("suggestions", [])])
                )
                for node_id in rework_agent_ids(validation, set(nodes)):
                    completed[node_id] = await self._execute_node(
                        run, nodes[node_id], completed, feedback=feedback, rework=True,
                    )
                previous_draft = completed.get("writer", "")
                completed["writer"] = await self._execute_node(
                    run, nodes["writer"], completed, feedback=feedback, rework=True,
                    previous_output=previous_draft,
                )
                if "fact-checker" in nodes:
                    completed["fact-checker"] = await self._execute_node(run, nodes["fact-checker"], completed, feedback=feedback, rework=True)
                completed["reviewer"] = await self._execute_node(run, nodes["reviewer"], completed, feedback=feedback, rework=True)
                validation = enforce_deliverable_validation(
                    run, normalize_validation(_safe_json(completed["reviewer"])), completed.get("writer", ""),
                )
                run["validation"] = validation
                run["score"] = int(validation.get("score", 0))
                self.save(run)
            run["final_output"] = completed.get("writer")
            select_best_result(run)
            run["delivery_metrics"] = evaluate_deliverable(run)
            run["status"] = "completed"
            run["progress"] = 100
            run["finished_at"] = utc_now()
            self.save(run)
            await self.emit(run_id, "run.completed", {"status": run["status"], "score": run["score"]})
        except asyncio.CancelledError:
            if run_id in self.pause_flags:
                for item in run.get("node_runs", []):
                    if item.get("status") in {"running", "reworking"}:
                        item["status"] = "paused"
                        item["finished_at"] = utc_now()
                run["status"] = "paused"
                run["finished_at"] = None
                self.save(run)
                await self.emit(run_id, "run.paused", {"status": "paused"})
            else:
                run["status"] = "cancelled"
                run["finished_at"] = utc_now()
                self.save(run)
                await self.emit(run_id, "run.cancelled", {"status": "cancelled"})
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = str(exc)[:500]
            run["finished_at"] = utc_now()
            self.save(run)
            await self.emit(run_id, "run.failed", {"error": run["error"]})

    async def _execute_node(
        self, run: dict, node: dict, completed: dict[str, str], feedback: str = "",
        rework: bool = False, previous_output: str = "",
    ) -> str:
        agent = db.get("agents", node["agent_id"])
        if not agent:
            raise RuntimeError(f"找不到Agent：{node['agent_id']}")
        node_run = {
            "id": uuid4().hex[:10], "node_id": node["id"], "label": node["label"],
            "status": "reworking" if rework else "running", "input": "", "output": None,
            "score": None, "duration_ms": None, "error": None, "retry_count": 0,
            "loop": run["loop_count"], "started_at": utc_now(), "finished_at": None,
        }
        dependency_text = "\n\n".join(f"[{key}]\n{completed[key]}" for key in node["dependencies"] if key in completed)
        prompt = f"原始任务：{run['task']}\n返工轮次: {run['loop_count']}\n前序成果：\n{dependency_text or '无'}"
        if previous_output:
            prompt += (
                "\n上一版完整报告：\n" + previous_output
                + "\n请保留上一版中正确且已验证的内容，只针对反馈做可追踪的增量修订，不要从头重写。"
            )
        if node["id"] == "reviewer" and "writer" not in node["dependencies"] and completed.get("writer"):
            prompt += f"\n待评审的完整报告正文：\n{completed['writer']}"
        if feedback:
            prompt += f"\n评审反馈：{feedback}\n请针对反馈修订。"
        if run.get("human_feedback") and node["id"] != "requirements":
            prompt += f"\n人工确认意见：{run['human_feedback']}\n后续工作必须遵循该意见。"
        research_context = "\n\n".join(filter(None, [
            run["task"],
            completed.get("requirements", ""),
            completed.get("planner", ""),
            run.get("human_feedback") or "",
        ]))
        prompt, tool_calls = await agent_logic.prepare_async(
            node["agent_id"], run["task"], prompt, research_context=research_context,
        )
        if node["id"] == "writer":
            evidence = _latest_literature_evidence(run, int(run["loop_count"]))
            if not evidence:
                query, evidence, planning_tokens = await agent_logic.prepare_writer_evidence(run["task"], research_context)
                tool_calls.append({
                    "tool": "writer_evidence", "query": query, "result_count": len(evidence),
                    "results": evidence, "token_usage": planning_tokens,
                })
            evidence_snapshot = _number_evidence(evidence)
            node_run["evidence_snapshot"] = evidence_snapshot
            if evidence_snapshot:
                prompt += (
                    "\n\n[本轮写作可用证据清单]\n"
                    + json.dumps(evidence_snapshot, ensure_ascii=False)
                    + "\n只能引用此清单中的证据。E1对应参考文献[1]、E2对应[2]，依次类推；"
                    "正文必须引用实际支撑论点的证据，并保留准确题名、DOI或URL。不得自行生成清单外文献。"
                )
            else:
                prompt += (
                    "\n\n[本轮写作可用证据清单]\n未获得与任务内容相符且含题名摘要的有效证据。"
                    "不得虚构参考文献；应完成无需外部事实支撑的任务结构，并明确将需要来源的结论标为待核验。"
                )
        run["token_usage"] += sum(int(call.get("token_usage") or 0) for call in tool_calls)
        node_run["input"] = prompt
        node_run["tool_calls"] = tool_calls
        run["node_runs"].append(node_run)
        self.save(run)
        await self.emit(run["id"], "node.started", {"node_id": node["id"], "label": node["label"], "loop": run["loop_count"]})
        start = time.perf_counter()
        error = None
        for attempt in range(node["retry_limit"] + 1):
            try:
                output, tokens = await asyncio.wait_for(
                    llm.complete(agent["system_prompt"], prompt, json_mode=node["kind"] == "validator"),
                    timeout=node["timeout_seconds"],
                )
                if node["id"] == "writer":
                    output = clean_report_output(output)
                run["token_usage"] += tokens
                node_run.update(status="completed", output=output, retry_count=attempt, finished_at=utc_now())
                if node["kind"] == "validator":
                    node_run["score"] = normalize_validation(_safe_json(output))["score"]
                break
            except Exception as exc:
                error = str(exc)
                node_run["retry_count"] = attempt
                if attempt < node["retry_limit"]:
                    await asyncio.sleep(0.3 * (attempt + 1))
        else:
            node_run.update(status="failed", error=error[:500] if error else "未知错误", finished_at=utc_now())
            self.save(run)
            await self.emit(run["id"], "node.failed", {"node_id": node["id"], "error": node_run["error"]})
            raise RuntimeError(f"节点 {node['label']} 执行失败：{node_run['error']}")
        node_run["duration_ms"] = int((time.perf_counter() - start) * 1000)
        self.save(run)
        await self.emit(run["id"], "node.completed", {"node_id": node["id"], "duration_ms": node_run["duration_ms"], "score": node_run["score"]})
        return node_run["output"]

    def _assert_not_cancelled(self, run_id: str) -> None:
        if run_id in self.cancel_flags:
            raise asyncio.CancelledError

    def cancel(self, run_id: str) -> bool:
        task = self.tasks.get(run_id)
        if task and not task.done():
            self.cancel_flags.add(run_id)
            task.cancel()
            return True
        return False

    def pause(self, run_id: str) -> dict:
        run = db.get("runs", run_id)
        if not run:
            raise ValueError("任务不存在")
        if run.get("status") not in {"queued", "running", "reworking"}:
            raise ValueError("只有执行中的任务可以暂停")
        self.pause_flags.add(run_id)
        run["status"] = "paused"
        self.save(run)
        task = self.tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        return run

    def resume(self, run_id: str) -> dict:
        run = db.get("runs", run_id)
        if not run:
            raise ValueError("任务不存在")
        if run.get("status") != "paused":
            raise ValueError("只有已暂停任务可以继续执行")
        self.pause_flags.discard(run_id)
        self.cancel_flags.discard(run_id)
        run["status"] = "queued"
        self.save(run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run_id, resume=True))
        return run

    def approve(self, run_id: str, feedback: str) -> dict:
        run = db.get("runs", run_id)
        if not run:
            raise ValueError("任务不存在")
        if run["status"] != "waiting_approval":
            raise ValueError("任务当前不在等待人工确认状态")
        run["human_feedback"] = feedback
        run["approval"] = {
            **(run.get("approval") or {}),
            "status": "approved",
            "feedback": feedback,
            "approved_at": utc_now(),
        }
        run["status"] = "queued"
        self.save(run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run_id, resume=True))
        return run

    def request_final_rework(self, run_id: str, feedback: str, agent_ids: list[str]) -> dict:
        run = self._final_review_run(run_id)
        workflow_ids = {node["id"] for node in run["workflow_snapshot"]["nodes"]}
        selected = [agent_id for agent_id in agent_ids if agent_id in workflow_ids]
        if not selected:
            raise ValueError("请选择当前工作流中的返工Agent")
        run["human_rework_count"] = int(run.get("human_rework_count", 0)) + 1
        run["final_acceptance"] = {
            "status": "revision_requested", "feedback": feedback, "agent_ids": selected,
            "requested_at": utc_now(),
        }
        run["status"] = "reworking"
        self.save(run)
        self.tasks[run_id] = asyncio.create_task(self._execute_final_rework(run_id, feedback, selected))
        return run

    async def _execute_final_rework(self, run_id: str, feedback: str, selected: list[str]) -> None:
        run = db.get("runs", run_id)
        if not run:
            return
        try:
            nodes = {node["id"]: node for node in run["workflow_snapshot"]["nodes"]}
            completed: dict[str, str] = {}
            for item in run.get("node_runs", []):
                if item.get("status") == "completed" and item.get("output"):
                    completed[item["node_id"]] = item["output"]
            previous_draft = completed.get("writer", run.get("final_output") or "")
            run["loop_count"] = int(run.get("loop_count", 0)) + 1
            order = ["planner", "literature", "analyst"]
            for node_id in order:
                if node_id in selected and node_id in nodes:
                    completed[node_id] = await self._execute_node(run, nodes[node_id], completed, feedback=feedback, rework=True)
            completed["writer"] = await self._execute_node(
                run, nodes["writer"], completed, feedback=feedback, rework=True, previous_output=previous_draft,
            )
            if "fact-checker" in nodes:
                completed["fact-checker"] = await self._execute_node(run, nodes["fact-checker"], completed, feedback=feedback, rework=True)
            completed["reviewer"] = await self._execute_node(run, nodes["reviewer"], completed, feedback=feedback, rework=True)
            run["validation"] = enforce_deliverable_validation(
                run, normalize_validation(_safe_json(completed["reviewer"])), completed.get("writer", ""),
            )
            run["score"] = run["validation"]["score"]
            run["final_output"] = completed["writer"]
            run["latest_score"] = run["score"]
            run["selected_loop"] = run["loop_count"]
            candidate_score = run["score"]
            candidate_loop = run["loop_count"]
            select_best_result(run)
            run["delivery_metrics"] = evaluate_deliverable(run)
            run["status"] = "completed"
            run["final_acceptance"] = {
                **(run.get("final_acceptance") or {}), "status": "revised", "ready_at": utc_now(),
                "candidate_score": candidate_score, "adopted_score": run["score"],
                "improvement_adopted": run.get("selected_loop") == candidate_loop,
            }
            run["finished_at"] = utc_now()
            self.save(run)
            await self.emit(run_id, "run.completed", {"status": run["status"], "score": run["score"]})
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = str(exc)[:500]
            run["finished_at"] = utc_now()
            self.save(run)

    def _final_review_run(self, run_id: str) -> dict:
        run = db.get("runs", run_id)
        if not run:
            raise ValueError("任务不存在")
        if run["status"] not in {"completed", "waiting_final_acceptance", "needs_review"}:
            raise ValueError("只有已完成任务可以提交人工返工")
        return run


run_manager = RunManager()

