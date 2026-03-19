from __future__ import annotations

import json
import random
import re
from typing import Any

from .config import SiroConfig
from .llm_client import OllamaClient, parse_tool_calls
from .memory import PersonalMemory
from .tools import SessionState, ToolRegistry


BASE_SYSTEM_PROMPT = """
당신의 이름은 Siro입니다.
역할: 사용자와 대화하는 친구 같은 AI 비서.
원칙:
- 항상 한국어 존댓말을 사용합니다.
- 따뜻하고 가벼운 친구 톤을 유지하되, 과하게 장황하지 않게 말합니다.
- Siro라는 정체성을 분명히 드러냅니다.
- 필요 시 함수 호출을 적극 사용합니다. 메모 관련 질문은 search_memory/save_memory를 우선 고려합니다.
- 게임 요청이 오면 start_game/play_game_turn/end_game/game_status를 우선 사용합니다.
- 음악 추천은 실시간 검색이 아닌 분위기 기반 추천임을 짧게 알립니다.
- "감사합니다", "다른 도움이 필요하면 말씀해 주세요", "도움이 필요하시면 언제든지" 같은
  상담원형 마무리 문구를 습관적으로 반복하지 않습니다.
- 대신 자연스러운 친구 대화처럼 짧고 편안하게 끝냅니다.
- "어떤 편의를 드릴까요?", "무엇을 도와드릴까요?" 같은 고객센터 문장을 쓰지 않습니다.
- 인사할 때는 "안녕하세요, 반가워요."처럼 부드럽고 친근하게 말합니다.
- 사용자가 먼저 요청하지 않으면 응답 끝에 추가 질문/권유 문장을 붙이지 않습니다.
- "더 도와드릴까요?", "다시 물어보세요", "오늘은 뭐 할까요?" 같은 후속 유도 문장은 금지합니다.
- 사용자가 물은 내용에만 정확히 답하고, 불필요한 마무리 멘트는 생략합니다.
- "~해줘/추천해줘/알려줘" 같은 요청에는 되묻지 말고 바로 결과를 제공합니다.
- 취향/주제 선택이 필요한 경우에도 먼저 랜덤 1개를 바로 제안한 뒤, 필요 시에만 선택지를 덧붙입니다.
- "한국어로 농담이 조금 어려울 것 같아요" 같은 회피/능력부족 문구는 절대 사용하지 않습니다.
""".strip()


def build_system_prompt(style: str, intensity: str, response_length: str) -> str:
    style_map = {
        "차분": "- 말투는 차분하고 안정감 있게 유지합니다.",
        "기본": "- 말투는 자연스럽고 편안한 친구 느낌을 기본으로 유지합니다.",
        "발랄": "- 말투는 에너지 있고 발랄하지만 과하지 않게 유지합니다.",
    }
    intensity_map = {
        "약하게": "- 표현 강도는 은은하게 유지합니다.",
        "중간": "- 표현 강도는 과하지 않게 중간으로 유지합니다.",
        "강하게": "- 표현 강도는 조금 더 생동감 있게 유지합니다.",
    }
    length_map = {
        "짧게": "- 답변은 핵심 1~2문장 위주로 짧게 말합니다.",
        "보통": "- 답변은 짧고 충분한 길이(2~4문장)로 말합니다.",
        "길게": "- 필요하면 자세히 말하되 중복 없이 정리해서 말합니다.",
    }
    return (
        f"{BASE_SYSTEM_PROMPT}\n"
        f"{style_map.get(style, style_map['기본'])}\n"
        f"{intensity_map.get(intensity, intensity_map['중간'])}\n"
        f"{length_map.get(response_length, length_map['보통'])}"
    )


class SiroAssistant:
    def __init__(self, config: SiroConfig) -> None:
        self.config = config
        self.client = OllamaClient(base_url=config.ollama_base_url, model=config.model)
        self.memory = PersonalMemory(config.memory_path)
        self.state = SessionState()
        self.debug_events: list[str] = []
        self.tools = ToolRegistry(
            self.memory,
            self.state,
            game_difficulty=config.game_difficulty,
            action_confirm_required=config.action_confirm_required,
            event_logger=self._debug_log,
        )
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": build_system_prompt(config.persona_style, config.persona_intensity, config.response_length),
            }
        ]
        self._last_reply = ""
        self._story_openers = [
            "퇴근길 지하철에서 누군가가 떨어뜨린 종이비행기를 주웠는데, 안에는 내일의 뉴스가 적혀 있었어요.",
            "비 오는 밤, 편의점 우산꽂이에서 마지막 우산을 잡는 순간 낯선 사람이 제 이름을 불렀어요.",
            "오래된 게임기를 켰더니 저장 파일 이름이 오늘 날짜와 제 이름으로 되어 있었어요.",
            "동네 고양이가 매일 같은 시간에 제 창문을 두드리더니, 어느 날 작은 열쇠를 물어다 줬어요.",
        ]

    def _debug_log(self, line: str) -> None:
        self.debug_events.append(line)
        if len(self.debug_events) > 400:
            self.debug_events = self.debug_events[-400:]

    def debug_dump(self, limit: int = 120) -> str:
        return "\n".join(self.debug_events[-limit:])

    def apply_settings(
        self,
        *,
        ollama_base_url: str,
        model: str,
        max_history: int,
        persona_style: str,
        persona_intensity: str,
        response_length: str,
        game_difficulty: str,
        action_confirm_required: bool,
    ) -> None:
        self.config.ollama_base_url = ollama_base_url
        self.config.model = model
        self.config.max_history = max_history
        self.config.persona_style = persona_style
        self.config.persona_intensity = persona_intensity
        self.config.response_length = response_length
        self.config.game_difficulty = game_difficulty
        self.config.action_confirm_required = action_confirm_required

        self.client.base_url = ollama_base_url.rstrip("/")
        self.client.model = model
        self.tools.games.set_difficulty(game_difficulty)
        self.state.action_confirm_required = action_confirm_required
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = build_system_prompt(persona_style, persona_intensity, response_length)

    def _fast_path(self, user_text: str) -> str | None:
        text = user_text.strip()
        low = text.lower()

        if text.startswith("기억해:") or text.startswith("기억해줘:"):
            content = text.split(":", 1)[1].strip()
            data = json.loads(self.tools.call("save_memory", {"text": content}))
            return data.get("message")

        if text.startswith("잊어줘:") or text.startswith("삭제해:"):
            query = text.split(":", 1)[1].strip()
            data = json.loads(self.tools.call("delete_memory", {"query": query}))
            return data.get("message")

        if any(k in low for k in ["저장하지마", "저장하지 마", "기억하지마", "기억하지 마"]):
            data = json.loads(self.tools.call("set_memory_mode", {"enabled": False}))
            return data.get("message")
        if any(k in low for k in ["저장 다시", "메모 저장 켜", "기억해둬", "기억 다시"]):
            data = json.loads(self.tools.call("set_memory_mode", {"enabled": True}))
            return data.get("message")

        if low in {"승인", "실행 승인", "오케이 실행", "그래 실행"}:
            data = json.loads(self.tools.call("confirm_action", {"approve": True}))
            return data.get("message")
        if low in {"취소", "실행 취소", "그만", "취소해"}:
            data = json.loads(self.tools.call("confirm_action", {"approve": False}))
            return data.get("message")

        if "실행 상태" in text or "명령 상태" in text:
            data = json.loads(self.tools.call("action_status", {}))
            pending = data.get("pending")
            if pending:
                return f"대기 중 요청: {pending.get('operation')} -> {pending.get('target')}"
            return "대기 중인 실행 요청은 없어요."

        app_map = {"사파리": "Safari", "크롬": "Google Chrome", "터미널": "Terminal", "파인더": "Finder", "노트": "Notes"}
        for k, app in app_map.items():
            if k in text and ("열어" in text or "실행" in text):
                data = json.loads(self.tools.call("request_action", {"operation": "open_app", "target": app}))
                return data.get("message")

        if "http://" in text or "https://" in text:
            m = re.search(r"(https?://[^\s]+)", text)
            if m:
                data = json.loads(self.tools.call("request_action", {"operation": "open_url", "target": m.group(1)}))
                return data.get("message")

        if "게임 상태" in text:
            data = json.loads(self.tools.call("game_status", {}))
            return data.get("message")
        if "게임 종료" in text or "게임 그만" in text:
            data = json.loads(self.tools.call("end_game", {}))
            return data.get("message")

        if "게임 시작" in text:
            mapper = {
                "끝말잇기": "word_chain",
                "연상": "association",
                "퀴즈": "quiz",
                "스무고개": "twenty",
                "이야기": "story",
                "숫자": "number_guess",
            }
            for k, v in mapper.items():
                if k in text:
                    category = None
                    if v == "quiz":
                        if "과학" in text:
                            category = "과학"
                        elif "코딩" in text or "개발" in text:
                            category = "코딩"
                        elif "상식" in text:
                            category = "상식"
                    payload = {"game": v}
                    if category:
                        payload["category"] = category
                    data = json.loads(self.tools.call("start_game", payload))
                    return data.get("message")

        if self.tools.games.state.active and not re.search(r"(게임 시작|게임 종료|게임 상태)", text):
            data = json.loads(self.tools.call("play_game_turn", {"text": text}))
            return data.get("message")

        if text.startswith("메모 저장:"):
            content = text.split(":", 1)[1].strip()
            data = json.loads(self.tools.call("save_memory", {"text": content}))
            return data.get("message")

        return None

    def _trim_history(self) -> None:
        if len(self.messages) <= self.config.max_history + 1:
            return
        self.messages = [self.messages[0]] + self.messages[-self.config.max_history :]

    def _polish_reply(self, text: str) -> str:
        cleaned = text.strip()
        repetitive = [
            "감사합니다!",
            "감사합니다.",
            "감사합니다,",
            "어떤 다른 도움이 필요하시면 말씀해 주세요.",
            "다른 도움이 필요하시면 말씀해 주세요.",
            "도움이 필요하시면 언제든지 말씀해 주세요.",
            "필요하시면 언제든지 말씀해 주세요.",
            "언제든지 다시 물어보세요!",
            "언제든지 다시 물어보세요.",
        ]
        for phrase in repetitive:
            cleaned = cleaned.replace(phrase, "").strip()

        stiff_map = {
            "어떤 편의를 드릴까요?": "",
            "무엇을 도와드릴까요?": "",
            "안녕하세요! 반갑습니다,": "안녕하세요.",
            "안녕하세요. 무엇을 도와드릴까요?": "안녕하세요.",
        }
        for old, new in stiff_map.items():
            cleaned = cleaned.replace(old, new)

        followup_patterns = [
            r"(오늘은 뭐.*놀까요\??)$",
            r"(오늘은 어떤 걸.*해볼까요\??)$",
            r"(다른 .*필요하시면.*말씀해 주세요\.?)$",
            r"(필요하시면 .*말씀해 주세요\.?)$",
            r"(언제든지 .*물어보세요\.?)$",
            r"(궁금한 .*있으시면 .*말씀해 주세요\.?)$",
            r"(더 .*도와드릴까요\??)$",
            r"(계속 .*해볼까요\??)$",
            r"(이어가볼까요\??)$",
            r"(궁금하신 .*있으신가요\??)$",
            r"(원하시면 .*제안해 드릴게.*)$",
            r"(어떤 정보를 원하시나요\??)$",
            r"(어떤 정보를 원하세요\??)$",
            r"(원하시는 정보를 .*말씀해 주세요\.?)$",
            r"(자세한 정보를 원하시면 .*말씀해 주세요\.?)$",
            r"(어떤 정보가 필요하신지 알려주시면 .*도와드릴 수 있을 것 같습니다\.?)$",
            r"(어떤 .*필요하신지 알려주시면 .*도와드릴.*)$",
        ]
        for p in followup_patterns:
            cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE).strip()

        # 회피형/무능력형 문구 차단
        cleaned = re.sub(
            r"한국어로\s*농담[^\n.!?]*어려울\s*것\s*같아요\.?",
            "짧은 농담 하나 해드릴게요. 커피가 잠을 못 잔 이유는 밤새 원두했기 때문이래요.",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(저는\s*현재\s*[^.!?\n]*할\s*수\s*없습니다\.?|지원하지\s*않습니다\.?|불가능합니다\.?)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        cleaned = re.sub(r"^\s*감사합니다[,.\s]+", "", cleaned, flags=re.IGNORECASE).strip()

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if not cleaned:
            cleaned = "좋아요, 계속 같이 해봐요."

        self._last_reply = cleaned
        return cleaned

    def _enforce_direct_request_reply(self, user_text: str, reply: str) -> str:
        user = user_text.strip()
        out = reply.strip()

        user_is_greeting = bool(re.search(r"^(안녕|하이|hello|ㅎㅇ)", user, re.IGNORECASE))
        if not user_is_greeting:
            out = re.sub(
                r"^\s*(안녕하세요|안녕|반가워요|반갑습니다)[!,. ]*",
                "",
                out,
                flags=re.IGNORECASE,
            ).strip()

        direct_request = (
            "?" not in user
            and any(k in user for k in ["해줘", "해주세요", "추천해", "알려줘", "말해줘", "보여줘", "써줘", "해봐"])
        )
        if direct_request:
            sentences = re.split(r"(?<=[.!?])\s+", out)
            kept: list[str] = []
            for s in sentences:
                s_clean = s.strip()
                if not s_clean:
                    continue
                if s_clean.endswith("?"):
                    continue
                if re.search(r"(주제|장르|원하시|원하시면|골라|선택)", s_clean):
                    continue
                kept.append(s_clean)
            out = " ".join(kept).strip()

            if not out and re.search(r"(재밌는 이야기|재미있는 이야기|이야기)", user):
                out = random.choice(self._story_openers)

        return out or reply

    def _enforce_first_turn_direct(self, user_text: str, reply: str, is_first_turn: bool) -> str:
        if not is_first_turn:
            return reply

        q = user_text.strip()
        is_question = (
            "?" in q
            or any(k in q for k in ["뭐", "무엇", "어떻게", "왜", "언제", "어디", "알려", "추천", "가능", "할 수"])
        )
        if not is_question:
            return reply

        intro_patterns = [
            r"^\s*안녕하세요[,.!\s]*",
            r"^\s*반가워요[,.!\s]*",
            r"^\s*저는\s*siro",
            r"^\s*제 이름은\s*siro",
            r"^\s*siro입니다",
        ]
        if not any(re.search(p, reply, re.IGNORECASE) for p in intro_patterns):
            return reply

        # 첫 문장(인사/자기소개성) 제거 후 본론만 남긴다.
        sentences = re.split(r"(?<=[.!?])\s+", reply.strip())
        kept: list[str] = []
        for s in sentences:
            low = s.lower().strip()
            if low.startswith("안녕하세요") or "저는 siro" in low or "제 이름은 siro" in low or low.startswith("반가워요"):
                continue
            kept.append(s)

        if kept:
            return " ".join(kept).strip()
        return reply

    def chat(self, user_text: str) -> str:
        is_first_turn = not any(m.get("role") == "user" for m in self.messages)
        fast = self._fast_path(user_text)
        if fast:
            fast = self._polish_reply(fast)
            fast = self._enforce_direct_request_reply(user_text, fast)
            fast = self._enforce_first_turn_direct(user_text, fast, is_first_turn)
            self.messages.append({"role": "user", "content": user_text})
            self.messages.append({"role": "assistant", "content": fast})
            self._trim_history()
            return fast

        self.messages.append({"role": "user", "content": user_text})
        self._trim_history()

        tool_defs = self.tools.schemas()
        final_text = ""
        for _ in range(4):
            resp = self.client.chat(messages=self.messages, tools=tool_defs)
            msg = resp.get("message", {})
            assistant_text = (msg.get("content") or "").strip()
            tool_calls = parse_tool_calls(msg)

            if not tool_calls:
                final_text = self._polish_reply(assistant_text)
                final_text = self._enforce_direct_request_reply(user_text, final_text)
                final_text = self._enforce_first_turn_direct(user_text, final_text, is_first_turn)
                self.messages.append({"role": "assistant", "content": final_text})
                break

            self.messages.append(msg)
            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("arguments", {})
                result = self.tools.call(name, args)
                self.messages.append(
                    {
                        "role": "tool",
                        "name": name,
                        "content": result,
                    }
                )

        if not final_text:
            final_text = self._polish_reply("죄송해요, 응답을 만드는 중 문제가 있었어요. 한 번만 다시 말씀해주시겠어요?")
            final_text = self._enforce_direct_request_reply(user_text, final_text)
            final_text = self._enforce_first_turn_direct(user_text, final_text, is_first_turn)
            self.messages.append({"role": "assistant", "content": final_text})

        self._trim_history()
        return final_text

    def quick_save_memory(self, text: str) -> str:
        res = self.tools.call("save_memory", {"text": text})
        data = json.loads(res)
        if data.get("ok"):
            return "메모 저장 완료했습니다."
        return f"메모 저장 실패: {data.get('message', '오류')}"
