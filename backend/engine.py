from __future__ import annotations

import asyncio
import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from backend.database import db
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


def normalize_validation(value: dict) -> dict:
    """Normalize common reviewer field variants into the platform contract."""
    dimensions = value.get("dimensions") or value.get("dimension_scores") or {}
    issues = value.get("issues") or value.get("problems") or []
    suggestions = value.get("suggestions") or value.get("improvement_suggestions") or []
    if isinstance(issues, str):
        issues = [issues]
    if isinstance(suggestions, str):
        suggestions = [suggestions]
    if not isinstance(dimensions, dict):
        dimensions = {}
    return {
        "score": int(value.get("score", value.get("total_score", 0)) or 0),
        "dimensions": dimensions,
        "issues": issues if isinstance(issues, list) else [],
        "suggestions": suggestions if isinstance(suggestions, list) else [],
    }


class RunManager:
    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancel_flags: set[str] = set()

    def create(self, task: str, workflow: dict) -> dict:
        run_id = uuid4().hex[:12]
        now = utc_now()
        run = {
            "id": run_id, "task": task, "workflow_id": workflow["id"], "workflow_snapshot": deepcopy(workflow),
            "status": "queued", "progress": 0, "score": None, "loop_count": 0, "token_usage": 0,
            "started_at": now, "finished_at": None, "created_at": now, "updated_at": now,
            "node_runs": [], "final_output": None, "validation": None, "error": None,
        }
        db.upsert("runs", run_id, run)
        self.tasks[run_id] = asyncio.create_task(self.execute(run_id))
        return run

    async def emit(self, run_id: str, event_type: str, data: dict) -> None:
        db.add_event(run_id, {"type": event_type, "data": data, "created_at": utc_now()})

    def save(self, run: dict) -> None:
        run["updated_at"] = utc_now()
        db.upsert("runs", run["id"], run)

    async def execute(self, run_id: str) -> None:
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
            pending = set(nodes)
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

            validation = normalize_validation(_safe_json(completed["reviewer"]))
            run["validation"] = validation
            run["score"] = int(validation.get("score", 0))
            while run["score"] < workflow["quality_threshold"] and run["loop_count"] < workflow["max_loop_count"]:
                self._assert_not_cancelled(run_id)
                run["loop_count"] += 1
                await self.emit(run_id, "run.rework", {"loop_count": run["loop_count"], "issues": validation.get("issues", [])})
                feedback = "\n".join(validation.get("suggestions", []))
                completed["writer"] = await self._execute_node(run, nodes["writer"], completed, feedback=feedback, rework=True)
                completed["fact-checker"] = await self._execute_node(run, nodes["fact-checker"], completed, feedback=feedback, rework=True)
                completed["reviewer"] = await self._execute_node(run, nodes["reviewer"], completed, feedback=feedback, rework=True)
                validation = normalize_validation(_safe_json(completed["reviewer"]))
                run["validation"] = validation
                run["score"] = int(validation.get("score", 0))
                self.save(run)

            run["final_output"] = completed.get("writer")
            run["status"] = "completed" if run["score"] >= workflow["quality_threshold"] else "needs_review"
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

    async def _execute_node(self, run: dict, node: dict, completed: dict[str, str], feedback: str = "", rework: bool = False) -> str:
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
        if feedback:
            prompt += f"\n评审反馈：{feedback}\n请针对反馈修订。"
        node_run["input"] = prompt
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
                run["token_usage"] += tokens
                node_run.update(status="completed", output=output, retry_count=attempt, finished_at=utc_now())
                if node["kind"] == "validator":
                    node_run["score"] = _safe_json(output).get("score")
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


run_manager = RunManager()

