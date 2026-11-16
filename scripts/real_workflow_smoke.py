"""Run one capped, real-model AgentFlow workflow for integration verification."""

import asyncio
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import db
from backend.engine import run_manager
from backend.seed import seed_defaults


async def main() -> None:
    db.initialize()
    seed_defaults(db)
    workflow = deepcopy(db.get("workflows", "research-demo"))
    workflow["max_loop_count"] = 1
    run = run_manager.create(
        "撰写一份约1000字的研究简报，分析生成式人工智能在高校科研管理中的三个主要应用价值、三个主要风险及对应治理建议；仅使用可核验的一般性事实，不虚构调查数据。",
        workflow,
    )
    await run_manager.tasks[run["id"]]
    waiting = db.get("runs", run["id"])
    if waiting["status"] != "waiting_approval":
        raise RuntimeError(f"需求确认节点状态异常：{waiting['status']}")
    run_manager.approve(
        run["id"],
        "研究对象限定为高校科研管理部门；重点分析效率、质量、合规与数据安全；输出约1000字Markdown研究简报；不得虚构统计数据。",
    )
    await run_manager.tasks[run["id"]]
    result = db.get("runs", run["id"])
    print({
        "run_id": result["id"],
        "status": result["status"],
        "score": result.get("score"),
        "loops": result.get("loop_count"),
        "node_runs": len(result.get("node_runs", [])),
        "tokens": result.get("token_usage"),
        "has_output": bool(result.get("final_output")),
        "error": result.get("error"),
    })


if __name__ == "__main__":
    asyncio.run(main())
