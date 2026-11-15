from __future__ import annotations

import ast
import operator
from pathlib import Path


class LocalKnowledgeTool:
    """Small, dependency-free keyword retrieval for text/markdown knowledge files."""

    def __init__(self, root: str = "knowledge") -> None:
        self.root = Path(root)

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        terms = {term.lower() for term in query.split() if len(term) > 1}
        matches = []
        if not self.root.exists():
            return matches
        for path in self.root.rglob("*"):
            if path.suffix.lower() not in {".txt", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = sum(text.lower().count(term) for term in terms)
            if score:
                matches.append({"source": str(path), "score": str(score), "snippet": text[:500]})
        return sorted(matches, key=lambda item: int(item["score"]), reverse=True)[:limit]


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

