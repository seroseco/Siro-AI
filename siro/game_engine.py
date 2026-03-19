from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuizState:
    index: int = 0
    score: int = 0
    category: str = "일반"
    questions: list[dict[str, str]] = field(default_factory=list)


@dataclass
class TwentyState:
    target: dict[str, Any] | None = None
    turn: int = 0


@dataclass
class GameState:
    active: str | None = None
    word_chain_last: str | None = None
    word_chain_used: set[str] = field(default_factory=set)
    association_last: str | None = None
    quiz: QuizState = field(default_factory=QuizState)
    twenty: TwentyState = field(default_factory=TwentyState)
    story_lines: list[str] = field(default_factory=list)
    number_target: int | None = None
    number_tries: int = 0


class GameEngine:
    def __init__(self) -> None:
        self.state = GameState()
        self.difficulty = "보통"
        self.word_pool = [
            "가방", "방울", "울음", "음악", "악기", "기차", "차표", "표정", "정보", "보물", "물감", "감자",
            "자리", "리본", "본능", "능력", "역할", "할인", "인형", "형광", "광고", "고양이", "이야기", "기상",
            "상자", "자전거", "거울", "울타리", "리듬", "음표", "표현", "현실", "실수", "수박", "박수", "수영",
            "영화", "화분", "분식", "식탁", "탁자", "자동차", "차량", "량심", "심장", "장난", "난로", "로봇",
            "봇짐", "짐승", "승부", "부엌", "억지", "지구", "구름", "음료", "요리", "리더", "더위", "위로",
            "로션", "연필", "필통", "통화", "화장", "장미", "미소", "소금", "금요일", "일기", "기억", "지식",
            "식물", "물병", "병원", "원숭이", "이불", "불꽃", "꽃병", "병아리", "음성", "성장", "장갑", "갑자기",
            "기분", "분위기", "기차역", "역사", "사과", "과자", "자율", "율동", "동화", "화면", "면접", "접시",
            "시간", "간식", "식빵", "빵집",
        ]
        self.association_map = {
            "바다": ["파도", "여름", "푸른빛", "모래"],
            "커피": ["향", "카페", "집중", "아메리카노"],
            "비": ["우산", "촉촉함", "감성", "장화"],
            "코딩": ["버그", "디버깅", "성취감", "집중"],
            "여행": ["설렘", "사진", "지도", "모험"],
            "음악": ["리듬", "가사", "멜로디", "플레이리스트"],
        }
        self.quiz_bank_by_category: dict[str, list[dict[str, str]]] = {
            "일반": [
                {"q": "대한민국의 수도는 어디인가요?", "a": "서울"},
                {"q": "1바이트는 몇 비트인가요?", "a": "8"},
                {"q": "지구는 태양계에서 몇 번째 행성인가요?", "a": "3"},
                {"q": "파이썬에서 리스트 길이를 구하는 함수는?", "a": "len"},
                {"q": "물의 화학식은 무엇인가요?", "a": "h2o"},
            ],
            "과학": [
                {"q": "빛의 속도는 약 초당 몇 km인가요?", "a": "300000"},
                {"q": "지구의 위성 이름은 무엇인가요?", "a": "달"},
                {"q": "식물이 광합성에 주로 사용하는 기체는?", "a": "이산화탄소"},
                {"q": "원자 번호 1번 원소는?", "a": "수소"},
                {"q": "중력 가속도는 약 얼마인가요?", "a": "9.8"},
            ],
            "코딩": [
                {"q": "파이썬에서 함수 정의 키워드는?", "a": "def"},
                {"q": "HTML의 약자는?", "a": "hypertext markup language"},
                {"q": "Git에서 변경사항 임시 저장 명령은?", "a": "stash"},
                {"q": "REST에서 조회에 주로 쓰는 HTTP 메서드는?", "a": "get"},
                {"q": "파이썬에서 예외 처리 키워드 조합은?", "a": "try except"},
            ],
            "상식": [
                {"q": "대한민국 국보 1호는 무엇이었나요?", "a": "숭례문"},
                {"q": "올림픽은 몇 년마다 열리나요?", "a": "4"},
                {"q": "세계에서 가장 큰 대양은?", "a": "태평양"},
                {"q": "피카소는 어느 나라 출신인가요?", "a": "스페인"},
                {"q": "한국의 화폐 단위는?", "a": "원"},
            ],
        }
        self.twenty_targets = [
            {
                "name": "고양이",
                "aliases": ["냥이"],
                "alive": True,
                "edible": False,
                "manmade": False,
                "indoor": True,
                "move": True,
                "size": "중간",
                "category": "동물",
            },
            {
                "name": "피자",
                "aliases": [],
                "alive": False,
                "edible": True,
                "manmade": True,
                "indoor": True,
                "move": False,
                "size": "중간",
                "category": "음식",
            },
            {
                "name": "자동차",
                "aliases": ["차"],
                "alive": False,
                "edible": False,
                "manmade": True,
                "indoor": False,
                "move": True,
                "size": "큼",
                "category": "탈것",
            },
            {
                "name": "사과",
                "aliases": [],
                "alive": False,
                "edible": True,
                "manmade": False,
                "indoor": True,
                "move": False,
                "size": "작음",
                "category": "과일",
            },
            {
                "name": "노트북",
                "aliases": ["랩탑"],
                "alive": False,
                "edible": False,
                "manmade": True,
                "indoor": True,
                "move": False,
                "size": "중간",
                "category": "전자기기",
            },
        ]

    def set_difficulty(self, level: str) -> None:
        lv = level.strip()
        if lv not in {"쉬움", "보통", "어려움"}:
            lv = "보통"
        self.difficulty = lv

    def start(self, game: str, category: str | None = None) -> str:
        game = game.strip().lower()

        aliases = {
            "끝말잇기": "word_chain",
            "wordchain": "word_chain",
            "연상": "association",
            "연상단어": "association",
            "퀴즈": "quiz",
            "스무고개": "twenty",
            "이야기": "story",
            "이야기이어쓰기": "story",
            "숫자맞추기": "number_guess",
        }
        game = aliases.get(game, game)
        self.stop()
        self.state.active = game

        if game == "word_chain":
            seed = random.choice(self.word_pool)
            self.state.word_chain_last = seed
            self.state.word_chain_used = {seed}
            return f"끝말잇기 시작할게요. 제 시작 단어는 '{seed}'입니다. 마지막 글자로 이어주세요."

        if game == "association":
            self.state.association_last = None
            return "연상 단어 게임 시작할게요. 단어 하나를 말해주시면 제가 연상 단어를 이어볼게요."

        if game == "quiz":
            selected = self._pick_quiz_category(category)
            pool = list(self.quiz_bank_by_category[selected])
            random.shuffle(pool)
            q_count = {"쉬움": 3, "보통": 5, "어려움": 7}.get(self.difficulty, 5)
            pool = pool[: min(q_count, len(pool))]
            self.state.quiz = QuizState(index=0, score=0, category=selected, questions=pool)
            return f"{selected} 퀴즈 시작합니다. 1번 문제: {pool[0]['q']}"

        if game == "twenty":
            self.state.twenty = TwentyState(target=random.choice(self.twenty_targets), turn=0)
            return "스무고개 시작합니다. 제가 하나를 정했어요. 예/아니오 질문을 해주시거나, 정답을 바로 맞춰보세요."

        if game == "story":
            opener = random.choice([
                "비가 오던 저녁, 작은 편지 한 장이 문틈으로 들어왔습니다.",
                "아침 7시, 알람 대신 낯선 노랫소리가 창밖에서 들렸습니다.",
                "오래된 서랍을 열자 지도 한 장과 열쇠가 함께 나왔습니다.",
            ])
            self.state.story_lines = [opener]
            return f"이야기 이어쓰기 시작할게요. 시작 문장: {opener} 이제 이어서 한 문장 말씀해 주세요."

        if game == "number_guess":
            max_num = {"쉬움": 20, "보통": 50, "어려움": 100}.get(self.difficulty, 50)
            self.state.number_target = random.randint(1, max_num)
            self.state.number_tries = 0
            return f"숫자 맞추기 시작. 1~{max_num} 숫자를 입력해 주세요."

        self.state.active = None
        return "지원하지 않는 게임입니다. 끝말잇기/연상/퀴즈/스무고개/이야기/숫자맞추기 중에서 선택해 주세요."

    def stop(self) -> str:
        self.state = GameState()
        return "게임을 종료했어요."

    def status(self) -> str:
        if not self.state.active:
            return "현재 진행 중인 게임이 없어요."
        if self.state.active == "quiz" and self.state.quiz.questions:
            return (
                f"현재 게임: 퀴즈({self.state.quiz.category}) "
                f"{self.state.quiz.index + 1}/{len(self.state.quiz.questions)} 문제 진행 중"
            )
        return f"현재 게임: {self.state.active} (난이도: {self.difficulty})"

    def turn(self, text: str) -> str:
        if not self.state.active:
            return "진행 중인 게임이 없어요. 먼저 게임 시작을 요청해 주세요."

        if self.state.active == "word_chain":
            return self._turn_word_chain(text)
        if self.state.active == "association":
            return self._turn_association(text)
        if self.state.active == "quiz":
            return self._turn_quiz(text)
        if self.state.active == "twenty":
            return self._turn_twenty(text)
        if self.state.active == "story":
            return self._turn_story(text)
        if self.state.active == "number_guess":
            return self._turn_number_guess(text)

        return "알 수 없는 게임 상태예요."

    def _extract_word(self, text: str) -> str:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)
        return tokens[0] if tokens else ""

    def _start_variants(self, ch: str) -> set[str]:
        mapping = {
            "라": {"라", "나"},
            "래": {"래", "내"},
            "로": {"로", "노"},
            "뢰": {"뢰", "뇌"},
            "루": {"루", "누"},
            "르": {"르", "느"},
            "리": {"리", "이"},
            "려": {"려", "여"},
            "례": {"례", "예"},
            "료": {"료", "요"},
            "류": {"류", "유"},
            "니": {"니", "이"},
            "녀": {"녀", "여"},
            "뇨": {"뇨", "요"},
            "뉴": {"뉴", "유"},
        }
        return mapping.get(ch, {ch})

    def _turn_word_chain(self, text: str) -> str:
        word = self._extract_word(text)
        if len(word) < 2:
            return "두 글자 이상 단어로 입력해 주세요."

        last = self.state.word_chain_last or ""
        if last:
            expected = self._start_variants(last[-1])
            if word[0] not in expected:
                expected_text = "/".join(sorted(expected))
                return f"규칙상 '{expected_text}'로 시작해야 해요. 다시 도전해 주세요."

        if word in self.state.word_chain_used:
            return "이미 나온 단어예요. 다른 단어로 부탁드려요."

        self.state.word_chain_used.add(word)
        user_last_char = word[-1]
        expected = self._start_variants(user_last_char)
        candidates = [
            w for w in self.word_pool if w[0] in expected and w not in self.state.word_chain_used
        ]

        if not candidates:
            self.stop()
            return "제가 이을 단어를 못 찾았어요. 이번 판은 승리하셨어요."

        bot = random.choice(candidates)
        self.state.word_chain_used.add(bot)
        self.state.word_chain_last = bot
        next_expected = "/".join(sorted(self._start_variants(bot[-1])))
        return f"좋아요, 저는 '{bot}'입니다. 이제 '{next_expected}'로 시작하는 단어 부탁드려요."

    def _turn_association(self, text: str) -> str:
        word = self._extract_word(text)
        if not word:
            return "단어 하나를 먼저 말씀해 주세요."
        candidates = self.association_map.get(word)
        if not candidates:
            pool = ["추억", "설렘", "도전", "휴식", "에너지", "여유", "영감", "몰입"]
            reply = random.choice(pool)
        else:
            reply = random.choice(candidates)
        self.state.association_last = reply
        return f"제가 떠올린 단어는 '{reply}'예요. 또 하나 던져주세요."

    def _pick_quiz_category(self, category: str | None) -> str:
        if not category:
            return "일반"
        low = category.strip().lower()
        aliases = {
            "일반": "일반",
            "general": "일반",
            "과학": "과학",
            "science": "과학",
            "코딩": "코딩",
            "coding": "코딩",
            "개발": "코딩",
            "상식": "상식",
            "trivia": "상식",
        }
        return aliases.get(low, "일반")

    def _turn_quiz(self, text: str) -> str:
        qs = self.state.quiz.questions
        idx = self.state.quiz.index
        if idx >= len(qs):
            total = len(qs)
            score = self.state.quiz.score
            self.stop()
            return f"퀴즈 끝. 총점은 {score}/{total}점이에요."

        answer = str(qs[idx]["a"]).lower().replace(" ", "")
        user = text.strip().lower().replace(" ", "")
        correct = answer in user or user in answer
        if correct:
            self.state.quiz.score += 1
            feedback = "정답입니다."
        else:
            feedback = f"아쉽지만 오답이에요. 정답은 '{qs[idx]['a']}'입니다."

        self.state.quiz.index += 1
        if self.state.quiz.index >= len(qs):
            total = len(qs)
            score = self.state.quiz.score
            category = self.state.quiz.category
            self.stop()
            return f"{feedback} {category} 퀴즈 종료. 총점은 {score}/{total}점이에요."

        next_idx = self.state.quiz.index + 1
        total = len(qs)
        next_q = qs[self.state.quiz.index]["q"]
        return f"{feedback} 다음 문제({next_idx}/{total}): {next_q}"

    def _turn_twenty(self, text: str) -> str:
        st = self.state.twenty
        target = st.target
        if not target:
            return "스무고개 상태가 꼬였어요. 다시 시작해 주세요."

        st.turn += 1
        low = text.lower().strip()

        names = [str(target["name"]).lower()] + [str(x).lower() for x in target.get("aliases", [])]
        if any(n and n in low for n in names) or low.startswith("정답") or low.startswith("맞춰"):
            self.stop()
            return f"정답. 제가 고른 단어는 '{target['name']}'였어요."

        yes_no = self._answer_twenty_yes_no(low, target)
        limit = {"쉬움": 25, "보통": 20, "어려움": 15}.get(self.difficulty, 20)
        remain = max(0, limit - st.turn)
        if remain == 0:
            reveal = target["name"]
            self.stop()
            return f"{limit}번 질문이 끝났어요. 정답은 '{reveal}'였습니다."

        hint = ""
        if st.turn in {8, 14}:
            hint = f" 힌트: 카테고리는 '{target.get('category', '알 수 없음')}'예요."

        return f"답변: {yes_no}. 남은 질문 횟수는 {remain}번입니다.{hint}"

    def _answer_twenty_yes_no(self, question: str, target: dict[str, Any]) -> str:
        if any(k in question for k in ["먹", "음식", "마실"]):
            return "네" if target["edible"] else "아니요"
        if any(k in question for k in ["살아", "동물", "생물"]):
            return "네" if target["alive"] else "아니요"
        if any(k in question for k in ["사람이 만든", "인공", "기계"]):
            return "네" if target["manmade"] else "아니요"
        if any(k in question for k in ["실내", "집 안"]):
            return "네" if target["indoor"] else "아니요"
        if any(k in question for k in ["움직", "이동", "달리"]):
            return "네" if target["move"] else "아니요"
        if any(k in question for k in ["작", "손바닥", "작은"]):
            return "네" if target["size"] == "작음" else "아니요"
        if any(k in question for k in ["크", "큰", "대형"]):
            return "네" if target["size"] == "큼" else "아니요"
        return "잘 모르겠어요"

    def _turn_story(self, text: str) -> str:
        user_line = text.strip()
        if not user_line:
            return "한 문장으로 이어주세요."

        self.state.story_lines.append(f"사용자: {user_line}")
        endings = [
            "그리고 그 순간, 멀리서 익숙한 발소리가 들렸습니다.",
            "하지만 예상과 다르게 문은 저절로 열리기 시작했죠.",
            "그 선택이 오늘의 모험을 완전히 바꿔놓았습니다.",
        ]
        bot_line = random.choice(endings)
        self.state.story_lines.append(f"Siro: {bot_line}")
        return f"좋아요, 이어서: {bot_line} 계속 이어가실래요?"

    def _turn_number_guess(self, text: str) -> str:
        if self.state.number_target is None:
            return "게임이 시작되지 않았어요."
        try:
            guess = int(text.strip())
        except ValueError:
            return "숫자로 입력해 주세요."

        if not 1 <= guess <= 50:
            return "1~50 사이 숫자로 입력해 주세요."

        self.state.number_tries += 1
        target = self.state.number_target
        if guess < target:
            return "UP. 더 큰 숫자입니다."
        if guess > target:
            return "DOWN. 더 작은 숫자입니다."

        tries = self.state.number_tries
        self.stop()
        return f"정답입니다. {tries}번 만에 맞추셨어요."
