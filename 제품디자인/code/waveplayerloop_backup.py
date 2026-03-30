import os
import queue
import wave
import threading

import numpy as np
import pyaudio
from soundeffects import *
from recorder import *
from bytes import *
from math import sqrt
import traceback

EFFECT_NORM = 0
EFFECT_REVERSE = 1
EFFECT_RETRIGGER = 2
EFFECT_GATED = 3
EFFECT_DOWNSAMPLE = 4
NUM_OF_EFFECTS = 5

default_block_sizes = {
    np.float32: 8,
    np.int32: 8,
    np.float16: 4,
    np.int16: 4,
    np.int8: 2
}


class WavePlayerLoop(threading.Thread):
    CHUNK = 1024
    SAMPLE_RATE = 48000

    def __init__(self, breaks):
        super(WavePlayerLoop, self).__init__()

        self.multiplier = np.float16(1)
        self.stop_event = threading.Event()
        self.isLooping = False
        self.filter_knob = 50
        self.time_interval_size = 4096

        self.enabled = [True] * 8
        self.patterns = [i for i in range(8)]

        self.effects = [EFFECT_NORM for i in range(8)]
        self.reverse_buffer = []
        self.retrigger_buffer = []
        self.gate_buffer = []

        self.breaks = breaks
        self.break_num = 0

        self.bass_file = "bass.wav"
        self.bass_buffer = None
        self.bthread = None
        self.bass_playing = threading.Event()

        initpath = self.breaks[self.break_num]
        self.initFile(initpath)
        self.initStream()

        self.recorder = Recorder()
        self.recorder.RATE = self.frame_rate * 2
        self.record_buffer = None
        self.record_bpm = -1
        self.record_playback = None
        self.record_enabled = False
        self.recording_thread = None
        self.play_recorded_audio = True

        self.reverse_button = False
        self.retrigger_button = False
        self.gate_button = False
        self.downsample_button = False

    def initFile(self, filepath):
        self.filepath = os.path.abspath(filepath)

        self.player = pyaudio.PyAudio()
        self.wf = wave.open(self.filepath, 'rb')
        sample_width = self.wf.getsampwidth()
        if sample_width == 1:
            self.audio_type = np.int8
        elif sample_width == 2:
            self.audio_type = np.int16
        elif sample_width == 3:
            self.audio_type = np.int16
        elif sample_width == 4:
            self.audio_type = np.int32
        else:
            raise ValueError("Unsupported sample width")
        print(f"audio datatype : {self.audio_type}")

        self.total_frames = self.wf.getnframes()
        self.frame_rate = self.wf.getframerate()
        self.duration_sec = self.total_frames / float(self.frame_rate)
        self.play_position = 0

        # init chunksd
        self.chunk_length = self.total_frames // 8
        self.chunks = []

        # default audio file stream (for stretching)
        self.default_buffer = self.wf.readframes(self.total_frames)
        self.original_bpm = detectBPM(self.default_buffer, self.audio_type)
        self.current_bpm = self.original_bpm

        # init chunks (default number of chunks : 8)
        block_size = default_block_sizes[self.audio_type]
        for i in range(8):
            if sample_width == 5:  # should be fixed, todo
                chunk_data_24 = self.default_buffer[
                                self.chunk_length * block_size * i:self.chunk_length * block_size * (i + 1)]
                chunk_data = convert_24bit_to_32bit(chunk_data_24)
            else:
                chunk_data = self.default_buffer[
                             self.chunk_length * block_size * i:self.chunk_length * block_size * (i + 1)]
            self.chunks.append(chunk_data)
            self.reverse_buffer.append(reverseAudio(self.chunks[i], self.audio_type))
            self.retrigger_buffer.append(retriggerAudio(self.chunks[i], self.audio_type))
            self.gate_buffer.append(gatedAudio(self.chunks[i], self.audio_type))

        self.empty_chunk = [0] * len(self.chunks[0])

        self.record_buffer = None

        # init bass
        self.bwf = wave.open(self.bass_file, 'rb')
        self.bass_buffer = self.bwf.readframes(self.bwf.getnframes())

    def initStream(self):
        self.stream = self.player.open(format=self.player.get_format_from_width(self.wf.getsampwidth()),
                                       channels=self.wf.getnchannels(),
                                       rate=self.wf.getframerate(),
                                       output=True)

        self.bstream = self.player.open(format=self.player.get_format_from_width(self.wf.getsampwidth()),
                                        channels=self.wf.getnchannels(),
                                        rate=self.wf.getframerate(),
                                        output=True)

    def restoreFile(self, filepath):
        self.stop_playback()
        self.initFile(filepath)

    def toggleEnable(self, chunk_num):
        assert 0 <= chunk_num < 8
        self.enabled[chunk_num] = not self.enabled[chunk_num]

    def changePattern(self, time_pos, chunk_num):
        assert 0 <= chunk_num < 8
        self.patterns[time_pos] = chunk_num
        effect = self.effects[time_pos]

    def changeVolume(self, volume):
        """
        modify volume in logarithmic scale
        """
        self.multiplier = pow(2, (sqrt(sqrt(sqrt(volume))) * 192 - 192) / 6)

    def stretch(self, bpm):
        stretched = stretchFromBPM(self.default_buffer, self.audio_type, self.original_bpm, bpm)
        block_size = default_block_sizes[self.audio_type]
        st_chunk_length = len(stretched) // (8 * block_size)
        self.chunks = []
        for i in range(8):
            if self.wf.getsampwidth() == 5:  # should be fixed, todo
                chunk_data_24 = stretched[st_chunk_length * block_size * i:st_chunk_length * block_size * (i + 1)]
                chunk_data = convert_24bit_to_32bit(chunk_data_24)
            else:
                chunk_data = stretched[
                             st_chunk_length * block_size * i:st_chunk_length * block_size * (i + 1)]
            self.chunks.append(chunk_data)

        self.record_playback = stretchFromBPM(self.default_buffer, self.audio_type, self.record_bpm, bpm)

    def run_stretch(self, bpm):
        """
        stretching in multithread
        """
        self.current_bpm = bpm
        t = threading.Thread(target=lambda: self.stretch(bpm))
        t.start()

    def filter(self, audio):
        if self.filter_knob < 45:
            filter_freq = (15000 / 45) * self.filter_knob
            print(filter_freq)
            ret = allpass_based_filter(audio, filter_freq, 48000, False)
        elif self.filter_knob > 55:
            ret = audio
        else:
            ret = audio
        return ret

    def setDataBytes(self, i):
        if not self.enabled[i]:
            data = self.empty_chunk
        else:
            chunk_num = self.patterns[i]
            if self.reverse_button:
                data = reverseAudio(self.chunks[chunk_num], self.audio_type)
            elif self.retrigger_button:
                data = retriggerAudio(self.chunks[chunk_num], self.audio_type)
            elif self.gate_button:
                data = gatedAudio(self.chunks[chunk_num], self.audio_type)
            elif self.downsample_button:
                data = downsampleAudio(self.chunks[chunk_num], self.audio_type)
            else:
                data = self.chunks[self.patterns[chunk_num]]
        data_bytes = bytes(data)
        return data_bytes

    def mix_audio(self, background_audio, recorded_audio, mix_ratio=1):
        # Convert byte data to numpy arrays
        background_samples = np.frombuffer(background_audio, dtype=self.audio_type)
        recorded_samples = np.frombuffer(recorded_audio, dtype=self.audio_type)

        min_len = min(len(background_samples), len(recorded_samples))
        background_samples = background_samples[:min_len]
        recorded_samples = recorded_samples[:min_len]

        mixed_samples = background_samples + recorded_samples * mix_ratio

        # mixed_samples = np.clip(mixed_samples, -32768, 32767).astype(self.audio_type)

        return mixed_samples.tobytes()

    def run(self):
        try:
            self.player = pyaudio.PyAudio()
            # Open Output Stream (based on PyAudio tutorial)

            # PLAYBACK LOOP
            time_interval = 8
            while not self.stop_event.is_set():

                if self.record_enabled:
                    if self.recording_thread == None or not self.recording_thread.is_alive():
                        self.start_recording()

                for i in range(8):
                    self.play_position = i
                    data_bytes = self.setDataBytes(i)
                    n = len(data_bytes)
                    pos = 0

                    while pos < n and not self.stop_event.is_set():
                        interval = data_bytes[pos:pos + time_interval]

                        audio_samples = np.frombuffer(interval, dtype=np.int16)  # Assuming 16-bit audio
                        audio_samples = self.filter(audio_samples)
                        mul = ((audio_samples.astype(np.float32) * self.multiplier)
                               .clip(-32768, 32767).astype(np.int16))
                        # Clip to prevent overflow

                        if self.play_recorded_audio and self.record_buffer:
                            rb_pos = n * i + pos
                            mixed_audio = self.mix_audio(mul.tobytes(),
                                                         self.record_buffer[rb_pos:rb_pos + time_interval])
                            self.stream.write(mixed_audio)
                        else:
                            self.stream.write(mul.tobytes())

                        pos += time_interval

                if self.wf.readframes(self.CHUNK) == b'':  # If file is over then rewind.
                    self.wf.rewind()

            # self.stream.close()
            self.player.terminate()

        except Exception as e:
            print(f"error while running : {traceback.format_exc()}")

    def start_playback(self):
        """
        Start playback(with multithread).
        """
        print("play")
        thread = threading.Thread(target=self.run)
        self.stop_event.clear()  # to be fixed later. todo
        self.isLooping = True
        thread.start()

    def stop_playback(self):
        """
        Stop playback.
        """
        print("stop")
        self.stop_event.set()
        self.isLooping = False

    def switch_playback(self, button):
        if not self.isLooping:
            self.start_playback()
        else:
            self.stop_playback()

    def enable_recording(self):
        self.record_enabled = True

    def disable_recording(self):
        self.record_enabled = False

    def start_recording(self):
        def recording_task():
            self.record_buffer = self.recorder.record(self.duration_sec)
            self.record_bpm = self.current_bpm

        if self.record_enabled:
            self.recording_thread = threading.Thread(target=recording_task)
            self.recording_thread.start()
            self.disable_recording()

    def switch_drum_break(self, counter):
        self.break_num = counter % len(self.breaks)
        self.restoreFile(self.breaks[self.break_num])
