from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SiroConfig:
    ollama_base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"
    memory_path: str = "data/memory.json"
    max_history: int = 20
    tts_rate: int = 180
    tts_voice_id: str = ""
    tts_output_device: str = ""
    tts_enabled: bool = True
    stt_device_index: int = -1
    persona_style: str = "기본"
    persona_intensity: str = "중간"
    response_length: str = "보통"
    game_difficulty: str = "보통"
    hotword_enabled: bool = False
    action_confirm_required: bool = True
    settings_path: str = "data/settings.json"

    @classmethod
    def load(cls, path: str = "data/settings.json") -> SiroConfig:
        p = Path(path)
        if not p.exists():
            cfg = cls(settings_path=path)
            cfg.save(path)
            return cfg

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("settings json must be object")
        except Exception:
            return cls(settings_path=path)

        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        cfg.settings_path = path
        return cfg

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | None = None) -> None:
        out = Path(path or self.settings_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
