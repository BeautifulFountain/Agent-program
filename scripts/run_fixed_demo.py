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
    "撰写一份约1500字的科研方法报告，分析大语言模型在文献检索、主题归纳、研究空白识别和综述写作中的应用价值与局限，"
    "并提出一套可复现的人机协作文献综述流程。要求说明检索策略、来源筛选、引用核验、幻觉控制和人工复核机制，"
    "引用可核验的经典综述与学术资料。"
)
CONFIRMATION = (
    "报告定位为科研方法类研究成果；重点展示OpenAlex、Crossref和arXiv检索及知识自动入库；检索策略需包含关键词、"
    "来源类型、筛选标准和去重方法；不得把平台未检出等同于学术研究空白；报告包含标题、摘要、关键词、研究背景、"
    "研究方法、人机协作流程、应用价值、风险与局限、结论与建议、参考来源；关键事实保留完整来源链接；"
    "输出正式Markdown并可导出Word。"
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
