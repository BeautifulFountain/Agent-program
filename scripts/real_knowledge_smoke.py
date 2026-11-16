"""Verify that real DeepSeek output cites retrieved local knowledge sources."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agent_logic import agent_logic
from backend.database import db
from backend.llm import llm
from backend.seed import seed_defaults


async def main() -> None:
    db.initialize()
    seed_defaults(db)
    agent = db.get("agents", "literature")
    task = "分析生成式人工智能用于高校科研管理时的数据安全、个人信息保护和科研诚信风险"
    prompt, calls = agent_logic.prepare("literature", task, "请形成简明证据综述，不超过800字。")
    output, tokens = await llm.complete(agent["system_prompt"], prompt)
    expected = ["生成式人工智能服务管理暂行办法", "数据安全法", "个人信息保护法", "科研失信行为调查处理规则"]
    cited = [title for title in expected if title in output]
    print({"tokens": tokens, "retrieved": calls[0]["result_count"], "cited": cited, "citation_count": len(cited), "output_chars": len(output)})
    if len(cited) < 3:
        raise RuntimeError("真实模型未充分引用本地知识库来源")


if __name__ == "__main__":
    asyncio.run(main())
