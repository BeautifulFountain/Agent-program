from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

import httpx

from backend.config import settings
from backend.tools import LocalKnowledgeTool


@dataclass
class ExternalRecord:
    provider: str
    title: str
    summary: str
    url: str
    published_at: str = ""
    organization: str = ""
    doi: str = ""
    authors: str = ""
    cited_by_count: int | None = None

    @property
    def identity(self) -> str:
        return self.doi or self.url or f"{self.provider}:{self.title}"

    def markdown(self) -> str:
        lines = [f"# {self.title}", "", f"- 外部数据源：{self.provider}"]
        if self.authors:
            lines.append(f"- 作者：{self.authors}")
        if self.published_at:
            lines.append(f"- 发布日期：{self.published_at}")
        if self.doi:
            lines.append(f"- DOI：{self.doi}")
        if self.cited_by_count is not None:
            lines.append(f"- 被引次数：{self.cited_by_count}")
        lines.extend([f"- 原始链接：{self.url}", "", "## 摘要或检索片段", "", self.summary or "外部接口未提供摘要，请通过原始链接核验全文。"])
        return "\n".join(lines)


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _openalex_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions = [(position, word) for word, values in index.items() for position in values]
    return " ".join(word for _, word in sorted(positions))


class ExternalKnowledgeService:
    """Search public scholarly APIs, normalize metadata, and persist traceable evidence."""

    def __init__(self, knowledge: LocalKnowledgeTool) -> None:
        self.knowledge = knowledge

    @staticmethod
    def passes_relevance_threshold(score: int, summary: str) -> bool:
        return score >= 50 and bool(summary.strip())

    @staticmethod
    def default_searches(task: str) -> list[dict[str, Any]]:
        """Deterministic fallback used only when dynamic search planning fails."""
        return [
            {"query": query, "must_include_groups": []}
            for query in ExternalKnowledgeService.focus_queries(task)
        ]

    @staticmethod
    def normalize_searches(value: Any, task: str) -> list[dict[str, Any]]:
        searches = value.get("searches", []) if isinstance(value, dict) else []
        normalized = []
        for item in searches[:4]:
            if not isinstance(item, dict):
                continue
            query = _clean(str(item.get("query") or ""))[:300]
            groups = []
            for group in item.get("must_include_groups", [])[:4]:
                if isinstance(group, list):
                    terms = [_clean(str(term)).lower()[:80] for term in group[:8] if _clean(str(term))]
                    if terms:
                        groups.append(terms)
            if len(query) >= 5:
                normalized.append({"query": query, "must_include_groups": groups})
        return normalized or ExternalKnowledgeService.default_searches(task)

    @staticmethod
    def relevant_to_search(title: str, summary: str, search: dict[str, Any]) -> bool:
        text = f"{title} {summary}".lower()
        if title.strip().lower().startswith("review for "):
            return False
        groups = search.get("must_include_groups") or []
        return all(any(term.lower() in text for term in group) for group in groups)

    async def assess_content_relevance(
        self, task_context: str, records: list[ExternalRecord],
    ) -> tuple[list[tuple[ExternalRecord, dict[str, Any]]], int]:
        """Judge task fit from title plus abstract, rather than accepting keyword hits alone."""
        if not records:
            return [], 0
        candidates = [
            {
                "index": index,
                "title": record.title,
                "abstract": record.summary[:1800],
                "source": record.provider,
                "published_at": record.published_at,
            }
            for index, record in enumerate(records[:30])
        ]
        try:
            from backend.llm import llm
            system = (
                "你是科研证据相关性审核器。仅依据题名和摘要判断候选文献能否支持研究任务，输出JSON。"
                "不能因共享宽泛关键词就判为相关；研究对象、核心问题和任务要求必须对应。"
                "若人工确认意见给出了明确年份范围，范围外文献必须判为reject；未给出明确范围时不得自行限制年份。"
                "摘要为空或无法判断正文内容时不得作为核心证据。每项输出index、decision、score、reason、"
                "supported_claims和limitations；decision只能是relevant或reject，score为0到100。"
            )
            prompt = (
                f"任务与已确认要求：\n{task_context[:6000]}\n\n候选文献：\n"
                + json.dumps(candidates, ensure_ascii=False)
                + "\n输出格式：{\"assessments\":[{\"index\":0,\"decision\":\"relevant\",\"score\":85,"
                  "\"reason\":\"...\",\"supported_claims\":[\"...\"],\"limitations\":[\"...\"]}]}"
            )
            raw, tokens = await llm.complete(system, prompt, json_mode=True)
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                start, end = raw.find("{"), raw.rfind("}")
                value = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
            assessments = {
                int(item.get("index")): item for item in value.get("assessments", [])
                if isinstance(item, dict) and str(item.get("index", "")).isdigit()
            }
            accepted = []
            for index, record in enumerate(records[:30]):
                assessment = assessments.get(index, {})
                score = max(0, min(100, int(assessment.get("score") or 0)))
                if assessment.get("decision") == "relevant" and self.passes_relevance_threshold(score, record.summary):
                    accepted.append((record, {
                        "relevance_score": score,
                        "relevance_reason": _clean(str(assessment.get("reason") or "")),
                        "supported_claims": assessment.get("supported_claims") or [],
                        "limitations": assessment.get("limitations") or [],
                    }))
            return accepted, tokens
        except Exception:
            accepted = []
            task_terms = LocalKnowledgeTool._terms(task_context)
            for record in records:
                content_terms = LocalKnowledgeTool._terms(f"{record.title} {record.summary}")
                overlap = task_terms & content_terms
                score = round(100 * len(overlap) / max(1, min(len(task_terms), 12)))
                if (
                    self.passes_relevance_threshold(score, record.summary)
                    and self.relevant_to_task(task_context, record.title, record.summary)
                ):
                    accepted.append((record, {
                        "relevance_score": score,
                        "relevance_reason": "语义审核不可用，已通过题名、摘要与任务要求的确定性内容重合检查",
                        "supported_claims": [],
                        "limitations": ["语义审核服务不可用，已退回确定性过滤"],
                    }))
            return accepted, 0

    @staticmethod
    def focus_query(task: str) -> str:
        """Translate verbose Chinese task instructions into a scholarly search intent."""
        lowered = task.lower()
        if ("大语言模型" in task or "llm" in lowered) and any(term in task for term in ("文献", "综述", "研究空白", "主题归纳")):
            return "large language models systematic literature review evidence synthesis literature search citation verification"
        if "计算机视觉" in task:
            return "computer vision systematic review survey"
        if "生成式人工智能" in task:
            return "generative artificial intelligence systematic review"
        return re.sub(r"\s+", " ", task.strip())[:500]

    @classmethod
    def focus_queries(cls, task: str) -> list[str]:
        primary = cls.focus_query(task)
        if ("大语言模型" in task or "llm" in task.lower()) and any(term in task for term in ("文献", "综述", "研究空白", "主题归纳")):
            return [
                "大语言模型 文献综述 证据综合 文献检索 引用核验",
                primary,
                "systematic literature review methodology PRISMA evidence synthesis literature screening citation",
            ]
        return [primary]

    @staticmethod
    def relevant_to_task(task: str, title: str, summary: str = "") -> bool:
        """Reject superficially matched records before they enter the durable library."""
        text = f"{title} {summary}".lower()
        if title.strip().lower().startswith("review for "):
            return False
        lowered = task.lower()
        if ("大语言模型" in task or "llm" in lowered) and any(term in task for term in ("文献", "综述", "研究空白", "主题归纳")):
            ai_terms = ("large language model", "llm", "generative ai", "artificial intelligence")
            review_terms = (
                "literature review", "systematic review", "scoping review", "evidence synthesis",
                "literature search", "citation", "bibliometric", "research synthesis", "review automation",
            )
            classic_terms = ("prisma", "cochrane", "systematic review methodology", "evidence synthesis", "literature screening")
            return (
                any(term in text for term in ai_terms) and any(term in text for term in review_terms)
            ) or any(term in text for term in classic_terms)
        return True

    async def search_and_ingest(self, query: str, searches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not settings.external_search_enabled:
            return {"query": query, "enabled": False, "providers": [], "imported": [], "duplicates": 0, "errors": []}
        search_specs = self.normalize_searches({"searches": searches or []}, query) if searches else self.default_searches(query)
        async with httpx.AsyncClient(timeout=18, follow_redirects=True, headers={"User-Agent": "AgentFlow/0.1 (research knowledge integration)"}) as client:
            calls = []
            labels: list[tuple[str, dict[str, Any]]] = []
            for search in search_specs:
                focused_query = search["query"]
                calls.extend([self._openalex(client, focused_query), self._crossref(client, focused_query), self._arxiv(client, focused_query)])
                labels.extend([("OpenAlex", search), ("Crossref", search), ("arXiv", search)])
                if settings.brave_search_api_key:
                    calls.append(self._brave(client, focused_query))
                    labels.append(("Brave Search", search))
            results = await asyncio.gather(*calls, return_exceptions=True)
        records: list[ExternalRecord] = []
        errors: list[str] = []
        providers = ["OpenAlex", "Crossref", "arXiv"] + (["Brave Search"] if settings.brave_search_api_key else [])
        discarded_irrelevant = 0
        for (provider, search), result in zip(labels, results):
            if isinstance(result, Exception):
                errors.append(f"{provider}: {_clean(str(result))[:160]}")
            else:
                for record in result:
                    if self.relevant_to_search(record.title, record.summary, search):
                        records.append(record)
                    else:
                        discarded_irrelevant += 1
        assessed, relevance_tokens = await self.assess_content_relevance(query, records)
        discarded_irrelevant += max(0, len(records) - len(assessed))
        imported: list[dict] = []
        duplicates = 0
        seen: set[str] = set()
        for record, assessment in assessed:
            identity = record.identity.strip().lower()
            if not identity or identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            document, created = self.knowledge.add_external_document(
                record.provider, record.identity, record.title, record.markdown(),
                {"organization": record.organization or record.provider, "published_at": record.published_at, "url": record.url},
            )
            if created:
                imported.append({
                    "id": document["id"], "provider": record.provider, "title": record.title,
                    "url": record.url, "doi": record.doi, **assessment,
                })
            else:
                duplicates += 1
        return {
            "query": query, "search_query": " | ".join(item["query"] for item in search_specs),
            "searches": search_specs, "enabled": True, "providers": providers,
            "found": len(records), "discarded_irrelevant": discarded_irrelevant,
            "imported": imported, "duplicates": duplicates, "errors": errors,
            "relevance_tokens": relevance_tokens,
        }

    async def _openalex(self, client: httpx.AsyncClient, query: str) -> list[ExternalRecord]:
        params: dict[str, str | int] = {"search": query, "per_page": settings.external_search_limit}
        if settings.openalex_api_key:
            params["api_key"] = settings.openalex_api_key
        response = await client.get("https://api.openalex.org/works", params=params)
        response.raise_for_status()
        records = []
        for item in response.json().get("results", []):
            doi = (item.get("doi") or "").removeprefix("https://doi.org/")
            location = item.get("primary_location") or {}
            source = location.get("source") or {}
            authors = ", ".join(entry.get("author", {}).get("display_name", "") for entry in item.get("authorships", [])[:8])
            records.append(ExternalRecord(
                provider="OpenAlex", title=_clean(item.get("title")), summary=_openalex_abstract(item.get("abstract_inverted_index")),
                url=doi and f"https://doi.org/{doi}" or item.get("id", ""), published_at=item.get("publication_date") or str(item.get("publication_year") or ""),
                organization=source.get("display_name") or "OpenAlex", doi=doi, authors=authors, cited_by_count=item.get("cited_by_count"),
            ))
        return [record for record in records if record.title and record.url]

    async def _crossref(self, client: httpx.AsyncClient, query: str) -> list[ExternalRecord]:
        params: dict[str, str | int] = {"query.bibliographic": query, "rows": settings.external_search_limit, "select": "DOI,title,author,published,container-title,abstract,URL,is-referenced-by-count"}
        if settings.crossref_mailto:
            params["mailto"] = settings.crossref_mailto
        response = await client.get("https://api.crossref.org/works", params=params)
        response.raise_for_status()
        records = []
        for item in response.json().get("message", {}).get("items", []):
            title = _clean(" ".join(item.get("title") or []))
            doi = item.get("DOI", "")
            date_parts = ((item.get("published") or {}).get("date-parts") or [[]])[0]
            published = "-".join(str(part) for part in date_parts)
            authors = ", ".join(" ".join(filter(None, [entry.get("given"), entry.get("family")])) for entry in item.get("author", [])[:8])
            records.append(ExternalRecord(
                provider="Crossref", title=title, summary=_clean(item.get("abstract")), url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
                published_at=published, organization=_clean(" ".join(item.get("container-title") or [])) or "Crossref", doi=doi, authors=authors,
                cited_by_count=item.get("is-referenced-by-count"),
            ))
        return [record for record in records if record.title and record.url]

    async def _arxiv(self, client: httpx.AsyncClient, query: str) -> list[ExternalRecord]:
        params = {"search_query": f'all:"{query}"', "start": 0, "max_results": settings.external_search_limit, "sortBy": "relevance"}
        response = await client.get("https://export.arxiv.org/api/query", params=params)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        atom = {"a": "http://www.w3.org/2005/Atom"}
        records = []
        for entry in root.findall("a:entry", atom):
            url = _clean(entry.findtext("a:id", default="", namespaces=atom))
            authors = ", ".join(_clean(node.findtext("a:name", default="", namespaces=atom)) for node in entry.findall("a:author", atom))
            records.append(ExternalRecord(
                provider="arXiv", title=_clean(entry.findtext("a:title", default="", namespaces=atom)),
                summary=_clean(entry.findtext("a:summary", default="", namespaces=atom)), url=url,
                published_at=_clean(entry.findtext("a:published", default="", namespaces=atom))[:10], organization="arXiv", authors=authors,
            ))
        return [record for record in records if record.title and record.url]

    async def _brave(self, client: httpx.AsyncClient, query: str) -> list[ExternalRecord]:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": settings.external_search_limit, "search_lang": "zh-hans"},
            headers={"X-Subscription-Token": settings.brave_search_api_key, "Accept": "application/json"},
        )
        response.raise_for_status()
        records = []
        for item in response.json().get("web", {}).get("results", []):
            records.append(ExternalRecord(provider="Brave Search", title=_clean(item.get("title")), summary=_clean(item.get("description")), url=item.get("url", ""), organization="网页检索"))
        return [record for record in records if record.title and record.url]
