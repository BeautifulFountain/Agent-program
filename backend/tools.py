from __future__ import annotations

import ast
import base64
import binascii
import io
import math
import operator
import re
from hashlib import sha256
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
        metadata = {
            "title": path.stem, "organization": "", "published_at": "", "url": "",
            "authors": "", "doi": "", "cited_by_count": "", "original_file": "", "file_type": path.suffix.lower().lstrip("."),
        }
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
                matched = {term for term in terms if term in lowered or term in title}
                total_weight = sum(max(2, min(len(term), 6)) for term in terms) or 1
                matched_weight = sum(max(2, min(len(term), 6)) for term in matched)
                coverage = matched_weight / total_weight
                strong_matches = {term for term in matched if len(term) >= 3}
                # Refuse weak coincidental hits. A missing result is safer than unrelated evidence.
                if coverage < 0.08 or (not strong_matches and len(matched) < 2):
                    continue
                title_hits = sum(1 for term in matched if term in title)
                frequency_bonus = min(10, sum(min(lowered.count(term), 3) for term in matched))
                try:
                    citation_count = max(0, int(metadata.get("cited_by_count") or 0))
                except ValueError:
                    citation_count = 0
                # Citations are a secondary authority signal: semantic relevance stays dominant.
                citation_bonus = min(8, round(math.log10(citation_count + 1) * 2.4))
                score = min(100, round(coverage * 76 + min(12, title_hits * 3) + frequency_bonus + citation_bonus))
                matches.append({
                    "source": str(path), "title": metadata["title"], "organization": metadata["organization"],
                    "published_at": metadata["published_at"], "url": metadata["url"], "chunk": str(index + 1),
                    "cited_by_count": metadata.get("cited_by_count", ""),
                    "score": str(score), "coverage": f"{coverage:.2f}",
                    "match_terms": sorted(strong_matches, key=lambda term: (-len(term), term))[:8],
                    "snippet": chunk[:700],
                })
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
        paths = [
            path for path in self.root.rglob("*")
            if path.suffix.lower() in {".md", ".txt"} and path.name.lower() != "readme.md"
        ]
        # Knowledge management is an ingestion timeline: foundational files
        # remain at the top and newly imported evidence is appended below.
        for path in sorted(paths, key=lambda item: (item.stat().st_mtime_ns, item.as_posix().lower())):
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

    @staticmethod
    def _decode_text(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("文本文件编码无法识别，请转换为 UTF-8 后重试")

    @staticmethod
    def _extract_pdf(data: bytes) -> tuple[str, dict[str, str]]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("服务器尚未安装 PDF 解析组件 pypdf，请先安装 requirements.txt 依赖") from exc
        try:
            reader = PdfReader(io.BytesIO(data))
            info = reader.metadata or {}
            sections = []
            for index, page in enumerate(reader.pages, 1):
                text = (page.extract_text() or "").strip()
                if text:
                    sections.append(f"## 第 {index} 页\n\n{text}")
            if not sections:
                raise ValueError("PDF 未提取到文本；扫描版 PDF 暂需 OCR 后再导入")
            return "\n\n".join(sections), {
                "title": str(info.get("/Title") or "").strip(),
                "authors": str(info.get("/Author") or "").strip(),
            }
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PDF 解析失败：{str(exc)[:160]}") from exc

    @staticmethod
    def _extract_docx(data: bytes) -> tuple[str, dict[str, str]]:
        try:
            from docx import Document
            document = Document(io.BytesIO(data))
            blocks: list[str] = []
            for paragraph in document.paragraphs:
                text = paragraph.text.strip()
                if not text:
                    continue
                style = (paragraph.style.name or "").lower() if paragraph.style else ""
                if "heading" in style or "标题" in style:
                    level_match = re.search(r"(\d+)", style)
                    level = min(3, max(1, int(level_match.group(1)))) if level_match else 2
                    blocks.append(f"{'#' * level} {text}")
                else:
                    blocks.append(text)
            for table_index, table in enumerate(document.tables, 1):
                rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
                if rows:
                    blocks.extend([f"## 表格 {table_index}", *rows])
            content = "\n\n".join(blocks).strip()
            if not content:
                raise ValueError("Word 文档未提取到可检索文字")
            props = document.core_properties
            return content, {
                "title": (props.title or "").strip(),
                "authors": (props.author or "").strip(),
                "published_at": props.created.date().isoformat() if props.created else "",
            }
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Word 文档解析失败：{str(exc)[:160]}") from exc

    @staticmethod
    def _infer_scholarly_metadata(content: str, extracted: dict[str, str]) -> dict[str, str]:
        """Recover stable identifiers and a usable title from extracted document text."""
        inferred = dict(extracted)
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", content, flags=re.IGNORECASE)
        if doi_match:
            inferred["doi"] = doi_match.group(0).rstrip(".,;)]}")
            inferred.setdefault("url", f"https://doi.org/{inferred['doi']}")
        if not inferred.get("doi"):
            arxiv_match = re.search(r"(?:arXiv\s*:\s*)?(\d{4}\.\d{4,5})(?:v\d+)?", content, flags=re.IGNORECASE)
            if arxiv_match:
                inferred["doi"] = f"10.48550/arXiv.{arxiv_match.group(1)}"
                inferred.setdefault("url", f"https://arxiv.org/abs/{arxiv_match.group(1)}")
        if not inferred.get("title"):
            for line in content.splitlines()[:40]:
                candidate = re.sub(r"^#+\s*", "", line).strip()
                if not candidate or re.fullmatch(r"第\s*\d+\s*页", candidate) or candidate.lower() in {"abstract", "摘要"}:
                    continue
                if 8 <= len(candidate) <= 240:
                    inferred["title"] = candidate
                    break
        return inferred

    def add_file_document(self, filename: str, data_base64: str, metadata: dict[str, str]) -> dict:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".md", ".txt"}:
            raise ValueError("支持 PDF、DOCX、Markdown 与 TXT 文件；旧版 DOC 请先另存为 DOCX")
        try:
            data = base64.b64decode(data_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("上传文件内容无效") from exc
        if not data:
            raise ValueError("上传文件不能为空")
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("单个文件不能超过 20 MB")

        extracted: dict[str, str] = {}
        if suffix == ".pdf":
            content, extracted = self._extract_pdf(data)
        elif suffix == ".docx":
            content, extracted = self._extract_docx(data)
        else:
            content = self._decode_text(data)
        extracted = self._infer_scholarly_metadata(content, extracted)
        if len(content) > 2_000_000:
            raise ValueError("提取后的文本超过 200 万字符，请拆分后导入")

        digest = sha256(data).hexdigest()[:18]
        safe_stem = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff_-]+", "-", Path(filename).stem).strip("-")[:60] or "document"
        original_folder = self.root / "uploads" / "originals"
        index_folder = self.root / "uploads" / "index"
        original_folder.mkdir(parents=True, exist_ok=True)
        index_folder.mkdir(parents=True, exist_ok=True)
        original_path = original_folder / f"{safe_stem}-{digest}{suffix}"
        index_path = index_folder / f"{safe_stem}-{digest}.md"
        if index_path.exists():
            return self.read_document(self._document_id(index_path))
        original_path.write_bytes(data)

        values = {
            "title": extracted.get("title", "").strip() or Path(filename).stem,
            "organization": metadata.get("organization", "").strip(),
            "published_at": extracted.get("published_at", "").strip() or metadata.get("published_at", "").strip(),
            "url": metadata.get("url", "").strip() or extracted.get("url", "").strip(),
            "authors": extracted.get("authors", "").strip(),
            "doi": extracted.get("doi", "").strip(),
            "original_file": original_path.resolve().relative_to(self.root.resolve()).as_posix(),
            "file_type": suffix.lstrip("."),
        }
        header = "---\n" + "\n".join(f"{key}: {value}" for key, value in values.items()) + "\n---\n\n"
        index_path.write_text(header + content.strip() + "\n", encoding="utf-8")
        return self.read_document(self._document_id(index_path))

    def update_document_metadata(self, document_id: str, updates: dict[str, str]) -> dict:
        path = self._path_from_id(document_id)
        raw = path.read_text(encoding="utf-8", errors="ignore")
        metadata, body = self._metadata(raw, path)
        for key in ("title", "organization", "published_at", "url", "authors", "doi", "cited_by_count"):
            value = str(updates.get(key, "")).strip()
            if value and not metadata.get(key):
                metadata[key] = value
        header = "---\n" + "\n".join(f"{key}: {value}" for key, value in metadata.items()) + "\n---\n\n"
        path.write_text(header + body.strip() + "\n", encoding="utf-8")
        return self.read_document(document_id)

    def add_external_document(self, provider: str, identity: str, title: str, content: str, metadata: dict[str, str]) -> tuple[dict, bool]:
        """Persist normalized external evidence once, using DOI/URL as a stable identity."""
        digest = sha256(identity.strip().lower().encode("utf-8")).hexdigest()[:18]
        safe_provider = re.sub(r"[^a-z0-9_-]+", "-", provider.lower()).strip("-") or "external"
        folder = self.root / "external"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{safe_provider}-{digest}.md"
        if path.exists():
            return self.read_document(self._document_id(path)), False
        header = (
            "---\n" f"title: {title.strip() or '外部检索资料'}\n"
            f"organization: {metadata.get('organization', provider).strip()}\n"
            f"published_at: {metadata.get('published_at', '').strip()}\n"
            f"url: {metadata.get('url', '').strip()}\n"
            f"authors: {metadata.get('authors', '').strip()}\n"
            f"doi: {metadata.get('doi', '').strip()}\n"
            f"cited_by_count: {str(metadata.get('cited_by_count', '')).strip()}\n" "---\n\n"
        )
        path.write_text(header + content.strip() + "\n", encoding="utf-8")
        return self.read_document(self._document_id(path)), True

    def delete_document(self, document_id: str) -> bool:
        path = self._path_from_id(document_id)
        if not path.exists():
            return False
        raw = path.read_text(encoding="utf-8", errors="ignore")
        metadata, _ = self._metadata(raw, path)
        original = metadata.get("original_file", "")
        path.unlink()
        if original:
            original_path = (self.root / original).resolve()
            if self.root.resolve() in original_path.parents and original_path.exists():
                original_path.unlink()
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

