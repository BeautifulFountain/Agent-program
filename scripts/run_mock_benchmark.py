"""Run three repeatable AgentFlow scenarios three times in isolated Mock mode."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RESULT_PATH = ROOT / "docs" / "mock-benchmark-results.json"
REPORT_PATH = ROOT / "docs" / "mock-benchmark-report.md"

SCENARIOS = [
    {
        "id": "governance",
        "name": "人工智能科研治理报告",
        "task": "分析人工智能辅助高校科研管理的应用价值、数据安全与伦理风险，并形成有来源边界的研究报告。",
        "approval": "覆盖科研管理部门，重点分析效率、质量、隐私、伦理与责任；只使用知识库证据，不虚构案例。",
    },
    {
        "id": "survey",
        "name": "高校学生AI使用调查方案",
        "task": "为高校学生生成式人工智能工具使用情况设计可复现调查与统计分析方案，包括变量、抽样、清洗、描述统计和局限。",
        "approval": "对象为本科生，采用分层抽样，指标包括使用率、频率、场景与付费；当前只形成方案，不虚构数据。",
    },
    {
        "id": "integrity",
        "name": "AI辅助科研诚信与合规",
        "task": "撰写AI辅助科研活动中的科研诚信、个人信息、科技伦理和证据可追溯风险报告，并提出平台治理措施。",
        "approval": "面向高校科研项目全生命周期，区分法律要求、伦理建议与工程控制，所有关键结论保留来源。",
    },
]


def aggregate(records: list[dict]) -> dict:
    scores = [item["score"] for item in records]
    tokens = [item["tokens"] for item in records]
    durations = [item["duration_ms"] for item in records]
    return {
        "runs": len(records),
        "success_rate": round(sum(item["success"] for item in records) / len(records), 4),
        "score_mean": round(statistics.mean(scores), 2),
        "score_stdev": round(statistics.pstdev(scores), 2),
        "token_mean": round(statistics.mean(tokens), 2),
        "token_stdev": round(statistics.pstdev(tokens), 2),
        "duration_ms_mean": round(statistics.mean(durations), 2),
        "duration_ms_stdev": round(statistics.pstdev(durations), 2),
        "failures": [item for item in records if not item["success"]],
    }


async def run_once(scenario: dict, repetition: int) -> dict:
    from backend.database import db
    from backend.engine import run_manager
    from backend.seed import seed_defaults

    db.initialize()
    seed_defaults(db)
    workflow = db.get("workflows", "research-demo")
    started = time.perf_counter()
    run = run_manager.create(scenario["task"], workflow)
    await run_manager.tasks[run["id"]]
    waiting = db.get("runs", run["id"])
    if waiting["status"] != "waiting_approval":
        return {
            "repetition": repetition,
            "run_id": run["id"],
            "success": False,
            "score": int(waiting.get("score") or 0),
            "tokens": int(waiting.get("token_usage") or 0),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "loops": int(waiting.get("loop_count") or 0),
            "node_runs": len(waiting.get("node_runs", [])),
            "error": waiting.get("error") or f"未进入人工确认：{waiting['status']}",
        }
    run_manager.approve(run["id"], scenario["approval"])
    await run_manager.tasks[run["id"]]
    result = db.get("runs", run["id"])
    success = result["status"] == "completed" and int(result.get("score") or 0) >= workflow["quality_threshold"]
    return {
        "repetition": repetition,
        "run_id": run["id"],
        "success": success,
        "score": int(result.get("score") or 0),
        "tokens": int(result.get("token_usage") or 0),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "loops": int(result.get("loop_count") or 0),
        "node_runs": len(result.get("node_runs", [])),
        "error": result.get("error"),
    }


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentflow-mock-", ignore_cleanup_errors=True) as folder:
        os.environ["DATABASE_PATH"] = str(Path(folder) / "benchmark.db")
        os.environ["LLM_MOCK"] = "true"
        os.environ["QUALITY_THRESHOLD"] = "80"
        os.environ["MAX_LOOP_COUNT"] = "3"

        scenario_results = []
        for scenario in SCENARIOS:
            records = []
            for repetition in range(1, 4):
                record = await run_once(scenario, repetition)
                records.append(record)
                print(f"{scenario['name']} #{repetition}: score={record['score']} tokens={record['tokens']} status={'PASS' if record['success'] else 'FAIL'}")
            scenario_results.append({**scenario, "runs": records, "summary": aggregate(records)})

        all_records = [record for scenario in scenario_results for record in scenario["runs"]]
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "mock",
            "quality_threshold": 80,
            "repetitions_per_scenario": 3,
            "scenario_count": len(SCENARIOS),
            "scenarios": scenario_results,
            "overall": aggregate(all_records),
        }
        RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        lines = [
            "# AgentFlow Mock稳定性基准", "", f"生成时间：{payload['generated_at']}", "",
            "每个复杂场景独立运行3次；使用临时SQLite数据库和Mock模型，不消耗API余额，也不污染演示任务。", "",
            "| 场景 | 成功率 | 质量分 均值±波动 | Token 均值±波动 | 耗时ms 均值±波动 | 失败数 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for item in scenario_results:
            value = item["summary"]
            lines.append(
                f"| {item['name']} | {value['success_rate'] * 100:.1f}% | {value['score_mean']:.2f} ± {value['score_stdev']:.2f} | "
                f"{value['token_mean']:.2f} ± {value['token_stdev']:.2f} | {value['duration_ms_mean']:.2f} ± {value['duration_ms_stdev']:.2f} | {len(value['failures'])} |"
            )
        overall = payload["overall"]
        lines += [
            "", "## 总体", "",
            f"- 成功率：{overall['success_rate'] * 100:.1f}%",
            f"- 质量分：{overall['score_mean']:.2f} ± {overall['score_stdev']:.2f}",
            f"- Token：{overall['token_mean']:.2f} ± {overall['token_stdev']:.2f}",
            f"- 耗时：{overall['duration_ms_mean']:.2f} ± {overall['duration_ms_stdev']:.2f} ms",
            f"- 失败案例：{len(overall['failures'])}", "",
            "> Mock结果用于验证工程链路、状态机和指标采集是否稳定，不代表真实模型的内容质量。真实模型实验应单独记录。", "",
        ]
        REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
