"""Run real-model single-agent and fixed-serial baselines against a saved multi-agent run."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent_logic import agent_logic
from backend.database import db
from backend.engine import _safe_json, normalize_validation
from backend.llm import llm
from backend.seed import seed_defaults


TASK = "撰写一份约1000字的研究简报，分析生成式人工智能在高校科研管理中的三个主要应用价值、三个主要风险及对应治理建议；仅使用可核验的一般性事实，不虚构调查数据。"
CONFIRMATION = "研究对象限定为高校科研管理部门；重点分析效率、质量、合规与数据安全；输出约1000字Markdown研究简报；不得虚构统计数据。"
MULTI_RUN_ID = "7c64929198f3"


async def complete(agent_id: str, base_prompt: str, *, json_mode: bool = False) -> tuple[str, int, int]:
    agent = db.get("agents", agent_id)
    prompt, _ = agent_logic.prepare(agent_id, TASK, base_prompt)
    started = time.perf_counter()
    output, tokens = await llm.complete(agent["system_prompt"], prompt, json_mode=json_mode)
    return output, tokens, int((time.perf_counter() - started) * 1000)


async def review(report: str, context: str) -> tuple[dict, int, int]:
    output, tokens, duration = await complete(
        "reviewer",
        f"原始任务：{TASK}\n人工确认：{CONFIRMATION}\n实验类型：{context}\n待评审完整报告：\n{report}",
        json_mode=True,
    )
    return normalize_validation(_safe_json(output)), tokens, duration


async def single_agent() -> dict:
    report, writer_tokens, writer_ms = await complete(
        "writer", f"原始任务：{TASK}\n人工确认：{CONFIRMATION}\n无其他Agent前序成果，请独立完成最终报告。"
    )
    validation, review_tokens, review_ms = await review(report, "单Agent直接写作")
    return {"method": "单Agent", "score": validation["score"], "success": validation["score"] >= 80, "tokens": writer_tokens + review_tokens, "duration_ms": writer_ms + review_ms, "output_chars": len(report), "issues": validation["issues"][:3]}


async def fixed_serial() -> dict:
    plan, plan_tokens, plan_ms = await complete("planner", f"原始任务：{TASK}\n人工确认：{CONFIRMATION}\n请制定固定串行执行计划。")
    report, writer_tokens, writer_ms = await complete("writer", f"原始任务：{TASK}\n人工确认：{CONFIRMATION}\n前序固定计划：\n{plan}\n请据此完成最终报告。")
    validation, review_tokens, review_ms = await review(report, "固定串行：规划→写作")
    return {"method": "固定串行", "score": validation["score"], "success": validation["score"] >= 80, "tokens": plan_tokens + writer_tokens + review_tokens, "duration_ms": plan_ms + writer_ms + review_ms, "output_chars": len(report), "issues": validation["issues"][:3]}


def multi_agent() -> dict:
    run = db.get("runs", MULTI_RUN_ID)
    if not run:
        raise RuntimeError(f"找不到多Agent基准任务：{MULTI_RUN_ID}")
    return {"method": "多Agent动态协作", "score": run["score"], "success": run["score"] >= 80, "tokens": run["token_usage"], "duration_ms": sum(item.get("duration_ms") or 0 for item in run["node_runs"]), "output_chars": len(run.get("final_output") or ""), "issues": (run.get("validation") or {}).get("issues", [])[:3], "run_id": run["id"]}


async def main() -> None:
    db.initialize()
    seed_defaults(db)
    results = [await single_agent(), await fixed_serial(), multi_agent()]
    print(json.dumps({"task": TASK, "model": "deepseek-chat", "threshold": 80, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
