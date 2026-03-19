# Siro
![Siro logo](assets/logo_a.png)
Qwen2.5:3b 기반의 간단한 한국어 AI 음성 비서입니다.

## ✨ 주요 기능
- 음성 입력(STT) -> 텍스트
- Ollama(Qwen2.5:3b) 기반 대화
- Function Calling(함수 호출)
- 개인화 메모(RAG 유사 검색)
- 음성 출력(TTS, pyttsx3)
- 친구 같은 톤 + 존댓말 캐릭터(Siro)
- 게임 로컬 엔진: 끝말잇기, 연상 단어, 퀴즈, 스무고개, 짧은 이야기 이어쓰기, 숫자 맞추기
- 설정 창: Ollama URL/모델, 말투 스타일, TTS 사용/속도, 히스토리 길이
- 온보딩/헬스체크: Ollama 연결, 모델 준비, STT/TTS 상태 자동 점검
- 메모 검색 고도화: 해시 임베딩 유사도 기반 개인화 검색
- 메모리 제어: `기억해: ...`, `잊어줘: ...`, `이건 저장하지마`
- 음성 UX: 핫워드(Siro야), 말하는 중 입력 시 TTS 중단(barge-in)
- 확장 설정: 응답 길이/말투 강도/게임 난이도
- 디버그 탭: 도구 호출 로그 + 오류 로그 tail 확인
- 실행 안전장치: 화이트리스트 실행 요청 + 승인/취소 워크플로우
- 실행 정책 설정: 실행 전 승인 필요 여부를 설정에서 제어

## 💬 사용 예시
- "기분이 좀 다운됐어요"
- "숫자 맞추기 게임 시작해줘"
- "메모 저장: 나는 주말에 등산을 좋아해"
- "기억해: 나는 주말에 등산을 좋아해"
- "잊어줘: 등산"
- "사파리 열어줘" (승인 필요 모드면 승인 후 실행)
- "승인" / "취소"
- "내 취미 관련 메모 보여줘"
- "짧은 농담 하나 해줘"
- "오늘 분위기에 맞는 음악 추천해줘"
- "끝말잇기 게임 시작해줘"
- "과학 퀴즈 게임 시작해줘"
- "게임 상태 알려줘"

## 🛠 실행 전 준비
1. Ollama 설치 후 모델 준비
```bash
ollama pull qwen2.5:3b
```
2. Python 가상환경(권장) 후 의존성 설치
```bash
pip install -r requirements.txt
```

> macOS에서 `pyaudio` 설치가 어렵다면 STT 기능은 비활성 상태로도 텍스트 채팅/TTS는 동작합니다.

## ▶️ 실행
### macOS
```bash
./run_macos.command
```

### Linux (Debian/Ubuntu)
```bash
./run_linux_debian.sh
```

### Windows
```bat
run_windows.bat
```

직접 실행하려면:
```bash
python main.py
```

GUI가 계속 실패하면 CLI 모드로 기능 검증:
```bash
python cli.py
```

## 🧯 macOS Qt 오류 해결
`Could not find the Qt platform plugin "cocoa"` 오류가 나면 아래 순서로 실행해 주세요.
```bash
unset QT_PLUGIN_PATH
unset QT_QPA_PLATFORM_PLUGIN_PATH
unset QT_QPA_PLATFORM
python -m pip install -U pip
python -m pip install -r requirements.txt --force-reinstall
python main.py
```

그래도 동일하면 `Python 3.12` 가상환경을 새로 만들어 재설치하는 것을 권장합니다.
