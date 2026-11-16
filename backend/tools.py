from __future__ import annotations

import ast
import operator
import re
from pathlib import Path


class LocalKnowledgeTool:
    """Dependency-free Chinese/English chunk retrieval with source metadata."""

    def __init__(self, root: str = "knowledge") -> None:
        self.root = Path(root)

    @staticmethod
    def _terms(text: str) -> set[str]:
        terms: set[str] = set()
        for token in re.findall(r"[a-zA-Z0-9_-]+|[\u4e00-\u9fff]+", text.lower()):
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                if 2 <= len(token) <= 8:
                    terms.add(token)
                for size in (2, 3, 4):
                    terms.update(token[index:index + size] for index in range(len(token) - size + 1))
            elif len(token) > 1:
                terms.add(token)
        return terms - {"以及", "进行", "相关", "可以", "研究", "报告", "分析", "一个", "形成"}

    @staticmethod
    def _metadata(text: str, path: Path) -> tuple[dict[str, str], str]:
        metadata = {"title": path.stem, "organization": "", "published_at": "", "url": ""}
        if text.startswith("---\n") and "\n---\n" in text[4:]:
            header, body = text[4:].split("\n---\n", 1)
            for line in header.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    if key.strip() in metadata:
                        metadata[key.strip()] = value.strip().strip('"')
            return metadata, body
        return metadata, text

    @staticmethod
    def _chunks(text: str, size: int = 900) -> list[str]:
        sections = re.split(r"(?=^#{1,3}\s)", text, flags=re.MULTILINE)
        return [section[start:start + size].strip() for section in sections if section.strip() for start in range(0, len(section.strip()), size)]

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        terms = self._terms(query)
        matches: list[dict[str, str]] = []
        if not self.root.exists():
            return matches
        for path in self.root.rglob("*"):
            if path.suffix.lower() not in {".txt", ".md"}:
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            metadata, text = self._metadata(raw, path)
            title = metadata["title"].lower()
            for index, chunk in enumerate(self._chunks(text)):
                lowered = chunk.lower()
                score = sum((1 + min(len(term), 6)) * lowered.count(term) for term in terms)
                score += sum(8 * (1 + min(len(term), 6)) for term in terms if term in title)
                if score:
                    matches.append({"source": str(path), "title": metadata["title"], "organization": metadata["organization"], "published_at": metadata["published_at"], "url": metadata["url"], "chunk": str(index + 1), "score": str(score), "snippet": chunk[:700]})
        ranked = sorted(matches, key=lambda item: int(item["score"]), reverse=True)
        selected: list[dict[str, str]] = []
        per_source: dict[str, int] = {}
        for item in ranked:
            if per_source.get(item["source"], 0) >= 1:
                continue
            selected.append(item)
            per_source[item["source"]] = per_source.get(item["source"], 0) + 1
            if len(selected) >= limit:
                break
        return selected


class CalculatorTool:
    OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}

    def calculate(self, expression: str) -> float:
        def evaluate(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in self.OPS:
                return self.OPS[type(node.op)](evaluate(node.left), evaluate(node.right))
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                return -evaluate(node.operand)
            raise ValueError("仅支持基础算术表达式")
        return float(evaluate(ast.parse(expression, mode="eval").body))

