import sys
import threading
import os

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QTimer
from time import sleep
from functools import partial

import waveplayerloop


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.buttons = [
            self.button0,
            self.button1,
            self.button2,
            self.button3,
            self.button4,
            self.button5,
            self.button6,
            self.button7
        ]

        self.sliders = [
            self.slider0,
            self.slider1,
            self.slider2,
            self.slider3,
            self.slider4,
            self.slider5,
            self.slider6,
            self.slider7
        ]

        self.effectLCDs = [
            self.effectLCD0,
            self.effectLCD1,
            self.effectLCD2,
            self.effectLCD3,
            self.effectLCD4,
            self.effectLCD5,
            self.effectLCD6,
            self.effectLCD7
        ]

        self.lcdButtons = [
            self.lcdButton0,
            self.lcdButton1,
            self.lcdButton2,
            self.lcdButton3,
            self.lcdButton4,
            self.lcdButton5,
            self.lcdButton6,
            self.lcdButton7
        ]

        files = os.listdir('.')
        audio_files = [file for file in files if file.endswith('.wav') and file.startswith('drum_')]
        self.loop = waveplayerloop.WavePlayerLoop(audio_files)

        timer = QTimer(self)
        timer.timeout.connect(self.updateTimePosition)
        timer.start(100)  # 0.5초마다 반복

        def switch_playback():
            if self.loop.isLooping:
                self.playButton.setText("Play")
                self.loop.stop_playback()
            else:
                self.playButton.setText("Stop")
                self.loop.start_playback()
        self.playButton.clicked.connect(switch_playback)

        for i, b in enumerate(self.buttons):
            def te(b, i):
                if not self.loop.enabled[i]:
                    b.setText(str(i+1))
                else:
                    b.setText("")
                self.loop.toggleEnable(i)
            b.clicked.connect(partial(te, b, i))

        def changePattern(i, s):
            value = s.value()
            self.loop.changePattern(i, value)

        for i, s in enumerate(self.sliders):
            cp = partial(changePattern, i, s)
            s.valueChanged.connect(cp)

        def changeEffect(i, el):
            try:
                value = (el.value() + 1) % 5
                el.display(value)
                self.loop.changeEffect(i)
            except Exception as e:
                print(e)

        for i, lb in enumerate(self.lcdButtons):
            el = self.effectLCDs[i]
            ce = partial(changeEffect, i, el)
            lb.clicked.connect(ce)

        def changeVolume():
            volume = self.volumeSlider.value / 25
            self.loop.changeVolume(volume)
        self.volumeSlider.valueChanged.connect(changeVolume)

        def setBPM():
            try:
                bpm = int(self.bpmText.text())
                self.loop.run_stretch(bpm)
            except Exception as e:
                print(f"error : {e}")
        self.bpmChangeButton.clicked.connect(setBPM)

        self.switchButton.clicked.connect(self.loop.switch_drum_break)

        self.recordButton.clicked.connect(self.loop.enable_recording)

        self.bassButton.clicked.connect(self.loop.start_playback_bass)

    def initUI(self):
        # Load the UI file
        uic.loadUi('0420.ui', self)
        # Show the window
        self.show()

    def updateTimePosition(self):
        pos = self.loop.play_position
        self.timePosLCD.display(pos + 1)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = Window()
    sys.exit(app.exec_())