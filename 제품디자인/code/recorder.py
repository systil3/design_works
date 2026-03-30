import threading
import pyaudio
import wave

class Recorder:
    def __init__(self):
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100
        self.CHUNK = 512
        self.WAVE_OUTPUT_FILENAME = "recordedFile.wav"
        self.device_index = 1
        self.audio = pyaudio.PyAudio()
        self.locked_event = threading.Event()
        self.save_recorded_audio = False

    def record(self, RECORD_SECONDS):
        try:
            print("----------------------record device list---------------------")
            info = self.audio.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            for i in range(0, numdevices):
                if (self.audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                    print("Input Device id ", i, " - ",
                          self.audio.get_device_info_by_host_api_device_index(0, i).get('name'))

            print("-------------------------------------------------------------")

            index = self.device_index  # set to microphone
            print("recording via index " + str(index))

            stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                                     rate=self.RATE, input=True, input_device_index=index,
                                     frames_per_buffer=self.CHUNK)
            print("recording started")
            recorded_bytes = b''

            for i in range(0, int(self.RATE / self.CHUNK * RECORD_SECONDS)):
                data = stream.read(self.CHUNK)
                recorded_bytes += data
            print("recording stopped")
            stream.stop_stream()
            stream.close()
            self.audio.terminate()

            if self.save_recorded_audio:
                waveFile = wave.open(self.WAVE_OUTPUT_FILENAME, 'wb')
                waveFile.setnchannels(self.CHANNELS)
                waveFile.setsampwidth(self.audio.get_sample_size(self.FORMAT))
                waveFile.setframerate(self.RATE)
                waveFile.writeframes(recorded_bytes)
                waveFile.close()

            return recorded_bytes

        except Exception as e:
            print(f"error while recording: {e}")