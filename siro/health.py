from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import requests

from .speech import Speaker, SpeechToText


@dataclass(slots=True)
class CheckItem:
    name: str
    status: str  # ok | warn | error
    message: str


class HealthChecker:
    def __init__(self, base_url: str, model: str, stt: SpeechToText, speaker: Speaker) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.stt = stt
        self.speaker = speaker

    def run(self) -> dict[str, Any]:
        items = [
            self._check_ollama_server(),
            self._check_ollama_model(),
            self._check_stt(),
            self._check_tts(),
        ]
        has_error = any(x.status == "error" for x in items)
        has_warn = any(x.status == "warn" for x in items)
        if has_error:
            overall = "error"
        elif has_warn:
            overall = "warn"
        else:
            overall = "ok"

        return {
            "overall": overall,
            "items": [asdict(x) for x in items],
            "summary": self._summary(items),
        }

    def _summary(self, items: list[CheckItem]) -> str:
        icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}
        return " | ".join(f"{icon.get(i.status, '•')} {i.name}: {i.message}" for i in items)

    def _check_ollama_server(self) -> CheckItem:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            resp.raise_for_status()
            return CheckItem("Ollama 서버", "ok", "연결됨")
        except Exception:
            return CheckItem("Ollama 서버", "error", "연결 실패 (ollama serve 필요)")

    def _check_ollama_model(self) -> CheckItem:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", []) if isinstance(data, dict) else []
            names = [str(m.get("name", "")) for m in models if isinstance(m, dict)]
            if any(n == self.model or n.startswith(f"{self.model}:") for n in names):
                return CheckItem("모델", "ok", f"{self.model} 준비됨")
            return CheckItem("모델", "warn", f"{self.model} 없음 (ollama pull 필요)")
        except Exception:
            return CheckItem("모델", "warn", "서버 연결 후 확인 가능")

    def _check_stt(self) -> CheckItem:
        if not self.stt.enabled:
            return CheckItem("마이크(STT)", "warn", "SpeechRecognition 또는 마이크 설정 확인 필요")
        return CheckItem("마이크(STT)", "ok", "사용 가능")

    def _check_tts(self) -> CheckItem:
        try:
            if getattr(self.speaker, "engine", None) is None:
                return CheckItem("음성출력(TTS)", "warn", "엔진 초기화 확인 필요")
            return CheckItem("음성출력(TTS)", "ok", "사용 가능")
        except Exception:
            return CheckItem("음성출력(TTS)", "warn", "초기화 점검 필요")
