from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from siro.assistant import SiroAssistant
from siro.config import SiroConfig
from siro.speech import Speaker, SpeechToText


def _configure_qt_plugin_path() -> None:
    # macOS에서 Qt 플러그인 탐색 실패를 피하기 위해 경로를 강제 설정
    spec = importlib.util.find_spec("PySide6")
    if not spec or not spec.submodule_search_locations:
        return

    pkg_dir = Path(list(spec.submodule_search_locations)[0])
    qt_root = pkg_dir / "Qt"
    plugin_root = qt_root / "plugins"
    platform_dir = plugin_root / "platforms"
    lib_dir = qt_root / "lib"

    if plugin_root.exists():
        os.environ["QT_PLUGIN_PATH"] = str(plugin_root)
    if platform_dir.exists():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_dir)

    # Qt framework 로딩 경로도 보강 (macOS)
    if lib_dir.exists():
        old_fw = os.environ.get("DYLD_FRAMEWORK_PATH", "")
        old_lib = os.environ.get("DYLD_LIBRARY_PATH", "")
        os.environ["DYLD_FRAMEWORK_PATH"] = f"{lib_dir}:{old_fw}" if old_fw else str(lib_dir)
        os.environ["DYLD_LIBRARY_PATH"] = f"{lib_dir}:{old_lib}" if old_lib else str(lib_dir)


def main() -> int:
    _configure_qt_plugin_path()
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as e:
        raise SystemExit(
            "PySide6가 설치되어 있지 않습니다. `python3 -m pip install -r requirements.txt`를 먼저 실행해 주세요."
        ) from e
    from siro.ui import SiroWindow

    cfg = SiroConfig.load()
    app = QApplication(sys.argv)

    assistant = SiroAssistant(cfg)
    speaker = Speaker(
        rate=cfg.tts_rate,
        voice_id=cfg.tts_voice_id,
        output_device=cfg.tts_output_device,
    )
    stt = SpeechToText(device_index=(cfg.stt_device_index if cfg.stt_device_index >= 0 else None))

    window = SiroWindow(assistant=assistant, speaker=speaker, stt=stt, config=cfg)
    window.show()

    code = app.exec()
    speaker.stop()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
