"""Audio preview player: QMediaPlayer + QAudioOutput (Qt6 API)."""

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtWidgets import (
    QWidget, QPushButton, QSlider, QLabel, QHBoxLayout, QMessageBox,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


def _fmt_ms(ms):
    if ms is None or ms < 0:
        ms = 0
    s = int(ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


class PlayerWidget(QWidget):
    """Play/Pause/Stop + position slider + time label for one audio file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = None

        self._player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._audio_out.setVolume(0.8)
        self._player.setAudioOutput(self._audio_out)

        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._toggle_play)
        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setEnabled(False)
        self._slider.sliderMoved.connect(self._on_slider_moved)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setObjectName("dimLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._stop_btn)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._time_label)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(self._on_error)

    # -- public ------------------------------------------------------

    def load(self, path):
        """Load a file for preview (does not autoplay)."""
        self.stop()
        self._path = str(path)
        self._player.setSource(QUrl.fromLocalFile(self._path))
        self._play_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)
        self._slider.setEnabled(True)

    def stop(self):
        self._player.stop()
        self._player.setPosition(0)

    def play(self):
        """Start playback of the loaded file (if any)."""
        if self._path:
            self._player.play()

    def clear(self):
        self.stop()
        self._path = None
        self._player.setSource(QUrl())
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._slider.setEnabled(False)
        self._slider.setRange(0, 0)
        self._slider.setValue(0)
        self._time_label.setText("0:00 / 0:00")

    # -- slots -------------------------------------------------------

    @Slot()
    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    @Slot()
    def _stop(self):
        self.stop()

    @Slot(int)
    def _on_slider_moved(self, value):
        self._player.setPosition(value)

    @Slot(int)
    def _on_position_changed(self, pos):
        if not self._slider.isSliderDown():
            self._slider.setValue(pos)
        self._time_label.setText(
            f"{_fmt_ms(pos)} / {_fmt_ms(self._player.duration())}")

    @Slot(int)
    def _on_duration_changed(self, duration):
        self._slider.setRange(0, max(duration, 0))
        self._time_label.setText(
            f"{_fmt_ms(self._player.position())} / {_fmt_ms(duration)}")

    @Slot(QMediaPlayer.PlaybackState)
    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸ Pause")
        else:
            self._play_btn.setText("▶ Play")

    @Slot(QMediaPlayer.Error, str)
    def _on_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return
        QMessageBox.warning(
            self, "Playback error",
            f"Couldn't play this file:\n{error_string or error}")
