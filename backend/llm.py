from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from backend.config import settings


class LLMService:
    def __init__(self) -> None:
        self.mock = settings.llm_mock or not settings.llm_api_key
        self.client = None if self.mock else AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=60,
            max_retries=1,
        )
        vision_key = settings.vision_api_key or settings.llm_api_key
        self.vision_client = None if self.mock or not settings.vision_model or not vision_key else AsyncOpenAI(
            api_key=vision_key,
            base_url=settings.vision_base_url or settings.llm_base_url,
            timeout=90,
            max_retries=1,
        )

    async def complete(self, system: str, prompt: str, *, json_mode: bool = False) -> tuple[str, int]:
        if self.mock:
            await asyncio.sleep(0.12)
            return self._mock_response(system, prompt, json_mode), max(80, len(prompt) // 2)
        try:
            kwargs: dict[str, Any] = {
                "model": settings.llm_model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            usage = response.usage.total_tokens if response.usage else 0
            return content, usage
        except Exception as exc:
            message = str(exc).replace(settings.llm_api_key, "***") if settings.llm_api_key else str(exc)
            raise RuntimeError(f"模型服务暂时不可用：{message[:240]}") from exc

    async def complete_with_images(self, system: str, prompt: str, images: list[str]) -> tuple[str, int]:
        if self.mock:
            await asyncio.sleep(0.12)
            return f"已收到{len(images)}张图片。当前为模拟模式，无法进行真实图像识别。", max(100, len(prompt) // 2)
        if not settings.vision_model or self.vision_client is None:
            raise RuntimeError("智能伙伴尚未配置视觉模型。请设置 VISION_MODEL，并按需配置 VISION_BASE_URL 与 VISION_API_KEY。")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": image}} for image in images)
        try:
            response = await self.vision_client.chat.completions.create(
                model=settings.vision_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                temperature=0.2,
            )
            answer = response.choices[0].message.content or ""
            usage = response.usage.total_tokens if response.usage else 0
            return answer, usage
        except Exception as exc:
            secret = settings.vision_api_key or settings.llm_api_key
            message = str(exc).replace(secret, "***") if secret else str(exc)
            raise RuntimeError(f"视觉模型暂时不可用：{message[:240]}") from exc

    def _mock_response(self, system: str, prompt: str, json_mode: bool) -> str:
        if json_mode or "评分" in system or "评审" in system:
            loop = 1 if "返工轮次: 0" in prompt else 2
            score = 72 if loop == 1 else 88
            return json.dumps({
                "score": score,
                "dimensions": {"完整性": score, "逻辑性": score + 2, "可验证性": score - 3},
                "issues": ["需要补充关键指标的来源说明"] if score < 80 else [],
                "suggestions": ["增加数据来源与局限性章节"] if score < 80 else ["质量达标，可形成最终报告"],
            }, ensure_ascii=False)
        if "需求分析" in system or "需求分析师" in system:
            choices = [
                {"id": "scope", "question": "研究对象与覆盖范围？", "type": "single", "options": ["聚焦一个典型群体", "覆盖多个群体并对比", "使用公开资料做宏观研究"]},
                {"id": "indicators", "question": "优先分析哪些维度？", "type": "multiple", "options": ["现状与频率", "效率与质量", "风险与局限", "改进路径"]},
                {"id": "evidence", "question": "数据和证据边界？", "type": "single", "options": ["仅使用已提供资料", "设计调研方案但不虚构结果", "结合公开资料并标注待核验来源"]},
            ]
            return (
                "## 研究需求澄清\n\n已识别研究对象、交付目标与关键约束。以下选项需要人工确认，确认后才进入规划阶段。\n\n"
                "```approval_options\n" + json.dumps(choices, ensure_ascii=False) + "\n```"
            )
        role = system.split("。", 1)[0].replace("你是", "")
        return (
            f"## {role}阶段成果\n\n"
            f"围绕任务“{prompt[:90]}”，已完成结构化分析。\n\n"
            "### 核心发现\n- 明确研究目标、对象与评价指标。\n- 给出可执行步骤与风险控制。\n"
            "- 标注需要进一步核验的数据与假设。\n\n"
            "### 阶段结论\n建议在后续节点中交叉核验事实来源，并以量化指标评估最终成果。"
        )


llm = LLMService()

