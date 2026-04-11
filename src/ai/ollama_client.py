"""
Ollama local AI client.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaClient:
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=self.settings.ollama.timeout)

    @property
    def base_url(self) -> str:
        return self.settings.ollama.base_url.rstrip("/")

    async def list_models(self) -> List[Dict[str, Any]]:
        response = await self.client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])

    async def chat(self, messages: List[Dict[str, str]], use_json_format: bool = True) -> Optional[Dict[str, Any]]:
        payload = {
            "model": self.settings.ollama.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.settings.ollama.temperature,
                "num_predict": self.settings.ollama.max_tokens,
            },
        }
        if use_json_format:
            payload["format"] = "json"
        response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "").strip()
        if not content:
            return None
        if not use_json_format:
            return {
                "response": content,
                "intent": "summary",
                "commands": [],
                "is_followup": False,
                "update_context": False,
            }
        parsed = self._parse_json_response(content)
        if parsed is None:
            logger.warning("Falling back to plain-text Ollama response because structured JSON parsing failed.")
            return self._fallback_response(content)
        return {
            "intent": parsed.get("intent", "command"),
            "commands": parsed.get("commands", []),
            "response": parsed.get("response", "Done"),
            "update_context": parsed.get("update_context", True),
            "expecting_followup": parsed.get("expecting_followup", False),
            "needs_context": parsed.get("needs_context", []),
        }

    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        candidates = [text]

        json_start = text.find("{")
        json_end = text.rfind("}")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            candidates.append(text[json_start : json_end + 1].strip())

        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        logger.error(f"Failed to parse JSON from Ollama response: {response_text[:500]}")
        return None

    def _fallback_response(self, content: str) -> Dict[str, Any]:
        cleaned = content.strip() or "I processed that, but the model did not return structured output."
        return {
            "intent": "question",
            "commands": [],
            "response": cleaned,
            "update_context": False,
            "expecting_followup": False,
            "needs_context": [],
        }

    async def close(self):
        await self.client.aclose()


_ollama_client: Optional[OllamaClient] = None


async def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


async def close_ollama_client():
    global _ollama_client
    if _ollama_client is not None:
        await _ollama_client.close()
        _ollama_client = None
