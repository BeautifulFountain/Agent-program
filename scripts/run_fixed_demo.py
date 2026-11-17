"""Run the canonical real-model demo and persist its acceptance summary."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import db
from backend.engine import evaluate_deliverable, run_manager
from backend.llm import llm
from backend.seed import seed_defaults


TASK = (
    "撰写一份约1500字的研究报告，分析生成式人工智能在程序设计、代码调试、课程作业和毕业设计中的应用价值、"
    "学习风险与评价挑战，并提出面向高校计算机专业的教学使用规范。要求覆盖学习效果、代码可靠性、学术诚信、"
    "隐私安全和教师监督，不得虚构调查结果。"
)
CONFIRMATION = (
    "研究对象为高校计算机专业教学场景；面向专业教师、教学管理人员与学生；采用公开学术资料、政策和规范性文件；"
    "不生成虚构的学习效果数据；报告包含标题、摘要、关键词、研究背景、研究方法、典型应用、风险与评价挑战、"
    "教学使用规范、结论与建议、参考来源；关键事实保留完整来源链接；输出正式Markdown并可导出Word。"
)


async def main() -> None:
    if llm.mock:
        raise RuntimeError("固定演示必须使用真实模型，当前仍为 Mock 模式")
    db.initialize()
    seed_defaults(db)
    workflow = db.get("workflows", "research-demo")
    created = run_manager.create(TASK, workflow, "document")
    await run_manager.tasks[created["id"]]
    waiting = db.get("runs", created["id"])
    if waiting.get("status") != "waiting_approval":
        raise RuntimeError(f"需求确认状态异常：{waiting.get('status')} / {waiting.get('error')}")
    run_manager.approve(created["id"], CONFIRMATION)
    await run_manager.tasks[created["id"]]
    result = db.get("runs", created["id"])
    if result.get("final_output"):
        result["delivery_metrics"] = evaluate_deliverable(result)
        db.upsert("runs", result["id"], result)
    summary = {
        "run_id": result["id"], "status": result.get("status"), "score": result.get("score"),
        "selected_loop": result.get("selected_loop"), "loop_count": result.get("loop_count"),
        "token_usage": result.get("token_usage"), "delivery_metrics": result.get("delivery_metrics"),
        "error": result.get("error"),
    }
    destination = Path("docs/fixed-demo-result.json")
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
