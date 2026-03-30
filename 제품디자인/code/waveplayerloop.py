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

        self.enabled = [True] * 8
        self.patterns = [i for i in range(8)]

        self.effects = [EFFECT_NORM for i in range(8)]
        self.effect_buffer = [[] for i in range(8)]

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
        self.play_recorded_audio = True

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

        # init chunks
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
        self.empty_chunk = [0] * len(self.chunks[0])

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

        for i, chunk_num in enumerate(self.patterns):
            self.writeEffectBuffer(self.effects[i], i, chunk_num)

    def toggleEnable(self, chunk_num):
        assert 0 <= chunk_num < 8
        self.enabled[chunk_num] = not self.enabled[chunk_num]

    def writeEffectBuffer(self, effect, time_pos, chunk_num):
        if effect != EFFECT_NORM:
            if effect == EFFECT_REVERSE:
                self.effect_buffer[time_pos] = reverseAudio(self.chunks[chunk_num], self.audio_type)
            if effect == EFFECT_RETRIGGER:
                self.effect_buffer[time_pos] = retriggerAudio(self.chunks[chunk_num], self.audio_type)
            if effect == EFFECT_GATED:
                self.effect_buffer[time_pos] = gatedAudio(self.chunks[chunk_num], self.audio_type)
            if effect == EFFECT_DOWNSAMPLE:
                self.effect_buffer[time_pos] = downsampleAudio(self.chunks[chunk_num], self.audio_type)

    def changePattern(self, time_pos, chunk_num):
        print(time_pos)
        assert 0 <= chunk_num < 8
        self.patterns[time_pos] = chunk_num
        effect = self.effects[time_pos]
        self.writeEffectBuffer(effect, time_pos, chunk_num)

    def changeEffect(self, time_pos):
        self.effects[time_pos] = (self.effects[time_pos] + 1) % NUM_OF_EFFECTS
        effect = self.effects[time_pos]
        chunk_num = self.patterns[time_pos]
        self.writeEffectBuffer(effect, time_pos, chunk_num)

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

        for time_pos in range(8):
            chunk_num = self.patterns[time_pos]
            effect = self.effects[time_pos]
            self.writeEffectBuffer(effect, time_pos, chunk_num)

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

    def setDataBytes(self):
        data = []
        for i in range(8):
            if not self.enabled[i]:
                data += self.empty_chunk
            elif self.effects[i] == EFFECT_NORM:
                data += self.chunks[self.patterns[i]]
            else:
                data += self.effect_buffer[i]
        data_bytes = bytes(data)
        return data_bytes

    def mix_audio(self, background_audio, recorded_audio):
        background_samples = np.frombuffer(background_audio, dtype=self.audio_type)
        recorded_samples = np.frombuffer(recorded_audio, dtype=self.audio_type)

        # Ensure both arrays are the same length
        #assert len(background_samples) == len(recorded_samples)
        min_len = min(len(background_samples), len(recorded_samples))
        background_samples = background_samples[:min_len]
        recorded_samples = recorded_samples[:min_len]

        # Mix the audio samples
        mixed_samples = background_samples + recorded_samples*4
        mixed_samples = np.clip(mixed_samples, -32768, 32767).astype(self.audio_type)
        return mixed_samples.tobytes()

    def run(self):
        try:
            self.player = pyaudio.PyAudio()
            # Open Output Stream (based on PyAudio tutorial)

            # PLAYBACK LOOP
            time_interval = 8
            while not self.stop_event.is_set():
                data_bytes = self.setDataBytes()
                n = len(data_bytes)

                pos = 0
                if self.record_enabled:
                    if not hasattr(self, 'recording_thread') or not self.recording_thread.is_alive():
                        self.start_recording()

                while pos < n and not self.stop_event.is_set():
                    #print(type(data_bytes), pos, type(self.record_buffer), len(self.record_buffer) if self.record_buffer else 0)
                    self.play_position = pos * 8 // n
                    interval = data_bytes[pos:pos + time_interval]

                    audio_samples = np.frombuffer(interval, dtype=np.int16)  # Assuming 16-bit audio
                    audio_samples = self.filter(audio_samples)
                    mul = ((audio_samples.astype(np.float32) * self.multiplier)
                           .clip(-32768, 32767).astype(np.int16))
                    # Clip to prevent overflow

                    if self.play_recorded_audio and self.record_buffer:
                        mixed_audio = self.mix_audio(mul.tobytes(), self.record_buffer[pos:pos + time_interval])
                        self.stream.write(mixed_audio)
                    else:
                        self.stream.write(mul.tobytes())

                    pos += time_interval

                if self.wf.readframes(self.CHUNK) == b'':  # If file is over then rewind.
                    self.wf.rewind()

            #self.stream.close()
            self.player.terminate()

        except Exception as e:
            print(f"error while running : {e}")

    def start_playback(self):
        """
        Start playback(with multithread).
        """
        thread = threading.Thread(target=self.run)
        self.stop_event.clear()  # to be fixed later. todo
        self.isLooping = True
        thread.start()

    def stop_playback(self):
        """
        Stop playback.
        """
        self.stop_event.set()
        self.isLooping = False
    def enable_recording(self):
        self.record_enabled = True

    def disable_recording(self):
        self.record_enabled = False

    def start_recording(self):
        def recording_task():
            if self.record_enabled:
                self.disable_recording()
                audio_data = self.recorder.record(self.duration_sec)
                self.record_buffer = audio_data
                print(self.record_buffer)
                #self.record_playback = self.record_buffer.copy()
                self.record_bpm = self.current_bpm

        self.recording_thread = threading.Thread(target=recording_task)
        self.recording_thread.start()

    def switch_drum_break(self):
        self.break_num = (self.break_num + 1) % len(self.breaks)
        self.restoreFile(self.breaks[self.break_num])

#--------------------------------------- about bass (not loop) -----------------------------------------

    def playBass(self):
        time_interval = 8
        m = len(self.bass_buffer)
        pos = 0

        while pos < m and self.bass_playing.is_set():
            self.bstream.write(self.bass_buffer[pos:pos+time_interval])
            pos += time_interval

    def start_playback_bass(self):
        """
        Start playback (with multithread).
        """
        if self.bthread and self.bthread.is_alive():
            # Fade out before stopping
            self.bass_buffer = fade_out(self.bass_buffer , dtype=self.audio_type, sample_rate=self.frame_rate)
            self.bass_playing.clear()
            self.bthread.join()

        # Fade in before starting
        self.bass_buffer = fade_in(self.bass_buffer, dtype=self.audio_type, sample_rate=self.frame_rate)
        self.bass_playing.set()
        self.bthread = threading.Thread(target=self.playBass)
        self.bthread.start()

    def stop_playback_bass(self):
        """
        Stop playback.
        """
        if self.bthread and self.bthread.is_alive():
            self.bass_playing.clear()
            self.bthread.join()