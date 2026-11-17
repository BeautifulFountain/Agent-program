"""Repeat three real-model scenarios and summarize quality, variance and cost."""
from __future__ import annotations

import asyncio
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from real_benchmark_suite import SCENARIOS, db, llm, run_multi, run_serial, run_single, seed_defaults


REPETITIONS = 3
OUTPUT = Path("docs/repeated-real-benchmark-results.json")
REPORT = Path("docs/repeated-real-benchmark-report.md")


def summarize(rows: list[dict]) -> dict:
    scores = [row["score"] for row in rows]
    tokens = [row["tokens"] for row in rows]
    durations = [row["duration_ms"] for row in rows]
    return {
        "runs": len(rows), "success_rate": round(sum(bool(row["success"]) for row in rows) / len(rows) * 100, 1),
        "score_mean": round(statistics.mean(scores), 2),
        "score_stdev": round(statistics.pstdev(scores), 2),
        "score_min": min(scores), "score_max": max(scores),
        "token_mean": round(statistics.mean(tokens)),
        "duration_mean_ms": round(statistics.mean(durations)),
        "failures": [row for row in rows if not row["success"]],
    }


def write_report(payload: dict) -> None:
    lines = [
        "# AgentFlow 三场景真实模型重复实验", "",
        f"- 执行时间：{payload['generated_at']}", f"- 模型：{payload['model']}",
        f"- 每场景重复：{REPETITIONS} 次", "- 达标阈值：80 分", "",
        "## 汇总", "",
        "| 场景 | 方法 | 质量均值 | 标准差 | 范围 | 成功率 | 平均Token | 平均耗时 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario, methods in payload["summary"].items():
        for method, item in methods.items():
            lines.append(
                f"| {scenario} | {method} | {item['score_mean']} | {item['score_stdev']} | "
                f"{item['score_min']}–{item['score_max']} | {item['success_rate']}% | "
                f"{item['token_mean']} | {item['duration_mean_ms']/1000:.2f}秒 |"
            )
    lines.extend(["", "## 失败案例", ""])
    failures = 0
    for scenario, methods in payload["summary"].items():
        for method, item in methods.items():
            for row in item["failures"]:
                failures += 1
                lines.append(f"- **{scenario} / {method} / 第{row['repetition']}次**：{row['score']}分；" + "；".join(row.get("issues") or [row.get("error") or "未提供错误详情"]))
    if not failures:
        lines.append("- 无低于80分的运行。")
    lines.extend(["", "## 说明", "", "所有方法使用相同 DeepSeek 模型与质量评审协议；多 Agent 对比关闭自动返工，以控制方法间调用预算并比较初稿链路。"])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    if llm.mock:
        raise RuntimeError("重复实验必须使用真实模型")
    db.initialize()
    seed_defaults(db)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "model": "deepseek-chat", "repetitions": REPETITIONS, "results": [], "summary": {}}
    for scenario_name, scenario in SCENARIOS.items():
        for repetition in range(1, REPETITIONS + 1):
            print(f"START {scenario_name} repetition {repetition}/{REPETITIONS}", flush=True)
            for runner in (run_single, run_serial, run_multi):
                try:
                    result = await runner(scenario["task"], scenario["confirmation"])
                except Exception as exc:
                    result = {"method": runner.__name__, "score": 0, "success": False, "tokens": 0, "duration_ms": 0, "issues": [], "error": str(exc)[:300]}
                result.update({"scenario": scenario_name, "repetition": repetition})
                payload["results"].append(result)
                OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"DONE {scenario_name} #{repetition} {result['method']} score={result['score']} tokens={result['tokens']}", flush=True)
    for scenario_name in SCENARIOS:
        payload["summary"][scenario_name] = {}
        methods = {row["method"] for row in payload["results"] if row["scenario"] == scenario_name}
        for method in sorted(methods):
            rows = [row for row in payload["results"] if row["scenario"] == scenario_name and row["method"] == method]
            payload["summary"][scenario_name][method] = summarize(rows)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
