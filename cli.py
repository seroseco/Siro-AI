from __future__ import annotations

from siro.assistant import SiroAssistant
from siro.config import SiroConfig


def main() -> int:
    assistant = SiroAssistant(SiroConfig())
    print("Siro CLI 모드입니다. 종료하려면 /exit 입력")
    while True:
        try:
            text = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            return 0

        if not text:
            continue
        if text in {"/exit", "/quit"}:
            print("Siro> 다음에 또 만나요.")
            return 0

        try:
            answer = assistant.chat(text)
        except Exception as e:
            print(f"Siro> 오류: {e}")
            continue

        print(f"Siro> {answer}")


if __name__ == "__main__":
    raise SystemExit(main())
