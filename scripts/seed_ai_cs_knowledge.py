"""Build a traceable 200-document AI and computer-science starter library.

The script uses OpenAlex public metadata, keeps works with abstracts, ranks by
citation count, deduplicates by DOI/OpenAlex URL, and writes through the same
knowledge API used by runtime external retrieval.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx

from backend.external_knowledge import ExternalRecord, _openalex_abstract
from backend.tools import LocalKnowledgeTool


TOPICS = [
    ("人工智能基础", "artificial intelligence survey"),
    ("机器学习", "machine learning survey"),
    ("深度学习", "deep learning review"),
    ("生成式人工智能", "generative artificial intelligence large language models survey"),
    ("自然语言处理", "natural language processing survey"),
    ("计算机视觉", "computer vision survey"),
    ("多模态学习", "multimodal machine learning survey"),
    ("强化学习", "reinforcement learning survey"),
    ("知识图谱", "knowledge graph survey"),
    ("推荐系统", "recommender systems survey"),
    ("数据挖掘", "data mining survey"),
    ("数据库系统", "database systems survey"),
    ("信息检索", "information retrieval survey"),
    ("计算机网络", "computer networks survey"),
    ("网络与信息安全", "cybersecurity survey"),
    ("软件工程", "software engineering systematic literature review"),
    ("分布式与云计算", "distributed systems cloud computing survey"),
    ("边缘计算与物联网", "edge computing internet of things survey"),
    ("人机交互", "human computer interaction survey"),
    ("可信人工智能", "trustworthy artificial intelligence explainable AI survey"),
]


@dataclass
class Candidate:
    topic: str
    record: ExternalRecord


def existing_identities(tool: LocalKnowledgeTool) -> set[str]:
    identities: set[str] = set()
    for document in tool.list_documents():
        url = str(document.get("url") or "").strip().lower()
        if url:
            identities.add(url.removeprefix("https://doi.org/"))
    return identities


async def fetch_topic(client: httpx.AsyncClient, topic: str, query: str, per_page: int) -> list[Candidate]:
    params = {
        "search": query,
        "filter": "has_abstract:true,is_retracted:false",
        "sort": "cited_by_count:desc",
        "per-page": per_page,
        "select": "id,doi,title,publication_date,publication_year,primary_location,authorships,cited_by_count,abstract_inverted_index",
    }
    response = None
    for attempt in range(6):
        response = await client.get("https://api.openalex.org/works", params=params)
        if response.status_code != 429:
            break
        await asyncio.sleep(min(12, 1.5 * (attempt + 1)))
    assert response is not None
    response.raise_for_status()
    candidates: list[Candidate] = []
    for item in response.json().get("results", []):
        doi = (item.get("doi") or "").removeprefix("https://doi.org/")
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        authors = ", ".join(
            author.get("author", {}).get("display_name", "")
            for author in item.get("authorships", [])[:10]
            if author.get("author", {}).get("display_name")
        )
        record = ExternalRecord(
            provider="OpenAlex",
            title=str(item.get("title") or "").strip(),
            summary=_openalex_abstract(item.get("abstract_inverted_index")),
            url=f"https://doi.org/{doi}" if doi else str(item.get("id") or ""),
            published_at=str(item.get("publication_date") or item.get("publication_year") or ""),
            organization=str(source.get("display_name") or "OpenAlex"),
            doi=doi,
            authors=authors,
            cited_by_count=item.get("cited_by_count"),
        )
        if record.title and len(record.summary) >= 120 and record.url:
            candidates.append(Candidate(topic, record))
    return candidates


async def seed(target: int, root: str) -> None:
    tool = LocalKnowledgeTool(root)
    current = tool.list_documents()
    needed = max(0, target - len(current))
    if not needed:
        print(f"Knowledge library already contains {len(current)} documents (target {target}).")
        return

    timeout = httpx.Timeout(35, connect=15)
    headers = {"User-Agent": "AgentFlow/0.2 knowledge seeder (OpenAlex public API)"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        batches = []
        for topic, query in TOPICS:
            batches.append(await fetch_topic(client, topic, query, max(28, needed // len(TOPICS) + 18)))
            await asyncio.sleep(0.35)

    known = existing_identities(tool)
    selected: list[Candidate] = []
    # Round-robin selection maintains broad subject coverage instead of allowing
    # one popular discipline to dominate the starter collection.
    for offset in range(max(map(len, batches), default=0)):
        for batch in batches:
            if offset >= len(batch) or len(selected) >= needed:
                continue
            candidate = batch[offset]
            identity = candidate.record.identity.strip().lower()
            canonical = identity.removeprefix("https://doi.org/")
            if canonical in known:
                continue
            known.add(canonical)
            selected.append(candidate)

    if len(selected) < needed:
        raise RuntimeError(f"Only found {len(selected)} unique records; {needed} are required.")

    for candidate in selected:
        record = candidate.record
        content = record.markdown() + f"\n\n## 主题分类\n\n{candidate.topic}\n"
        tool.add_external_document(
            record.provider,
            record.identity,
            record.title,
            content,
            {
                "organization": record.organization or record.provider,
                "published_at": record.published_at,
                "url": record.url,
            },
        )
    documents = tool.list_documents()
    categories = {candidate.topic for candidate in selected}
    print(f"Added {len(selected)} documents across {len(categories)} topics; total={len(documents)}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=200)
    parser.add_argument("--root", default="knowledge")
    args = parser.parse_args()
    Path(args.root).mkdir(parents=True, exist_ok=True)
    asyncio.run(seed(args.target, args.root))


if __name__ == "__main__":
    main()
