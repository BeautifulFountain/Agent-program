"""Run capped real-model comparisons for additional research task types.

Each scenario uses the same model and reviewer for three methods:
single writer, fixed serial planner/writer, and AgentFlow multi-agent workflow.
The multi-agent workflow disables automatic rework so that one run cannot
consume an uncontrolled number of model calls during benchmarking.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent_logic import agent_logic
from backend.database import db
from backend.engine import _safe_json, normalize_validation, run_manager
from backend.llm import llm
from backend.seed import seed_defaults


SCENARIOS = {
    "governance": {
        "task": "撰写一份约1000字的研究简报，分析生成式人工智能在高校科研管理中的三个主要应用价值、三个主要风险及对应治理建议；仅使用可核验的一般性事实，不虚构调查数据。",
        "confirmation": "研究对象限定为高校科研管理部门；重点分析效率、质量、合规与数据安全；引用可核验来源；输出约1000字Markdown研究简报；不得虚构统计数据。",
    },
    "analysis": {
        "task": "为某高校研究生生成式人工智能工具使用调查设计一份约1000字、可复现的数据分析方案，包括变量定义、数据清洗、描述统计、组间比较、稳健性检查和结果呈现；不得虚构数据或分析结果。",
        "confirmation": "研究对象为某高校在读研究生；只设计分析方案，不生成调查结果；区分使用率、使用频率、使用场景和付费情况；输出Markdown；明确统计方法的适用条件与局限。",
    },
    "integrity": {
        "task": "撰写一份约1000字的风险评估简报，分析高校使用生成式人工智能辅助科研项目申报材料审核时的数据安全、个人信息保护、学术诚信和管理责任风险，并提出可执行的分级治理措施。",
        "confirmation": "面向高校科研管理部门；重点覆盖敏感材料处理、人工复核、使用披露、权限与日志；只引用知识库中可追溯的政策原则，不编造法条、案例或统计数据；输出Markdown。",
    },
}


async def call(agent_id: str, task: str, prompt: str, *, json_mode: bool = False) -> tuple[str, int, int]:
    agent = db.get("agents", agent_id)
    prepared, _ = agent_logic.prepare(agent_id, task, prompt)
    started = time.perf_counter()
    output, tokens = await llm.complete(agent["system_prompt"], prepared, json_mode=json_mode)
    return output, tokens, int((time.perf_counter() - started) * 1000)


async def review(task: str, confirmation: str, report: str, method: str) -> tuple[dict, int, int]:
    raw, tokens, duration = await call(
        "reviewer",
        task,
        f"原始任务：{task}\n人工确认：{confirmation}\n实验类型：{method}\n待评审完整报告：\n{report}",
        json_mode=True,
    )
    return normalize_validation(_safe_json(raw)), tokens, duration


async def run_single(task: str, confirmation: str) -> dict:
    report, tokens, duration = await call(
        "writer", task, f"原始任务：{task}\n人工确认：{confirmation}\n无其他Agent前序成果，请独立完成最终报告。"
    )
    validation, review_tokens, review_duration = await review(task, confirmation, report, "单Agent直接写作")
    return {
        "method": "单Agent",
        "score": validation["score"],
        "success": validation["score"] >= 80,
        "tokens": tokens + review_tokens,
        "duration_ms": duration + review_duration,
        "output_chars": len(report),
        "issues": validation["issues"][:3],
    }


async def run_serial(task: str, confirmation: str) -> dict:
    plan, plan_tokens, plan_duration = await call(
        "planner", task, f"原始任务：{task}\n人工确认：{confirmation}\n请制定固定串行执行计划。"
    )
    report, writer_tokens, writer_duration = await call(
        "writer", task, f"原始任务：{task}\n人工确认：{confirmation}\n前序固定计划：\n{plan}\n请据此完成最终报告。"
    )
    validation, review_tokens, review_duration = await review(task, confirmation, report, "固定串行：规划→写作")
    return {
        "method": "固定串行",
        "score": validation["score"],
        "success": validation["score"] >= 80,
        "tokens": plan_tokens + writer_tokens + review_tokens,
        "duration_ms": plan_duration + writer_duration + review_duration,
        "output_chars": len(report),
        "issues": validation["issues"][:3],
    }


async def run_multi(task: str, confirmation: str) -> dict:
    workflow = deepcopy(db.get("workflows", "research-demo"))
    workflow["max_loop_count"] = 0
    created = run_manager.create(task, workflow)
    await run_manager.tasks[created["id"]]
    waiting = db.get("runs", created["id"])
    if waiting["status"] != "waiting_approval":
        raise RuntimeError(f"需求确认节点状态异常：{waiting['status']}")
    run_manager.approve(created["id"], confirmation)
    await run_manager.tasks[created["id"]]
    result = db.get("runs", created["id"])
    return {
        "method": "多Agent动态协作",
        "score": result.get("score") or 0,
        "success": result.get("status") == "completed" and (result.get("score") or 0) >= 80,
        "tokens": result.get("token_usage") or 0,
        "duration_ms": sum(item.get("duration_ms") or 0 for item in result.get("node_runs", [])),
        "output_chars": len(result.get("final_output") or ""),
        "issues": (result.get("validation") or {}).get("issues", [])[:3],
        "run_id": result["id"],
        "status": result.get("status"),
        "error": result.get("error"),
        "delivery_metrics": result.get("delivery_metrics"),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args()
    db.initialize()
    seed_defaults(db)
    scenario = SCENARIOS[args.scenario]
    task = scenario["task"]
    confirmation = scenario["confirmation"]
    results = [
        await run_single(task, confirmation),
        await run_serial(task, confirmation),
        await run_multi(task, confirmation),
    ]
    print(json.dumps({
        "scenario": args.scenario,
        "task": task,
        "model": "deepseek-chat",
        "threshold": 80,
        "results": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
