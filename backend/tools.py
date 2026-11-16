from __future__ import annotations

import ast
import base64
import binascii
import operator
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


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
            if path.suffix.lower() not in {".txt", ".md"} or path.name.lower() == "readme.md":
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

    def _document_id(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.root.resolve()).as_posix()
        return base64.urlsafe_b64encode(relative.encode("utf-8")).decode("ascii").rstrip("=")

    def _path_from_id(self, document_id: str) -> Path:
        padding = "=" * (-len(document_id) % 4)
        try:
            relative = base64.urlsafe_b64decode(document_id + padding).decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError("知识文档标识无效") from exc
        candidate = (self.root / relative).resolve()
        root = self.root.resolve()
        if root not in candidate.parents or candidate.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("知识文档路径无效")
        return candidate

    def list_documents(self) -> list[dict]:
        documents = []
        if not self.root.exists():
            return documents
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"} or path.name.lower() == "readme.md":
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            metadata, body = self._metadata(raw, path)
            relative = path.resolve().relative_to(self.root.resolve())
            documents.append({
                "id": self._document_id(path), **metadata, "filename": path.name,
                "path": relative.as_posix(), "size": path.stat().st_size,
                "characters": len(body), "chunks": len(self._chunks(body)),
                "editable": "uploads" in relative.parts,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            })
        return documents

    def read_document(self, document_id: str) -> dict:
        path = self._path_from_id(document_id)
        if not path.exists():
            raise FileNotFoundError("知识文档不存在")
        raw = path.read_text(encoding="utf-8", errors="ignore")
        metadata, body = self._metadata(raw, path)
        relative = path.resolve().relative_to(self.root.resolve())
        return {"id": document_id, **metadata, "filename": path.name, "content": body, "editable": "uploads" in relative.parts}

    def add_document(self, filename: str, content: str, metadata: dict[str, str]) -> dict:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".md", ".txt"}:
            raise ValueError("首版仅支持 Markdown 与 TXT 文件")
        if not content.strip():
            raise ValueError("知识文档内容不能为空")
        if len(content) > 500_000:
            raise ValueError("单个知识文档不能超过50万字符")
        safe_stem = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "-", Path(filename).stem).strip("-")[:60] or "document"
        folder = self.root / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{safe_stem}-{uuid4().hex[:8]}{suffix}"
        title = metadata.get("title", "").strip() or Path(filename).stem
        header = (
            "---\n" f"title: {title}\n"
            f"organization: {metadata.get('organization', '').strip()}\n"
            f"published_at: {metadata.get('published_at', '').strip()}\n"
            f"url: {metadata.get('url', '').strip()}\n" "---\n\n"
        )
        path.write_text(header + content.strip() + "\n", encoding="utf-8")
        return self.read_document(self._document_id(path))

    def delete_document(self, document_id: str) -> bool:
        path = self._path_from_id(document_id)
        relative = path.resolve().relative_to(self.root.resolve())
        if "uploads" not in relative.parts:
            raise PermissionError("内置知识文档受保护，不能在页面中删除")
        if not path.exists():
            return False
        path.unlink()
        return True


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

