"""Built-in audio preview player (QMediaPlayer + seek slider)."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)


def _fmt_ms(ms):
    if ms is None or ms < 0:
        ms = 0
    total_s = int(ms // 1000)
    return "%d:%02d" % (total_s // 60, total_s % 60)


class PreviewPlayer(QWidget):
    """Small play/pause + seek bar + time readout widget."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.play_btn = QPushButton("\u25b6")  # ▶
        self.play_btn.setFixedWidth(40)
        self.play_btn.setToolTip("Play / pause")
        self.play_btn.clicked.connect(self.toggle)
        layout.addWidget(self.play_btn)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        layout.addWidget(self.slider, 1)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("muted")
        layout.addWidget(self.time_label)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    # -- public API ---------------------------------------------------
    def load(self, path):
        """Load an audio file (does not start playback)."""
        self._player.setSource(QUrl.fromLocalFile(path))
        self.slider.setValue(0)
        self.time_label.setText("0:00 / 0:00")

    def play(self):
        self._player.play()

    def pause(self):
        self._player.pause()

    def toggle(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def stop(self):
        self._player.stop()
        self.slider.setValue(0)

    # -- slots --------------------------------------------------------
    def _on_slider_moved(self, position):
        self._player.setPosition(position)

    def _on_position_changed(self, position):
        self.slider.blockSignals(True)
        try:
            self.slider.setValue(position)
        finally:
            self.slider.blockSignals(False)
        self._update_time_label(position, self._player.duration())

    def _on_duration_changed(self, duration):
        self.slider.setRange(0, max(0, duration))
        self._update_time_label(self._player.position(), duration)

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("\u275a\u275a")  # ❚❚
        else:
            self.play_btn.setText("\u25b6")  # ▶

    def _update_time_label(self, position, duration):
        self.time_label.setText(
            "%s / %s" % (_fmt_ms(position), _fmt_ms(duration)))
