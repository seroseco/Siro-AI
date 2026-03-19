from __future__ import annotations

import json
from typing import Any

import requests
from requests import RequestException


class OllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.7},
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=90)
            resp.raise_for_status()
            return resp.json()
        except RequestException as e:
            raise RuntimeError(
                "Ollama 서버에 연결하지 못했습니다. "
                "1) `ollama serve` 실행 "
                "2) `ollama pull qwen2.5:3b` 확인 "
                "3) 설정 URL(`http://localhost:11434`) 점검 후 다시 시도해 주세요."
            ) from e


def parse_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    # Ollama format: message.tool_calls[]
    calls = message.get("tool_calls") or []
    parsed: list[dict[str, Any]] = []

    for call in calls:
        fn = call.get("function", {})
        name = fn.get("name")
        args = fn.get("arguments", {})

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        if name:
            parsed.append({"name": name, "arguments": args})

    return parsed
