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
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def rework_improved(previous_score: int, candidate_score: int) -> bool:
    """Continue automatic rework only when the candidate improves the audited score."""
    return candidate_score > previous_score


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
        candidates.append((int(validation["score"]), int(review.get("loop", 0)), validation, review))
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

    best_output = writer_runs[-1]["output"]
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


def evaluate_deliverable(run: dict) -> dict:
    """Compute deterministic citation and explicit-constraint acceptance metrics."""
    output = run.get("final_output") or ""
    evidence: dict[str, dict] = {}
    for node_run in run.get("node_runs", []):
        for call in node_run.get("tool_calls", []):
            if call.get("tool") not in {"local_knowledge", "local_knowledge_recheck"}:
                continue
            for item in call.get("results", []):
                key = f"{item.get('source', '')}:{item.get('chunk', '')}"
                evidence[key] = item
    cited = [
        item for item in evidence.values()
        if (item.get("url") and item["url"] in output) or (item.get("title") and item["title"] in output)
    ]
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


class RunManager:
    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancel_flags: set[str] = set()

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

            validation = normalize_validation(_safe_json(completed["reviewer"]))
            run["validation"] = validation
            run["score"] = int(validation.get("score", 0))
            while run["score"] < workflow["quality_threshold"] and run["loop_count"] < workflow["max_loop_count"]:
                self._assert_not_cancelled(run_id)
                previous_score = int(run["score"])
                run["loop_count"] += 1
                await self.emit(run_id, "run.rework", {"loop_count": run["loop_count"], "issues": validation.get("issues", [])})
                feedback = (
                    f"上一轮统一量表评分：{previous_score}分。只修复下列影响验收的关键问题，"
                    "不得扩展无关主题、增加重复免责声明或把核验过程写入报告正文。\n"
                    + "\n".join([*validation.get("issues", []), *validation.get("suggestions", [])])
                )
                previous_draft = completed.get("writer", "")
                completed["writer"] = await self._execute_node(
                    run, nodes["writer"], completed, feedback=feedback, rework=True,
                    previous_output=previous_draft,
                )
                if "fact-checker" in nodes:
                    completed["fact-checker"] = await self._execute_node(run, nodes["fact-checker"], completed, feedback=feedback, rework=True)
                completed["reviewer"] = await self._execute_node(run, nodes["reviewer"], completed, feedback=feedback, rework=True)
                validation = normalize_validation(_safe_json(completed["reviewer"]))
                run["validation"] = validation
                run["score"] = int(validation.get("score", 0))
                self.save(run)
                if not rework_improved(previous_score, run["score"]):
                    await self.emit(run_id, "run.rework_stopped", {
                        "reason": "score_not_improved", "previous_score": previous_score,
                        "candidate_score": run["score"], "loop_count": run["loop_count"],
                    })
                    break

            run["final_output"] = completed.get("writer")
            select_best_result(run)
            run["delivery_metrics"] = evaluate_deliverable(run)
            run["status"] = "completed"
            run["progress"] = 100
            run["finished_at"] = utc_now()
            self.save(run)
            await self.emit(run_id, "run.completed", {"status": run["status"], "score": run["score"]})
        except asyncio.CancelledError:
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
        prompt, tool_calls = await agent_logic.prepare_async(node["agent_id"], run["task"], prompt)
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
            run["validation"] = normalize_validation(_safe_json(completed["reviewer"]))
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

