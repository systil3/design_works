import sys
import audioplayer
from PyQt5.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = audioplayer.AudioPlayer()
    player.show()
    sys.exit(app.exec_())