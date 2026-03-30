from pydub import AudioSegment
from pydub.playback import play
from soundeffects import *
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QCheckBox

READ_CAPACITY = 1024
NUM_OF_CHUNKS = 4
class AudioPlayer(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Player")
        self.resize(300, 200)
        self.setAcceptDrops(True)

        btn = QPushButton("Play", self)
        btn.clicked.connect(self.playAudio)
        btn.move(100, 40)  # Move button to a desired position within the widget

        self.muteCheckBox = QCheckBox("Mute", self)
        self.muteCheckBox.move(100, 80)

        self.playCount = 0
        self.duration = 0

        self.segments = [AudioSegment.from_wav('./test3_1.wav'),
                    AudioSegment.from_wav('./test3_2.wav'),
                    AudioSegment.from_wav('./test3_3.wav'),
                    AudioSegment.from_wav('./test3_4.wav')]

        self.number_of_chops = 4
        self.reverse = False
        self.speedup = False
        self.position = [0, 1, 2, 3]
        self.audio = AudioSegment.silent(duration=0)  # Initialize with silence
        for i in range(len(self.position)):
            self.audio += self.segments[self.position[i]]
        self.playing = False
    def playAudio(self, position_num=0):
        # Play the new audio
        try:
            if not self.playing:
                self.audio = AudioSegment.silent(duration=0)  # Initialize with silence
                for i in range(len(self.position)):
                    self.audio += self.segments[self.position[i]]
                audio = self.audio
                faster_audio = audio._spawn(audio.raw_data, overrides={
                    "frame_rate": int(audio.frame_rate * 1.2)
                })
                if self.speedup:
                    play(faster_audio)
                elif self.reverse:
                    play(audio.reverse())
                else:
                    play(audio)

        except Exception as e:
            print(e)
            exit(-1)
    def readSignal(self, signal):
        try:
            print(signal)
            type = signal.split("/")[0]
            if type == "analogRead":
                slidersRead = signal.split("/")[1].split("\r")[0].split(", ")
                if len(slidersRead) != NUM_OF_CHUNKS:
                    return
                for i, sliderRead in enumerate(slidersRead):
                    analogRead = int(sliderRead.split(": ")[1])
                    chunk_num = analogRead // (READ_CAPACITY // NUM_OF_CHUNKS)
                    self.position[i] = chunk_num

            elif type == "digitalRead":
                digitalRead = signal.split("/")[1].split("\r")[0].split(":")
                digitalSign = digitalRead[0]
                if digitalSign == "incr":
                    chunk_num = int(digitalRead[1])-1
                    self.segments[chunk_num] = reverseAudio(self.segments[chunk_num])
                    #self.segments[chunk_num] = retriggerAudio(self.segments[chunk_num])
                    self.segments[chunk_num] = gatedAudio(self.segments[chunk_num])

        except Exception as e:
            print(e)

        print(f"position : {self.position}")
    def toggleMute(self, state):
        #self.mediaPlayer.setMuted(state)
        return

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = AudioPlayer()
    player.show()
    sys.exit(app.exec_())