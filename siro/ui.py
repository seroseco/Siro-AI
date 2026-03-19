from __future__ import annotations

from pathlib import Path
import traceback
from datetime import datetime
from threading import Event, Thread
import time

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Signal, QTimer, Qt, QSize
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedLayout,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .assistant import SiroAssistant
from .config import SiroConfig
from .health import HealthChecker
from .speech import Speaker, SpeechToText


def _tint_icon(icon: QIcon, size: QSize, color: QColor) -> QIcon:
    src = icon.pixmap(max(size.width() * 2, 32), max(size.height() * 2, 32))
    if src.isNull():
        return icon

    # Some theme icons include large transparent padding.
    # Crop to alpha bounds first so the glyph fills the button area naturally.
    img = src.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    min_x, min_y = w, h
    max_x, max_y = -1, -1
    for y in range(h):
        for x in range(w):
            if QColor.fromRgba(img.pixel(x, y)).alpha() > 0:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if max_x >= min_x and max_y >= min_y:
        src = src.copy(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)

    src = src.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QPixmap(src.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.drawPixmap(0, 0, src)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), color)
    painter.end()
    return QIcon(out)


def _make_mic_icon(size: QSize, color: QColor) -> QIcon:
    w, h = size.width(), size.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, max(2.0, w * 0.09))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    # Microphone capsule
    capsule_w = w * 0.30
    capsule_h = h * 0.44
    capsule_x = (w - capsule_w) / 2
    capsule_y = h * 0.16
    p.drawRoundedRect(capsule_x, capsule_y, capsule_w, capsule_h, capsule_w / 2, capsule_w / 2)

    # U-shaped holder
    holder_x = w * 0.25
    holder_y = h * 0.33
    holder_w = w * 0.50
    holder_h = h * 0.42
    p.drawArc(int(holder_x), int(holder_y), int(holder_w), int(holder_h), 200 * 16, 140 * 16)

    # Stem and base
    cx = w / 2
    p.drawLine(cx, h * 0.72, cx, h * 0.84)
    p.drawLine(w * 0.34, h * 0.88, w * 0.66, h * 0.88)
    p.end()
    return QIcon(pm)


def _make_send_tail_icon(size: QSize, color: QColor) -> QIcon:
    w, h = size.width(), size.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, max(2.2, w * 0.1))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)

    # Upward arrow with tail
    p.drawLine(int(w * 0.50), int(h * 0.78), int(w * 0.50), int(h * 0.30))  # tail
    p.drawLine(int(w * 0.50), int(h * 0.30), int(w * 0.32), int(h * 0.48))  # head left
    p.drawLine(int(w * 0.50), int(h * 0.30), int(w * 0.68), int(h * 0.48))  # head right
    p.end()
    return QIcon(pm)


def _make_stop_icon(size: QSize, color: QColor) -> QIcon:
    w, h = size.width(), size.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    side = min(w, h) * 0.46
    x = (w - side) / 2
    y = (h - side) / 2
    p.drawRoundedRect(x, y, side, side, side * 0.16, side * 0.16)
    p.end()
    return QIcon(pm)


class UiSignals(QObject):
    assistant_done = Signal(str)
    stt_done = Signal(str)
    stt_partial = Signal(str)
    status = Signal(str)
    error = Signal(str, str)
    health_done = Signal(object, bool)
    hotword_heard = Signal(str)


class ChatInputTextEdit(QTextEdit):
    send_requested = Signal()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()
            try:
                im = QGuiApplication.inputMethod()
                if hasattr(im, "commit"):
                    im.commit()
            except Exception:
                pass
            QTimer.singleShot(35, self.send_requested.emit)
            return
        super().keyPressEvent(event)


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: SiroConfig,
        speaker: Speaker,
        stt: SpeechToText,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Siro 설정")
        self.resize(500, 580)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        self.url_edit = QLineEdit(config.ollama_base_url)
        self.model_edit = QLineEdit(config.model)

        self.style_combo = QComboBox()
        self.style_combo.addItems(["기본", "차분", "발랄"])
        idx = self.style_combo.findText(config.persona_style)
        if idx >= 0:
            self.style_combo.setCurrentIndex(idx)

        self.intensity_combo = QComboBox()
        self.intensity_combo.addItems(["약하게", "중간", "강하게"])
        idx = self.intensity_combo.findText(config.persona_intensity)
        if idx >= 0:
            self.intensity_combo.setCurrentIndex(idx)

        self.length_combo = QComboBox()
        self.length_combo.addItems(["짧게", "보통", "길게"])
        idx = self.length_combo.findText(config.response_length)
        if idx >= 0:
            self.length_combo.setCurrentIndex(idx)

        self.diff_combo = QComboBox()
        self.diff_combo.addItems(["쉬움", "보통", "어려움"])
        idx = self.diff_combo.findText(config.game_difficulty)
        if idx >= 0:
            self.diff_combo.setCurrentIndex(idx)

        self.tts_enabled_check = QCheckBox("TTS 음성 출력 사용")
        self.tts_enabled_check.setChecked(config.tts_enabled)

        self.hotword_enabled_check = QCheckBox("핫워드(Siro야) 사용")
        self.hotword_enabled_check.setChecked(config.hotword_enabled)
        self.action_confirm_check = QCheckBox("실행 전 승인 필요")
        self.action_confirm_check.setChecked(config.action_confirm_required)

        self.tts_rate_spin = QSpinBox()
        self.tts_rate_spin.setRange(110, 260)
        self.tts_rate_spin.setValue(int(config.tts_rate))

        self.history_spin = QSpinBox()
        self.history_spin.setRange(5, 100)
        self.history_spin.setValue(int(config.max_history))

        self.stt_device_combo = QComboBox()
        self.stt_device_combo.addItem("기본 입력 장치", -1)
        for idx, name in stt.list_input_devices():
            self.stt_device_combo.addItem(name, idx)
        stt_idx = self.stt_device_combo.findData(int(config.stt_device_index))
        if stt_idx >= 0:
            self.stt_device_combo.setCurrentIndex(stt_idx)
        else:
            self.stt_device_combo.setCurrentIndex(0)

        self.tts_output_combo = QComboBox()
        self.tts_output_combo.addItem("시스템 기본 출력", "")
        for name in speaker.list_output_devices():
            self.tts_output_combo.addItem(name, name)
        out_idx = self.tts_output_combo.findData(str(config.tts_output_device))
        if out_idx >= 0:
            self.tts_output_combo.setCurrentIndex(out_idx)
        else:
            self.tts_output_combo.setCurrentIndex(0)

        shell = QFrame()
        shell.setObjectName("settingsShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        layout.addWidget(shell)

        sidebar = QFrame()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(154)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(10, 12, 10, 10)
        side_layout.setSpacing(8)

        self._settings_nav_buttons: dict[str, QPushButton] = {}
        for text in ["일반", "음성", "입력/출력", "모델", "보안", "고급"]:
            b = QPushButton(text)
            b.setObjectName("sideItem")
            b.setProperty("active", False)
            b.clicked.connect(lambda _=False, key=text: self._switch_settings_section(key))
            side_layout.addWidget(b)
            self._settings_nav_buttons[text] = b
        side_layout.addStretch(1)

        content = QFrame()
        content.setObjectName("settingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 12, 14, 10)
        content_layout.setSpacing(0)

        self._settings_title_label = QLabel("일반")
        self._settings_title_label.setObjectName("settingsTitle")
        content_layout.addWidget(self._settings_title_label)

        self._settings_section_widgets: dict[str, list[QWidget]] = {}

        def add_divider() -> QFrame:
            line = QFrame()
            line.setObjectName("settingsDivider")
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Plain)
            content_layout.addWidget(line)
            return line

        def add_row(label: str, widget: QWidget, description: str = "") -> tuple[QWidget, QFrame]:
            row = QWidget()
            row.setObjectName("settingsRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            row_layout.setSpacing(10)
            left = QWidget()
            left_layout = QVBoxLayout(left)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(4)
            lbl = QLabel(label)
            lbl.setObjectName("rowLabel")
            left_layout.addWidget(lbl)
            if description:
                desc = QLabel(description)
                desc.setObjectName("rowDesc")
                desc.setWordWrap(True)
                left_layout.addWidget(desc)
            row_layout.addWidget(left, 1)
            row_layout.addWidget(widget, 0, Qt.AlignVCenter)
            content_layout.addWidget(row)
            divider = add_divider()
            return row, divider

        def add_to_section(section: str, label: str, widget: QWidget, description: str = "") -> None:
            row, divider = add_row(label, widget, description)
            self._settings_section_widgets.setdefault(section, []).extend([row, divider])

        # Right panel rows by section
        add_to_section("모델", "Ollama URL", self.url_edit)
        add_to_section("모델", "모델", self.model_edit)

        add_to_section("입력/출력", "입력 장치", self.stt_device_combo)
        add_to_section("입력/출력", "출력 장치", self.tts_output_combo)

        add_to_section("일반", "Siro 말투", self.style_combo)
        add_to_section("일반", "말투 강도", self.intensity_combo)
        add_to_section("일반", "응답 길이", self.length_combo)

        add_to_section("음성", "TTS 사용", self.tts_enabled_check)
        add_to_section("음성", "TTS 속도", self.tts_rate_spin)
        add_to_section("음성", "핫워드(Siro야)", self.hotword_enabled_check, "핫워드 감지 후 바로 듣기 모드로 전환합니다.")

        add_to_section("보안", "실행 보호", self.action_confirm_check, "앱 실행/URL 열기 전 승인 여부를 확인합니다.")

        add_to_section("고급", "게임 난이도", self.diff_combo)
        add_to_section("고급", "대화 히스토리", self.history_spin)

        content_layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset_btn = QPushButton("기본값 복원")
        reset_btn.setObjectName("resetButton")
        buttons.addButton(reset_btn, QDialogButtonBox.ResetRole)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setObjectName("primaryButton")
            ok_btn.setText("저장")
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setObjectName("subtleButton")
            cancel_btn.setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset_btn.clicked.connect(self._restore_defaults)
        content_layout.addWidget(buttons)

        shell_layout.addWidget(sidebar)
        shell_layout.addWidget(content, 1)
        self._apply_settings_theme()
        self._switch_settings_section("일반")

    def _switch_settings_section(self, section: str) -> None:
        self._settings_title_label.setText(section)
        for key, widgets in self._settings_section_widgets.items():
            visible = key == section
            for w in widgets:
                w.setVisible(visible)
        for key, btn in self._settings_nav_buttons.items():
            btn.setProperty("active", key == section)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _restore_defaults(self) -> None:
        self.url_edit.setText("http://localhost:11434")
        self.model_edit.setText("qwen2.5:3b")
        self.style_combo.setCurrentText("기본")
        self.intensity_combo.setCurrentText("중간")
        self.length_combo.setCurrentText("보통")
        self.diff_combo.setCurrentText("보통")
        self.tts_enabled_check.setChecked(True)
        self.hotword_enabled_check.setChecked(False)
        self.action_confirm_check.setChecked(True)
        self.tts_rate_spin.setValue(180)
        self.history_spin.setValue(20)
        self.stt_device_combo.setCurrentIndex(0)
        self.tts_output_combo.setCurrentIndex(0)

    def _apply_settings_theme(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #F8F9FD;
                color: #1E1B4B;
                font-family: "Pretendard", "Inter", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
                font-size: 14px;
            }
            QFrame#settingsShell {
                background: #F8F9FD;
                border: none;
                border-radius: 0px;
            }
            QFrame#settingsSidebar {
                background: #F2F4FA;
                border-right: 1px solid rgba(30, 27, 75, 0.08);
                border-top-left-radius: 22px;
                border-bottom-left-radius: 22px;
            }
            QFrame#settingsContent {
                background: transparent;
            }
            QLabel#settingsTitle {
                font-size: 36px;
                font-weight: 700;
                color: #1E1B4B;
                margin-bottom: 8px;
            }
            QPushButton#sideItem {
                border: none;
                border-radius: 14px;
                min-height: 36px;
                text-align: left;
                padding: 0 10px;
                font-size: 15px;
                background: transparent;
                color: #71798C;
            }
            QPushButton#sideItem[active="true"] {
                background: rgba(142, 84, 233, 0.16);
                color: #1E1B4B;
                font-weight: 700;
            }
            QWidget#settingsRow {
                background: transparent;
            }
            QLabel#rowLabel {
                color: #1E1B4B;
                font-size: 16px;
                font-weight: 600;
            }
            QLabel#rowDesc {
                color: #8B91A0;
                font-size: 12px;
            }
            QFrame#settingsDivider {
                color: rgba(30, 27, 75, 0.10);
                background: rgba(30, 27, 75, 0.10);
                max-height: 1px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: transparent;
                border: none;
                border-radius: 0px;
                min-width: 190px;
                min-height: 28px;
                padding: 0 2px;
                color: #1E1B4B;
                font-size: 15px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: none;
            }
            QCheckBox {
                spacing: 8px;
                padding: 3px 0;
                color: #1E1B4B;
                font-size: 16px;
            }
            QDialogButtonBox QPushButton {
                border: 1px solid rgba(30, 27, 75, 0.18);
                border-radius: 14px;
                min-height: 34px;
                min-width: 88px;
                padding: 0 10px;
                color: #1E1B4B;
                background: #FFFFFF;
            }
            QDialogButtonBox QPushButton:hover {
                background: #EEF2FB;
            }
            QPushButton#primaryButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #7B4FE2,
                    stop:1 #A56AF0
                );
                color: #FFFFFF;
                border: none;
            }
            QPushButton#primaryButton:hover {
                background: #8E54E9;
            }
            QPushButton#subtleButton, QPushButton#resetButton {
                background: rgba(255, 255, 255, 0.9);
            }
            """
        )

    def values(self) -> dict[str, object]:
        return {
            "ollama_base_url": self.url_edit.text().strip() or "http://localhost:11434",
            "model": self.model_edit.text().strip() or "qwen2.5:3b",
            "persona_style": self.style_combo.currentText(),
            "persona_intensity": self.intensity_combo.currentText(),
            "response_length": self.length_combo.currentText(),
            "game_difficulty": self.diff_combo.currentText(),
            "tts_enabled": self.tts_enabled_check.isChecked(),
            "tts_output_device": str(self.tts_output_combo.currentData() or ""),
            "stt_device_index": int(self.stt_device_combo.currentData() or -1),
            "hotword_enabled": self.hotword_enabled_check.isChecked(),
            "action_confirm_required": self.action_confirm_check.isChecked(),
            "tts_rate": int(self.tts_rate_spin.value()),
            "max_history": int(self.history_spin.value()),
        }


class ChatBubbleWidget(QWidget):
    def __init__(self, text: str, stamp: str, is_me: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatRow")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignRight if is_me else Qt.AlignLeft)

        wrap = QWidget()
        wrap.setObjectName("chatWrap")
        wrap_layout = QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(6)
        wrap_layout.setAlignment(Qt.AlignVCenter)

        bubble = QFrame()
        bubble.setObjectName("chatBubbleMe" if is_me else "chatBubbleBot")
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(18, 14, 18, 14)
        bubble_layout.setSpacing(0)
        bubble_shadow = QGraphicsDropShadowEffect(self)
        bubble_shadow.setBlurRadius(24)
        bubble_shadow.setOffset(0, 2)
        bubble_shadow.setColor(QColor(30, 27, 75, 28))
        bubble.setGraphicsEffect(bubble_shadow)

        label = QLabel(text)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setObjectName("chatTextMe" if is_me else "chatTextBot")
        label.setStyleSheet("background: transparent;")
        label.setMaximumWidth(324)
        bubble_layout.addWidget(label)

        time_label = QLabel(stamp)
        time_label.setObjectName("chatTime")
        time_label.setStyleSheet("background: transparent;")
        time_label.setAlignment(Qt.AlignBottom | (Qt.AlignRight if is_me else Qt.AlignLeft))

        if is_me:
            wrap_layout.addWidget(time_label, 0, Qt.AlignBottom)
            wrap_layout.addWidget(bubble, 0, Qt.AlignBottom)
        else:
            wrap_layout.addWidget(bubble, 0, Qt.AlignBottom)
            wrap_layout.addWidget(time_label, 0, Qt.AlignBottom)

        wrap.setMaximumWidth(420)
        outer.addWidget(wrap)


class SiroWindow(QMainWindow):
    def __init__(self, assistant: SiroAssistant, speaker: Speaker, stt: SpeechToText, config: SiroConfig) -> None:
        super().__init__()
        self.assistant = assistant
        self.speaker = speaker
        self.stt = stt
        self.config = config
        self.signals = UiSignals()
        self._hotword_running = False
        self._hotword_failed_notice = False
        self._animations: list[QPropertyAnimation] = []
        self._suggested_prompts = [
            "오늘 기분 체크해줘.",
            "짧은 농담 하나 해줘.",
            "끝말잇기 게임 시작해줘.",
        ]
        self._stt_listening = False
        self._stt_stop_event: Event | None = None
        self._stt_send_on_stop = False

        self.setWindowTitle("Siro")
        self.resize(480, 860)
        self.setMinimumSize(420, 720)
        self._build_ui()
        self._bind_signals()
        self._error_log_path = Path("data/siro_error.log")
        self._error_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._apply_theme()
        self.run_health_check(show_popup=False)
        if self.config.hotword_enabled:
            self._start_hotword_loop()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 4, 0, 0)
        top_row.setSpacing(8)
        top_row.setAlignment(Qt.AlignVCenter)
        self.logo_label = QLabel()
        self.logo_label.setObjectName("logoLabel")
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo_a.png"
        if logo_path.exists():
            pix = QPixmap(str(logo_path))
            if not pix.isNull():
                self.logo_label.setPixmap(
                    pix.scaled(168, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        self.logo_label.setFixedSize(170, 52)
        self.logo_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.settings_btn = QToolButton()
        settings_icon = QIcon.fromTheme("preferences-system")
        if not settings_icon.isNull():
            self.settings_btn.setIcon(settings_icon)
            self.settings_btn.setToolTip("설정")
        else:
            self.settings_btn.setText("설정")
        self.settings_btn.setFixedSize(38, 38)
        self.settings_btn.setIconSize(QSize(20, 20))
        self.health_btn = QToolButton()
        health_icon = QIcon.fromTheme("view-refresh")
        if health_icon.isNull():
            health_icon = self.style().standardIcon(QStyle.SP_BrowserReload)
        self.health_btn.setIcon(health_icon)
        self.health_btn.setToolTip("점검")
        self.health_btn.setFixedSize(38, 38)
        self.health_btn.setIconSize(QSize(20, 20))
        self.settings_btn.clicked.connect(self.on_open_settings)
        self.health_btn.clicked.connect(lambda: self.run_health_check(show_popup=True))
        self.status_label = QLabel("준비됨")
        self.status_label.setObjectName("statusLabel")

        top_row.addWidget(self.logo_label, 0, Qt.AlignVCenter)
        top_row.addStretch(1)
        top_row.addWidget(self.health_btn, 0, Qt.AlignVCenter)
        top_row.addWidget(self.settings_btn, 0, Qt.AlignVCenter)
        layout.addLayout(top_row)

        self.chat_view = QListWidget()
        self.chat_view.setAlternatingRowColors(False)
        self.chat_view.setSelectionMode(QAbstractItemView.NoSelection)
        self.chat_view.setFocusPolicy(Qt.NoFocus)
        self.chat_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.empty_state = self._build_empty_state()
        chat_stack_host = QWidget()
        self.chat_stack = QStackedLayout(chat_stack_host)
        self.chat_stack.setContentsMargins(0, 0, 0, 0)
        self.chat_stack.addWidget(self.empty_state)  # index 0
        self.chat_stack.addWidget(self.chat_view)  # index 1
        self.chat_stack.setCurrentIndex(0)
        layout.addWidget(chat_stack_host, 1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 2, 0, 0)
        input_row.setSpacing(-18)

        self.input_bar = QFrame()
        self.input_bar.setObjectName("inputBar")
        input_shadow = QGraphicsDropShadowEffect(self)
        input_shadow.setBlurRadius(28)
        input_shadow.setOffset(0, 3)
        input_shadow.setColor(QColor(30, 27, 75, 24))
        self.input_bar.setGraphicsEffect(input_shadow)
        bar_layout = QHBoxLayout(self.input_bar)
        bar_layout.setContentsMargins(12, 7, 8, 7)
        bar_layout.setSpacing(8)

        self.input_edit = ChatInputTextEdit()
        self.input_edit.setObjectName("chatInput")
        self.input_edit.setPlaceholderText("메시지를 입력하세요.")
        self.input_edit.setAcceptRichText(False)
        self.input_edit.setFixedHeight(36)
        self.input_edit.send_requested.connect(self.on_send_clicked)

        self.listen_btn = QToolButton()
        self.listen_btn.setObjectName("micButton")
        self.listen_btn.setIcon(_make_mic_icon(QSize(26, 26), QColor("#FFFFFF")))
        self.listen_btn.setToolTip("듣기")
        self.listen_btn.setIconSize(QSize(26, 26))
        self.listen_btn.clicked.connect(self.on_listen_clicked)
        self.listen_btn.setProperty("active", False)
        self._set_mic_shadow(False)

        self.send_btn = QToolButton()
        self.send_btn.setObjectName("sendButton")
        self.send_btn.setIcon(_make_send_tail_icon(QSize(24, 24), QColor("#FFFFFF")))
        self.send_btn.setToolTip("전송")
        self.send_btn.setIconSize(QSize(22, 22))
        self.send_btn.clicked.connect(self.on_send_clicked)
        self.listen_btn.setFixedSize(72, 72)
        self.send_btn.setFixedSize(38, 38)
        self.input_bar.setFixedHeight(52)

        bar_layout.addWidget(self.input_edit, 1)
        bar_layout.addWidget(self.send_btn)
        input_row.addWidget(self.listen_btn, 0, Qt.AlignVCenter)
        input_row.addWidget(self.input_bar, 1)
        layout.addLayout(input_row)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.status_label)
        layout.addLayout(bottom_row)
        layout.setStretch(1, 1)
        self._update_chat_empty_state()

    def _build_empty_state(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)
        v.setAlignment(Qt.AlignCenter)

        title = QLabel("Siro에 오신 걸 환영해요")
        title.setObjectName("emptyTitle")
        subtitle = QLabel("이렇게 말해보세요")
        subtitle.setObjectName("emptySubtitle")
        v.addWidget(title, 0, Qt.AlignHCenter)
        v.addWidget(subtitle, 0, Qt.AlignHCenter)

        for text in self._suggested_prompts:
            btn = QPushButton(text)
            btn.setObjectName("suggestionButton")
            btn.clicked.connect(lambda _=False, t=text: self._use_suggestion(t))
            v.addWidget(btn, 0, Qt.AlignHCenter)
        return wrap

    def _use_suggestion(self, text: str) -> None:
        self.input_edit.setPlainText(text)
        self.on_send_clicked()

    def _update_chat_empty_state(self) -> None:
        if self.chat_view.count() == 0:
            self.chat_stack.setCurrentIndex(0)
        else:
            self.chat_stack.setCurrentIndex(1)

    def _bind_signals(self) -> None:
        self.signals.assistant_done.connect(self._on_assistant_done)
        self.signals.stt_done.connect(self._on_stt_done)
        self.signals.stt_partial.connect(self._on_stt_partial)
        self.signals.status.connect(self.status_label.setText)
        self.signals.error.connect(self._on_error)
        self.signals.health_done.connect(self._on_health_done)
        self.signals.hotword_heard.connect(self._on_hotword_heard)

    def _append_chat(self, speaker: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        bubble = ChatBubbleWidget(text=text, stamp=stamp, is_me=(speaker == "나"))
        item = QListWidgetItem()
        self.chat_view.addItem(item)
        self.chat_view.setItemWidget(item, bubble)
        bubble.adjustSize()
        hint = bubble.sizeHint()
        item.setSizeHint(QSize(hint.width(), hint.height() + 10))
        self._update_chat_empty_state()

        # Subtle message fade-in animation
        fade = QGraphicsOpacityEffect(bubble)
        fade.setOpacity(0.0)
        bubble.setGraphicsEffect(fade)
        anim = QPropertyAnimation(fade, b"opacity", bubble)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._animations.append(anim)

        def _cleanup() -> None:
            try:
                bubble.setGraphicsEffect(None)
            except Exception:
                pass
            if anim in self._animations:
                self._animations.remove(anim)

        anim.finished.connect(_cleanup)
        anim.start()
        self.chat_view.scrollToBottom()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#appRoot {
                background: #F8F9FD;
                color: #1E1B4B;
                font-size: 14px;
                font-family: "Pretendard", "Inter", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
            }
            QLabel#statusLabel {
                color: #8A909A;
                font-size: 12px;
            }
            QLabel#emptyTitle {
                color: #1E1B4B;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#emptySubtitle {
                color: #7E8798;
                font-size: 13px;
                margin-bottom: 4px;
            }
            QLabel#logoLabel {
                background: transparent;
            }
            QTextEdit, QComboBox, QLineEdit {
                border: 1px solid rgba(117, 126, 155, 0.18);
                border-radius: 18px;
                padding: 7px 12px;
                background: rgba(255, 255, 255, 0.92);
                selection-background-color: #D4D9E2;
                selection-color: #1E1B4B;
            }
            QTextEdit:focus, QLineEdit:focus, QComboBox:focus {
                border: 1px solid rgba(117, 126, 155, 0.35);
                background: rgba(255, 255, 255, 0.96);
            }
            QFrame#inputBar {
                border: 1px solid rgba(117, 126, 155, 0.18);
                border-radius: 26px;
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.9),
                    stop:1 rgba(255, 255, 255, 0.76)
                );
            }
            QTextEdit#chatInput {
                border: none;
                border-radius: 20px;
                background: transparent;
                padding: 5px 2px;
            }
            QTextEdit#chatInput:focus {
                border: none;
                background: transparent;
            }
            QListWidget {
                border: none;
                border-radius: 0px;
                background: transparent;
                padding: 6px;
                outline: none;
            }
            QListWidget::viewport {
                background: transparent;
            }
            QFrame#chatBubbleMe {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6F5DE7,
                    stop:1 #C85BD6
                );
                border-radius: 20px;
            }
            QFrame#chatBubbleBot {
                background: rgba(255, 255, 255, 0.86);
                border: 1px solid rgba(117, 126, 155, 0.12);
                border-radius: 20px;
            }
            QLabel#chatTextMe {
                color: #FFFFFF;
                font-size: 15px;
                font-weight: 500;
            }
            QLabel#chatTextBot {
                color: #1E1B4B;
                font-size: 15px;
                font-weight: 500;
            }
            QLabel#chatTime {
                color: #8D94A0;
                font-size: 12px;
                padding: 0 4px;
            }
            QPushButton {
                border: 1px solid #D6DCE6;
                border-radius: 16px;
                padding: 7px 12px;
                background: #FFFFFF;
                color: #1E1B4B;
            }
            QPushButton#suggestionButton {
                min-height: 34px;
                padding: 0 14px;
                border-radius: 17px;
                background: rgba(255, 255, 255, 0.8);
            }
            QPushButton:hover {
                background: #F3F5F8;
            }
            QPushButton:pressed {
                background: #E8ECF2;
            }
            QPushButton:disabled, QTextEdit:disabled {
                background: #F1F3F6;
                color: #A2A8B2;
                border: 1px solid #E4E8EE;
            }
            QPushButton:checked, QToolButton:checked {
                background: #8E54E9;
                color: #FFFFFF;
                border: none;
            }
            QToolButton {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QToolButton[toolTip="점검"], QToolButton[toolTip="설정"] {
                color: #666B7A;
            }
            QToolButton#micButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #7B4FE2,
                    stop:1 #A56AF0
                );
                border: 1px solid rgba(30, 27, 75, 0.18);
                border-radius: 36px;
                color: #FFFFFF;
            }
            QToolButton#micButton[active="true"] {
                background: #FFFFFF;
                border: 1px solid rgba(142, 84, 233, 0.45);
                color: #8E54E9;
            }
            QToolButton#micButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #7045D7,
                    stop:1 #9C5EE8
                );
                border: none;
            }
            QToolButton#micButton[active="true"]:hover {
                background: #FFFFFF;
                border: 1px solid rgba(142, 84, 233, 0.6);
            }
            QToolButton#micButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6738CC,
                    stop:1 #8B53DD
                );
                border: none;
            }
            QToolButton#micButton[active="true"]:pressed {
                background: #F8F4FF;
                border: 1px solid rgba(142, 84, 233, 0.65);
            }
            QToolButton#sendButton {
                background: #1E1B4B;
                border: 1px solid rgba(30, 27, 75, 0.25);
                border-radius: 19px;
                color: #FFFFFF;
            }
            QToolButton#sendButton:hover {
                background: #17191D;
            }
            QToolButton#sendButton:pressed {
                background: #111216;
            }
            QToolButton:hover, QToolButton:pressed { background: transparent; border: none; }
            QToolButton:disabled { background: transparent; border: none; }
            QToolButton#micButton:disabled, QToolButton#sendButton:disabled {
                background: #C7CCD5;
                color: #F7F8FA;
            }
            QListWidget::item {
                margin: 2px 0px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 8px 2px 8px 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(138, 144, 154, 0.38);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(138, 144, 154, 0.66);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                width: 0px;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 6px;
                margin: 2px 8px 2px 8px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(138, 144, 154, 0.38);
                min-width: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(138, 144, 154, 0.66);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                height: 0px;
                width: 0px;
                border: none;
                background: transparent;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
            QWidget#chatRow, QWidget#chatWrap {
                background: transparent;
            }
            QLabel#chatTextMe, QLabel#chatTextBot, QLabel#chatTime {
                background: transparent;
            }
            """
        )

    def refresh_debug_panel(self) -> None:
        tool_log = self.assistant.debug_dump(limit=120)
        err_tail = ""
        if self._error_log_path.exists():
            lines = self._error_log_path.read_text(encoding="utf-8").splitlines()
            err_tail = "\n".join(lines[-40:])
        merged = (
            "[Tool/Assistant 로그]\n"
            f"{tool_log or '(없음)'}\n\n"
            "[Error 로그 tail]\n"
            f"{err_tail or '(없음)'}"
        )
        return merged

    def _set_busy(self, busy: bool) -> None:
        self.listen_btn.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.settings_btn.setEnabled(not busy)
        self.health_btn.setEnabled(not busy)
        self.input_edit.setEnabled(not busy)

    def _set_mic_shadow(self, active: bool) -> None:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(28 if active else 24)
        effect.setOffset(0, 3 if active else 2)
        effect.setColor(QColor("#8E54E9") if active else QColor(30, 27, 75, 36))
        self.listen_btn.setGraphicsEffect(effect)

    def _set_listening_ui(self, listening: bool) -> None:
        self._stt_listening = listening
        self.listen_btn.setProperty("active", listening)
        if listening:
            self.listen_btn.setIcon(_make_stop_icon(QSize(26, 26), QColor("#8E54E9")))
            self.listen_btn.setToolTip("정지")
        else:
            self.listen_btn.setIcon(_make_mic_icon(QSize(26, 26), QColor("#FFFFFF")))
            self.listen_btn.setToolTip("듣기")
        self.listen_btn.style().unpolish(self.listen_btn)
        self.listen_btn.style().polish(self.listen_btn)
        self._set_mic_shadow(listening)

        # Keep only critical controls disabled during active listening.
        self.send_btn.setEnabled(not listening)
        self.send_btn.setVisible(not listening)
        self.settings_btn.setEnabled(not listening)
        self.health_btn.setEnabled(not listening)

    def _log_error(self, title: str, detail: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._error_log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {title}\n{detail}\n\n")

    def _emit_error(self, user_message: str, detail: str) -> None:
        self.signals.error.emit(user_message, detail)

    def on_send_clicked(self) -> None:
        if self._stt_listening and self._stt_stop_event is not None:
            self._stt_stop_event.set()
            self._set_listening_ui(False)

        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        self.speaker.interrupt()
        self.input_edit.clear()
        self._append_chat("나", text)
        self.signals.status.emit("Siro가 생각 중...")
        self._set_busy(True)

        def run() -> None:
            try:
                answer = self.assistant.chat(text)
                self.signals.assistant_done.emit(answer)
            except Exception as e:
                self._emit_error(str(e), traceback.format_exc())

        Thread(target=run, daemon=True).start()

    def on_listen_clicked(self) -> None:
        if self._stt_listening:
            if self._stt_stop_event is not None:
                self._stt_send_on_stop = True
                self._stt_stop_event.set()
            self.signals.status.emit("마이크 종료 중...")
            return

        self.speaker.interrupt()
        self._stt_stop_event = Event()
        self._stt_send_on_stop = True
        self._set_listening_ui(True)
        self.signals.status.emit("듣고 있어요... (다시 누르면 종료)")

        def run() -> None:
            try:
                assert self._stt_stop_event is not None
                text = self.stt.listen_stream(
                    stop_event=self._stt_stop_event,
                    on_stage=self.signals.status.emit,
                    on_partial=self.signals.stt_partial.emit,
                )
                self.signals.stt_done.emit(text)
            except Exception as e:
                if self._stt_stop_event is not None and self._stt_stop_event.is_set():
                    self.signals.stt_done.emit(self.input_edit.toPlainText().strip())
                else:
                    self._emit_error(str(e), traceback.format_exc())

        Thread(target=run, daemon=True).start()

    def on_save_memo_clicked(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Siro", "저장할 메모 문장을 먼저 입력해 주세요.")
            return
        message = self.assistant.quick_save_memory(text)
        self._append_chat("Siro", message)
        self.signals.status.emit("메모 저장 완료")

    def on_tts_toggled(self, checked: bool) -> None:
        self.config.tts_enabled = checked
        self.config.save()

    def on_hotword_toggled(self, checked: bool) -> None:
        self.config.hotword_enabled = checked
        self.config.save()
        if checked:
            self._start_hotword_loop()
        else:
            self._hotword_running = False

    def on_open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self.speaker, self.stt, self)
        if dialog.exec() != QDialog.Accepted:
            return

        values = dialog.values()
        self.config.ollama_base_url = str(values["ollama_base_url"])
        self.config.model = str(values["model"])
        self.config.persona_style = str(values["persona_style"])
        self.config.persona_intensity = str(values["persona_intensity"])
        self.config.response_length = str(values["response_length"])
        self.config.game_difficulty = str(values["game_difficulty"])
        self.config.tts_enabled = bool(values["tts_enabled"])
        self.config.tts_output_device = str(values["tts_output_device"])
        self.config.stt_device_index = int(values["stt_device_index"])
        self.config.hotword_enabled = bool(values["hotword_enabled"])
        self.config.action_confirm_required = bool(values["action_confirm_required"])
        self.config.tts_rate = int(values["tts_rate"])
        self.config.max_history = int(values["max_history"])
        self.config.save()

        self.assistant.apply_settings(
            ollama_base_url=self.config.ollama_base_url,
            model=self.config.model,
            max_history=self.config.max_history,
            persona_style=self.config.persona_style,
            persona_intensity=self.config.persona_intensity,
            response_length=self.config.response_length,
            game_difficulty=self.config.game_difficulty,
            action_confirm_required=self.config.action_confirm_required,
        )
        self.speaker.set_rate(self.config.tts_rate)
        self.speaker.set_output_device(self.config.tts_output_device)
        self.stt.set_input_device(self.config.stt_device_index if self.config.stt_device_index >= 0 else None)
        if self.config.hotword_enabled:
            self._start_hotword_loop()
        else:
            self._hotword_running = False
        self.signals.status.emit("설정을 적용했어요. 바로 반영되었습니다.")
        self.run_health_check(show_popup=False)

    def run_health_check(self, show_popup: bool) -> None:
        self.signals.status.emit("시스템 점검 중...")
        self._set_busy(True)

        def run() -> None:
            checker = HealthChecker(
                base_url=self.config.ollama_base_url,
                model=self.config.model,
                stt=self.stt,
                speaker=self.speaker,
            )
            result = checker.run()
            self.signals.health_done.emit(result, show_popup)

        Thread(target=run, daemon=True).start()

    def _start_hotword_loop(self) -> None:
        if self._hotword_running:
            return
        self._hotword_running = True
        self._hotword_failed_notice = False

        def run() -> None:
            while self._hotword_running:
                try:
                    heard = self.stt.listen_once(timeout=3, phrase_time_limit=4)
                    low = heard.lower().strip()
                    if "siro야" in low or "siro" in low:
                        cleaned = (
                            heard.replace("Siro야", "")
                            .replace("siro야", "")
                            .replace("Siro", "")
                            .replace("siro", "")
                            .strip()
                        )
                        self.signals.hotword_heard.emit(cleaned)
                except Exception:
                    if not self._hotword_failed_notice:
                        self._hotword_failed_notice = True
                        self.signals.status.emit("핫워드 사용 불가(STT/마이크 확인 필요)")
                    time.sleep(1.0)

        Thread(target=run, daemon=True).start()

    def _on_assistant_done(self, answer: str) -> None:
        self._append_chat("Siro", answer)
        self.signals.status.emit("준비됨")
        self._set_busy(False)
        if self.config.tts_enabled:
            try:
                self.speaker.say(answer)
            except Exception as e:
                self._emit_error(f"TTS 출력 실패: {e}", traceback.format_exc())

    def _on_stt_done(self, text: str) -> None:
        send_on_stop = self._stt_send_on_stop
        self._stt_send_on_stop = False
        self._set_listening_ui(False)
        self._stt_stop_event = None
        if text:
            self.input_edit.setPlainText(text)
            if send_on_stop:
                self.on_send_clicked()
                return
            self.signals.status.emit("음성 인식 완료")
        else:
            self.signals.status.emit("준비됨")

    def _on_stt_partial(self, text: str) -> None:
        if not text:
            return
        self.input_edit.setPlainText(text)

    def _on_error(self, user_message: str, detail: str) -> None:
        self.signals.status.emit(f"문제가 발생했어요: {user_message}")
        self._set_busy(False)
        self._set_listening_ui(False)
        self._stt_stop_event = None
        self._log_error(user_message, detail)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Siro 오류")
        box.setText(user_message)
        box.setInformativeText("상세 내용은 data/siro_error.log 에 저장되었습니다.")
        if detail.strip():
            box.setDetailedText(detail)
        box.exec()

    def _health_status_brief(self, result: dict[str, object]) -> str:
        items = result.get("items")
        if not isinstance(items, list):
            return str(result.get("summary", "점검 결과를 확인해 주세요."))

        icon_map = {"ok": "✅", "warn": "⚠️", "error": "❌"}
        name_map = {
            "Ollama 서버": "서버",
            "모델": "모델",
            "마이크(STT)": "마이크",
            "음성출력(TTS)": "TTS",
        }
        parts: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "warn"))
            name = str(item.get("name", "항목"))
            message = str(item.get("message", "확인 필요"))

            # Keep it short for bottom status text.
            if name == "모델":
                if "준비됨" in message:
                    short_msg = "준비됨"
                elif "없음" in message:
                    short_msg = "없음"
                else:
                    short_msg = "확인 필요"
            elif name == "Ollama 서버":
                short_msg = "연결됨" if "연결됨" in message else "연결 실패"
            elif name == "마이크(STT)":
                short_msg = "사용 가능" if "사용 가능" in message else "확인 필요"
            elif name == "음성출력(TTS)":
                short_msg = "사용 가능" if "사용 가능" in message else "확인 필요"
            else:
                short_msg = message

            parts.append(f"{icon_map.get(status, '•')} {name_map.get(name, name)}: {short_msg}")

        return " | ".join(parts) if parts else str(result.get("summary", "점검 결과를 확인해 주세요."))

    def _on_health_done(self, result: object, show_popup: bool) -> None:
        self._set_busy(False)
        if not isinstance(result, dict):
            self.signals.status.emit("점검 실패")
            return

        overall = str(result.get("overall", "warn"))
        summary = str(result.get("summary", "점검 결과를 확인해 주세요."))
        brief = self._health_status_brief(result)
        self.signals.status.emit(f"시스템 점검 결과: {brief}")

        if show_popup or overall != "ok":
            title_map = {"ok": "점검 완료", "warn": "점검 경고", "error": "점검 오류"}
            icon_map = {"ok": QMessageBox.Information, "warn": QMessageBox.Warning, "error": QMessageBox.Critical}
            box = QMessageBox(self)
            box.setIcon(icon_map.get(overall, QMessageBox.Warning))
            box.setWindowTitle(title_map.get(overall, "점검 결과"))
            box.setText(summary)
            if overall != "ok":
                box.setInformativeText("Ollama가 꺼져 있으면 `ollama serve`를 먼저 실행해 주세요.")
            box.exec()

    def _on_hotword_heard(self, text: str) -> None:
        if not self.config.hotword_enabled:
            return
        prompt = text or "듣고 있어"
        self.input_edit.setPlainText(prompt)
        self.on_send_clicked()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._hotword_running = False
        super().closeEvent(event)
