from __future__ import annotations

import json
import subprocess
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .game_engine import GameEngine
from .memory import PersonalMemory


ToolFn = Callable[[dict[str, Any]], str]


@dataclass
class SessionState:
    mood: str = "보통"
    memory_enabled: bool = True
    action_confirm_required: bool = True
    pending_action: dict[str, str] | None = None
    history_notes: list[str] = field(default_factory=list)


class ToolRegistry:
    def __init__(
        self,
        memory: PersonalMemory,
        state: SessionState,
        game_difficulty: str = "보통",
        action_confirm_required: bool = True,
        event_logger: Callable[[str], None] | None = None,
    ) -> None:
        self.memory = memory
        self.state = state
        self.games = GameEngine()
        self.games.set_difficulty(game_difficulty)
        self.state.action_confirm_required = action_confirm_required
        self.event_logger = event_logger

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "save_memory",
                    "description": "사용자 개인 정보를 짧게 메모로 저장",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "저장할 메모 텍스트"}
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "사용자 메모에서 관련 내용을 검색",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "검색어"},
                            "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_memory",
                    "description": "메모에서 특정 주제/문장을 삭제",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "삭제할 메모 검색어"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_memory_mode",
                    "description": "메모 저장 모드 on/off",
                    "parameters": {
                        "type": "object",
                        "properties": {"enabled": {"type": "boolean", "description": "true면 저장 허용"}},
                        "required": ["enabled"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "request_action",
                    "description": (
                        "안전한 실행 요청. operation은 open_url/open_app/open_path 중 선택. "
                        "확인 정책이 켜져 있으면 승인 대기 상태로 저장됨."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string", "description": "open_url | open_app | open_path"},
                            "target": {"type": "string", "description": "실행 대상"},
                        },
                        "required": ["operation", "target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "confirm_action",
                    "description": "대기 중인 실행 요청을 승인/취소",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "approve": {"type": "boolean", "description": "true면 실행, false면 취소"},
                        },
                        "required": ["approve"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "action_status",
                    "description": "대기 중인 실행 요청 및 최근 실행 상태 확인",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_action_policy",
                    "description": "실행 전 승인 필요 여부 설정",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "require_confirmation": {"type": "boolean", "description": "true면 승인 필요"},
                        },
                        "required": ["require_confirmation"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_datetime",
                    "description": "현재 날짜와 시간 확인",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "start_game",
                    "description": (
                        "게임 시작. 지원: word_chain(끝말잇기), association(연상), "
                        "quiz(퀴즈), twenty(스무고개), story(이야기), number_guess(숫자맞추기). "
                        "퀴즈는 category(일반/과학/코딩/상식) 지정 가능"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "game": {"type": "string", "description": "게임 이름"},
                            "category": {"type": "string", "description": "퀴즈 카테고리 (선택)"},
                        },
                        "required": ["game"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "play_game_turn",
                    "description": "진행 중인 게임 한 턴 진행",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "사용자 입력"}
                        },
                        "required": ["text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "end_game",
                    "description": "현재 게임 종료",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "game_status",
                    "description": "현재 게임 상태 확인",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "random_question",
                    "description": "대화를 이어갈 랜덤 질문 제공",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "tell_joke",
                    "description": "짧은 농담/드립 제공",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_mood",
                    "description": "기분 체크 및 응원 문구",
                    "parameters": {
                        "type": "object",
                        "properties": {"mood": {"type": "string", "description": "예: 좋음/보통/지침/우울"}},
                        "required": ["mood"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recommend_music",
                    "description": "현재 기분에 맞는 음악 추천",
                    "parameters": {
                        "type": "object",
                        "properties": {"mood": {"type": "string", "description": "기분 키워드"}},
                        "required": ["mood"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "start_number_guess",
                    "description": "숫자 맞추기 게임 시작(호환용)",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "guess_number",
                    "description": "숫자 맞추기 입력(호환용)",
                    "parameters": {
                        "type": "object",
                        "properties": {"guess": {"type": "integer", "minimum": 1, "maximum": 50}},
                        "required": ["guess"],
                    },
                },
            },
        ]

    def handlers(self) -> dict[str, ToolFn]:
        return {
            "save_memory": self._save_memory,
            "search_memory": self._search_memory,
            "delete_memory": self._delete_memory,
            "set_memory_mode": self._set_memory_mode,
            "request_action": self._request_action,
            "confirm_action": self._confirm_action,
            "action_status": self._action_status,
            "set_action_policy": self._set_action_policy,
            "get_datetime": self._get_datetime,
            "start_game": self._start_game,
            "play_game_turn": self._play_game_turn,
            "end_game": self._end_game,
            "game_status": self._game_status,
            "random_question": self._random_question,
            "tell_joke": self._tell_joke,
            "check_mood": self._check_mood,
            "recommend_music": self._recommend_music,
            "start_number_guess": self._start_number_guess,
            "guess_number": self._guess_number,
        }

    def call(self, name: str, args: dict[str, Any]) -> str:
        fn = self.handlers().get(name)
        if not fn:
            return json.dumps({"error": f"unknown function: {name}"}, ensure_ascii=False)
        try:
            out = fn(args)
            if self.event_logger:
                self.event_logger(f"tool={name} args={args} result={out}")
            return out
        except Exception as e:  # pragma: no cover
            if self.event_logger:
                self.event_logger(f"tool={name} args={args} error={e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _save_memory(self, args: dict[str, Any]) -> str:
        if not self.state.memory_enabled:
            return json.dumps({"ok": False, "message": "현재 메모 저장이 꺼져 있어요."}, ensure_ascii=False)
        text = str(args.get("text", "")).strip()
        if not text:
            return json.dumps({"ok": False, "message": "빈 메모는 저장할 수 없습니다."}, ensure_ascii=False)
        item = self.memory.add(text)
        return json.dumps({"ok": True, "message": "메모 저장 완료", "item": asdict(item)}, ensure_ascii=False)

    def _search_memory(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        top_k = int(args.get("top_k", 3))
        rows = self.memory.search(query, top_k=top_k)
        return json.dumps(
            {
                "ok": True,
                "count": len(rows),
                "items": [asdict(r) for r in rows],
            },
            ensure_ascii=False,
        )

    def _delete_memory(self, args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 3))
        removed = self.memory.delete_by_query(query, limit=limit)
        if removed <= 0:
            return json.dumps({"ok": False, "message": "조건에 맞는 메모를 찾지 못했어요."}, ensure_ascii=False)
        return json.dumps({"ok": True, "message": f"메모 {removed}개를 삭제했어요."}, ensure_ascii=False)

    def _set_memory_mode(self, args: dict[str, Any]) -> str:
        enabled = bool(args.get("enabled", True))
        self.state.memory_enabled = enabled
        msg = "메모 저장을 켰어요." if enabled else "메모 저장을 껐어요. 원하시면 다시 켤 수 있어요."
        return json.dumps({"ok": True, "enabled": enabled, "message": msg}, ensure_ascii=False)

    def _request_action(self, args: dict[str, Any]) -> str:
        operation = str(args.get("operation", "")).strip()
        target = str(args.get("target", "")).strip()
        ok, reason = self._validate_action(operation, target)
        if not ok:
            return json.dumps({"ok": False, "message": reason}, ensure_ascii=False)

        if self.state.action_confirm_required:
            self.state.pending_action = {"operation": operation, "target": target}
            msg = (
                f"실행 요청을 준비했어요: {operation} -> {target}. "
                "승인하려면 '승인' 또는 '실행 승인', 취소하려면 '취소'라고 말씀해 주세요."
            )
            return json.dumps({"ok": True, "pending": True, "message": msg}, ensure_ascii=False)

        result = self._execute_action(operation, target)
        return json.dumps({"ok": True, "pending": False, "message": result}, ensure_ascii=False)

    def _confirm_action(self, args: dict[str, Any]) -> str:
        approve = bool(args.get("approve", False))
        pending = self.state.pending_action
        if not pending:
            return json.dumps({"ok": False, "message": "대기 중인 실행 요청이 없어요."}, ensure_ascii=False)

        if not approve:
            self.state.pending_action = None
            return json.dumps({"ok": True, "message": "실행 요청을 취소했어요."}, ensure_ascii=False)

        op = pending.get("operation", "")
        tg = pending.get("target", "")
        self.state.pending_action = None
        result = self._execute_action(op, tg)
        return json.dumps({"ok": True, "message": result}, ensure_ascii=False)

    def _action_status(self, _: dict[str, Any]) -> str:
        pending = self.state.pending_action
        return json.dumps(
            {
                "ok": True,
                "require_confirmation": self.state.action_confirm_required,
                "pending": pending,
                "recent": self.state.history_notes[-5:],
            },
            ensure_ascii=False,
        )

    def _set_action_policy(self, args: dict[str, Any]) -> str:
        require_confirmation = bool(args.get("require_confirmation", True))
        self.state.action_confirm_required = require_confirmation
        msg = "실행 전 승인 모드를 켰어요." if require_confirmation else "실행 전 승인 모드를 껐어요."
        return json.dumps({"ok": True, "require_confirmation": require_confirmation, "message": msg}, ensure_ascii=False)

    def _validate_action(self, operation: str, target: str) -> tuple[bool, str]:
        operation = operation.lower()
        if operation not in {"open_url", "open_app", "open_path"}:
            return False, "지원하지 않는 작업입니다. open_url/open_app/open_path만 허용돼요."
        if not target:
            return False, "실행 대상을 입력해 주세요."

        if operation == "open_url":
            if not (target.startswith("http://") or target.startswith("https://")):
                return False, "URL은 http:// 또는 https:// 로 시작해야 해요."
            return True, "ok"

        if operation == "open_app":
            whitelist = {"Safari", "Google Chrome", "Terminal", "Finder", "Notes"}
            if target not in whitelist:
                return False, f"허용되지 않은 앱입니다. 허용 목록: {', '.join(sorted(whitelist))}"
            return True, "ok"

        # open_path
        p = Path(target).expanduser().resolve()
        home = Path.home().resolve()
        try:
            p.relative_to(home)
        except ValueError:
            return False, "보안을 위해 홈 디렉터리 내부 경로만 열 수 있어요."
        if not p.exists():
            return False, "해당 경로가 존재하지 않아요."
        return True, "ok"

    def _execute_action(self, operation: str, target: str) -> str:
        operation = operation.lower()
        if operation == "open_url":
            subprocess.run(["open", target], check=False)
        elif operation == "open_app":
            subprocess.run(["open", "-a", target], check=False)
        elif operation == "open_path":
            p = str(Path(target).expanduser().resolve())
            subprocess.run(["open", p], check=False)
        else:
            return "알 수 없는 실행 요청입니다."

        note = f"{datetime.now().strftime('%H:%M:%S')} {operation} {target}"
        self.state.history_notes.append(note)
        return f"실행했습니다: {operation} -> {target}"

    def _get_datetime(self, _: dict[str, Any]) -> str:
        now = datetime.now()
        return json.dumps(
            {
                "ok": True,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
            },
            ensure_ascii=False,
        )

    def _start_game(self, args: dict[str, Any]) -> str:
        game = str(args.get("game", "")).strip()
        category = str(args.get("category", "")).strip() or None
        if not game:
            return json.dumps({"ok": False, "message": "게임 이름을 전달해 주세요."}, ensure_ascii=False)
        msg = self.games.start(game, category=category)
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)

    def _play_game_turn(self, args: dict[str, Any]) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            return json.dumps({"ok": False, "message": "게임 입력 텍스트가 비어 있습니다."}, ensure_ascii=False)
        msg = self.games.turn(text)
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)

    def _end_game(self, _: dict[str, Any]) -> str:
        msg = self.games.stop()
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)

    def _game_status(self, _: dict[str, Any]) -> str:
        msg = self.games.status()
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)

    def _start_number_guess(self, _: dict[str, Any]) -> str:
        msg = self.games.start("number_guess")
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)

    def _guess_number(self, args: dict[str, Any]) -> str:
        guess = args.get("guess")
        msg = self.games.turn(str(guess))
        return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)

    def _random_question(self, _: dict[str, Any]) -> str:
        questions = [
            "요즘 가장 기대되는 일이 무엇인가요?",
            "최근에 웃겼던 순간 하나 공유해주실래요?",
            "주말에 딱 하루 쉬면 무엇을 하고 싶으세요?",
            "오늘 자신에게 칭찬 한마디 해본다면 뭐라고 하시겠어요?",
        ]
        return json.dumps({"ok": True, "question": random.choice(questions)}, ensure_ascii=False)

    def _tell_joke(self, _: dict[str, Any]) -> str:
        jokes = [
            "제가 다이어트 시작했는데요, 냉장고가 저를 먼저 찾더라고요.",
            "버그를 잡았더니요, 알고 보니 기능이었대요.",
            "커피를 세 잔 마셨더니, 할 일은 그대로인데 심장은 스프린트 중이에요.",
        ]
        return json.dumps({"ok": True, "joke": random.choice(jokes)}, ensure_ascii=False)

    def _check_mood(self, args: dict[str, Any]) -> str:
        mood = str(args.get("mood", "보통")).strip() or "보통"
        self.state.mood = mood
        support = {
            "좋음": "좋은 기운이 느껴져요. 그 에너지로 하고 싶은 걸 하나 밀어볼까요?",
            "보통": "안정적인 하루도 충분히 소중해요. 작은 성취 하나 같이 만들어요.",
            "지침": "오늘 많이 달리셨네요. 5분만 눈/어깨 쉬는 타임 가져보셔도 좋아요.",
            "우울": "그럴 때 있으시죠. 무리하지 말고 지금 할 수 있는 가장 작은 것부터 같이 해봐요.",
        }
        msg = support.get(mood, f"{mood} 상태군요. 지금 필요한 리듬으로 천천히 가요.")
        return json.dumps({"ok": True, "mood": mood, "message": msg}, ensure_ascii=False)

    def _recommend_music(self, args: dict[str, Any]) -> str:
        mood = str(args.get("mood", "보통")).strip().lower()
        mapping = {
            "좋": ["DAY6 - 한 페이지가 될 수 있게", "NELL - 기억을 걷는 시간", "백예린 - Square"],
            "우울": ["아이유 - 밤편지", "검정치마 - Everything", "AKMU - 어떻게 이별까지 사랑하겠어"],
            "집중": ["Lofi Girl 스타일 플레이리스트", "Brian Eno - Ambient 1", "Nujabes - Luv(sic)"],
            "운동": ["Imagine Dragons - Believer", "NewJeans - Super Shy", "Dua Lipa - Physical"],
        }

        picks = ["잔잔한 재즈 플레이리스트", "K-indie 감성 플레이리스트", "집중용 Lo-fi 플레이리스트"]
        for key, songs in mapping.items():
            if key in mood:
                picks = songs
                break

        return json.dumps(
            {
                "ok": True,
                "mood": mood,
                "recommendations": picks,
                "note": "실시간 스트리밍 검색은 아니고, 분위기 기반 추천이에요.",
            },
            ensure_ascii=False,
        )
