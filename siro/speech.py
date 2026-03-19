from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
from typing import Callable, Optional

import pyttsx3

try:
    import speech_recognition as sr
except Exception:  # pragma: no cover
    sr = None


class Speaker:
    def __init__(self, rate: int = 180, voice_id: str = "", output_device: str = "") -> None:
        self._rate = rate
        self._voice_id = voice_id
        self._is_macos = sys.platform == "darwin"
        self.engine = self._build_engine() if not self._is_macos else None
        self._current_proc: subprocess.Popen[str] | None = None
        if output_device:
            self.set_output_device(output_device)
        self._q: queue.Queue[Optional[str]] = queue.Queue()
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._start_worker()

    def _build_engine(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", self._rate)
        if self._voice_id:
            try:
                engine.setProperty("voice", self._voice_id)
            except Exception:
                pass
        return engine

    def _start_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _restart_engine(self) -> None:
        if self._is_macos:
            return
        with self._lock:
            try:
                assert self.engine is not None
                self.engine.stop()
            except Exception:
                pass
            self.engine = self._build_engine()

    def say(self, text: str) -> None:
        if not text or not text.strip():
            return
        self._start_worker()
        self._q.put(text)

    def set_rate(self, rate: int) -> None:
        self._rate = int(rate)
        if self._is_macos:
            return
        with self._lock:
            assert self.engine is not None
            self.engine.setProperty("rate", self._rate)

    def list_voices(self) -> list[tuple[str, str]]:
        if self._is_macos and shutil.which("say"):
            try:
                proc = subprocess.run(
                    ["say", "-v", "?"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                out: list[tuple[str, str]] = []
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    voice = line.split(maxsplit=1)[0].strip()
                    if voice:
                        out.append((voice, voice))
                return out
            except Exception:
                return []

        assert self.engine is not None
        voices = self.engine.getProperty("voices") or []
        out: list[tuple[str, str]] = []
        for v in voices:
            vid = str(getattr(v, "id", "") or "")
            name = str(getattr(v, "name", "") or vid or "voice")
            out.append((vid, name))
        return out

    def set_voice(self, voice_id: str) -> bool:
        if not voice_id:
            return False
        try:
            self._voice_id = voice_id
            if self._is_macos:
                return True
            with self._lock:
                assert self.engine is not None
                self.engine.setProperty("voice", voice_id)
            return True
        except Exception:
            return False

    def list_output_devices(self) -> list[str]:
        # macOS: switchaudio-osx (SwitchAudioSource) is the most reliable way.
        if shutil.which("SwitchAudioSource"):
            try:
                proc = subprocess.run(
                    ["SwitchAudioSource", "-a", "-t", "output"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
                if lines:
                    return lines
            except Exception:
                pass
        return []

    def set_output_device(self, device_name: str) -> bool:
        if not device_name:
            return True
        if not shutil.which("SwitchAudioSource"):
            return False
        try:
            subprocess.run(
                ["SwitchAudioSource", "-s", device_name, "-t", "output"],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except Exception:
            return False

    def interrupt(self) -> None:
        with self._lock:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            if self._is_macos and self._current_proc is not None:
                try:
                    if self._current_proc.poll() is None:
                        self._current_proc.terminate()
                except Exception:
                    pass
            try:
                if self.engine is not None:
                    self.engine.stop()
            except Exception:
                pass

    def stop(self) -> None:
        self.interrupt()
        self._q.put(None)

    def _speak_macos(self, text: str) -> None:
        if not shutil.which("say"):
            return
        cmd = ["say", "-r", str(max(80, min(420, int(self._rate))))]
        if self._voice_id:
            cmd.extend(["-v", self._voice_id])
        cmd.append(text)
        proc: subprocess.Popen[str]
        with self._lock:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            self._current_proc = proc
        try:
            proc.wait()
        finally:
            with self._lock:
                if self._current_proc is proc:
                    self._current_proc = None

    def _run(self) -> None:
        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                if self._is_macos:
                    self._speak_macos(text)
                    continue
                with self._lock:
                    assert self.engine is not None
                    self.engine.say(text)
                    self.engine.runAndWait()
            except Exception:
                # pyttsx3가 간헐적으로 멈추는 경우가 있어 엔진을 재생성 후 1회 재시도
                try:
                    if self._is_macos:
                        self._speak_macos(text)
                        continue
                    self._restart_engine()
                    with self._lock:
                        assert self.engine is not None
                        self.engine.say(text)
                        self.engine.runAndWait()
                except Exception:
                    continue


class SpeechToText:
    def __init__(self, device_index: int | None = None) -> None:
        self.enabled = sr is not None
        self._recognizer = sr.Recognizer() if self.enabled else None
        self.device_index = device_index

    def list_input_devices(self) -> list[tuple[int, str]]:
        if not self.enabled:
            return []
        names = sr.Microphone.list_microphone_names()
        return [(i, n) for i, n in enumerate(names)]

    def set_input_device(self, device_index: int | None) -> None:
        self.device_index = device_index

    def listen_once(
        self,
        timeout: int = 5,
        phrase_time_limit: int = 8,
        on_stage: Callable[[str], None] | None = None,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("SpeechRecognition 패키지를 찾지 못했습니다.")

        assert self._recognizer is not None
        if on_stage:
            on_stage("마이크 입력 대기 중...")
        with sr.Microphone(device_index=self.device_index) as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            if on_stage:
                on_stage("듣고 있어요...")
            audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

        try:
            if on_stage:
                on_stage("음성을 텍스트로 변환 중...")
            return self._recognizer.recognize_google(audio, language="ko-KR")
        except sr.UnknownValueError as e:
            raise RuntimeError("음성을 인식하지 못했습니다.") from e
        except sr.RequestError as e:
            raise RuntimeError("STT 서비스 요청에 실패했습니다.") from e

    def listen_stream(
        self,
        stop_event: threading.Event,
        timeout: int = 1,
        phrase_time_limit: int = 3,
        silence_timeout_count: int = 2,
        on_stage: Callable[[str], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
    ) -> str:
        if not self.enabled:
            raise RuntimeError("SpeechRecognition 패키지를 찾지 못했습니다.")

        assert self._recognizer is not None
        chunks: list[str] = []
        silence_hits = 0
        if on_stage:
            on_stage("마이크 입력 대기 중...")
        with sr.Microphone(device_index=self.device_index) as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
            if on_stage:
                on_stage("듣고 있어요... (다시 누르면 종료)")
            while not stop_event.is_set():
                try:
                    audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                except sr.WaitTimeoutError:
                    if chunks:
                        silence_hits += 1
                        if silence_hits >= max(1, silence_timeout_count):
                            break
                    continue

                try:
                    text = self._recognizer.recognize_google(audio, language="ko-KR").strip()
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    raise RuntimeError("STT 서비스 요청에 실패했습니다.") from e

                if text:
                    chunks.append(text)
                    silence_hits = 0
                    if on_partial:
                        on_partial(" ".join(chunks))

        return " ".join(chunks).strip()
