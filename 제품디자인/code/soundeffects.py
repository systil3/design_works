from pydub import AudioSegment
import numpy as np
import librosa
import pyrubberband as pyrb
import fractions

from scipy import signal
from scipy.signal import butter, lfilter

DEFAULT_SAMPLE_RATE = 48000
PRINT_STATE = True

def byte_string_to_binary_array(byte_string):
    binary_array = []
    for byte in byte_string:
        binary_representation = bin(byte)[2:].zfill(8)  # Removing '0b' prefix and zero-padding to 8 bits
        # Convert each binary digit to 0 or 1 and add to the array
        for bit in binary_representation:
            binary_array.append(int(bit))
    return binary_array

def binary_array_to_byte_object(binary_array):
    byte_string = b""
    for i in range(0, len(binary_array), 8):
        byte_bits = binary_array[i:i+8]
        byte_value = int("".join(map(str, byte_bits)), 2)
        byte_string += bytes([byte_value])
    return byte_string

def reverseAudio(audio, np_type):
    audio_arr = np.frombuffer(audio, dtype=np_type)
    reversed_audio = audio_arr[::-1]
    return reversed_audio.tobytes()

def retriggerAudio(audio, np_type, fraction = 4, samplerate = 48000):
    length = len(audio)

    start_time = 0  # Start from the beginning
    end_time = length // fraction # End at the duration of 1/16 beat chunk
    chunk = audio[start_time:end_time]

    repeated_chunk = chunk * fraction
    return repeated_chunk

def gatedAudio(audio, np_type, fraction=4, samplerate = 48000):
    length = len(audio)
    chunk_size = length // fraction
    ret = []

    for i in range(fraction):
        if i % 2 == 0:
            ret.extend(audio[chunk_size*i:chunk_size*(i+1)])
        else:
            ret.extend(np.zeros(chunk_size, dtype=np_type))
    return ret


def downsampleAudio(audio, np_type, fraction=8):

    def sin_wave(freq, duration, sample_rate):
        t = np.linspace(0, duration, int(duration * sample_rate), endpoint=False)
        sinw = np.sin(2 * np.pi * freq * t)
        return sinw

    audio_arr = np.frombuffer(audio, dtype=np_type).copy()  # Create a copy of the array
    downsampled_audio = audio_arr
    length = len(downsampled_audio)
    for i in range(length):
        if i % fraction != 0:
            downsampled_audio[i] = downsampled_audio[i - i % fraction]

    ret = downsampled_audio.tobytes()
    return ret

#-------------------------------------- filter section ----------------------------------------------

def a1_coefficient(break_frequency, sampling_rate):
    tan = np.tan(np.pi * break_frequency / sampling_rate)
    return (tan - 1) / (tan + 1)

def allpass_filter(input_signal, break_frequency, sampling_rate):
    allpass_output = np.zeros(input_signal.shape)
    dn_1 = 0
    a1 = a1_coefficient(break_frequency, sampling_rate)

    for n in range(input_signal.shape[0]):
        allpass_output[n] = a1 * input_signal[n] + dn_1
        dn_1 = input_signal[n] - a1 * allpass_output[n]

    return allpass_output

def allpass_based_filter(audio, cutoff_frequency, sampling_rate, highpass=False, amplitude=1.0):
    input_signal = np.frombuffer(audio, dtype=np.int16)
    allpass_output = allpass_filter(input_signal, cutoff_frequency, sampling_rate)
    assert allpass_output.shape == input_signal.shape

    if highpass:
        allpass_output *= -1

    filter_output = input_signal + allpass_output
    filter_output *= 0.5
    filter_output *= amplitude

    return filter_output
def butter_lowpass(cutoff, fs, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a

def butter_lowpass_filter(data, cutoff, fs, order=5):
    b, a = butter_lowpass(cutoff, fs, order=order)
    filtered_data = lfilter(b, a, data)
    return filtered_data

def butter_highpass(cutoff, fs, order=3):
    nyq = 0.5 * fs
    if cutoff >= nyq:
        raise ValueError("Cutoff frequency must be less than the Nyquist frequency.")
    normal_cutoff = cutoff / nyq
    b, a = signal.butter(order, normal_cutoff, btype='high', analog=False)
    return b, a

def butter_highpass_filter(data, cutoff, fs, order=3):
    b, a = butter_highpass(cutoff, fs, order=order)
    y = signal.filtfilt(b, a, data)
    return y

#-------------------------------------- stretching section ----------------------------------------------

def detectBPM(audio, np_type):
    np_sound = np.frombuffer(audio, dtype=np_type).astype(
        np.float16 if np_type in (np.int16, np.float16)
        else np.float32
    )  # Change the dtype to float
    tempo, beat_frames = librosa.beat.beat_track(y=np_sound, sr=DEFAULT_SAMPLE_RATE)
    if tempo < 100:
        if PRINT_STATE:
            print(f'Estimated tempo: {round(tempo)} or {round(tempo * 2)} bpm')
            tempo *= 2 #to be fixed. todo
    else:
        if PRINT_STATE:
            print(f'Estimated tempo: {round(tempo)} bpm')
    return tempo

def stretchFromBPM(audio, np_type, original_bpm, modified_bpm, nfft = 2048):
    """
    open-source algorithm in https://github.com/gaganbahga/time_stretch
    """

    try:
        np_sound = np.frombuffer(audio, dtype=np_type).astype(
            np.float16 if np_type in (np.int16, np.float16)
            else np.float32
        )
        factor = modified_bpm / original_bpm
        print(factor)
        '''
        stretch an audio sequence by a factor using FFT of size nfft converting to frequency domain
        :param x: np.ndarray, audio array in PCM float32 format
        :param factor: float, stretching or shrinking factor, depending on if its > or < 1 respectively
        :return: np.ndarray, time stretched audio
        '''
        stft = librosa.core.stft(np_sound, n_fft=nfft).transpose()  # i prefer time-major fashion, so transpose
        stft_cols = stft.shape[1]

        times = np.arange(0, stft.shape[0], factor)  # times at which new FFT to be calculated
        hop = nfft/4                                 # frame shift
        stft_new = np.zeros((len(times), stft_cols), dtype=np.complex_)
        phase_adv = (2 * np.pi * hop * np.arange(0, stft_cols))/ nfft
        phase = np.angle(stft[0])

        stft = np.concatenate( (stft, np.zeros((1, stft_cols))), axis=0)

        for i, time in enumerate(times):
            left_frame = int(np.floor(time))
            local_frames = stft[[left_frame, left_frame + 1], :]
            right_wt = time - np.floor(time)                        # weight on right frame out of 2
            local_mag = (1 - right_wt) * np.absolute(local_frames[0, :]) + right_wt * np.absolute(local_frames[1, :])
            local_dphi = np.angle(local_frames[1, :]) - np.angle(local_frames[0, :]) - phase_adv
            local_dphi = local_dphi - 2 * np.pi * np.floor(local_dphi/(2 * np.pi))
            stft_new[i, :] =  local_mag * np.exp(phase*1j)
            phase += local_dphi + phase_adv

        stretched_audio = librosa.core.istft(stft_new.transpose()).astype(np_type).tobytes()
        print(type(audio), len(audio), type(stretched_audio), len(stretched_audio))
        return stretched_audio

    except Exception as e:
        print(f"error:{e}")

#-------------------------------------- fade in / out section -------------------------------------#
def fade_in(buffer, sample_rate, dtype, fade_duration=0.1):
    fade_samples = int(sample_rate * fade_duration)
    fade = np.linspace(0, 1, fade_samples, dtype=np.float32)

    # Convert byte buffer to numpy array
    audio_data = np.frombuffer(buffer, dtype=dtype).copy()

    # Apply fade-in
    audio_data[:fade_samples] = (audio_data[:fade_samples].astype(np.float32) * fade).astype(dtype)

    # Convert numpy array back to byte buffer
    return audio_data.tobytes()

def fade_out(buffer, sample_rate, dtype, fade_duration=0.1):
    try:
        fade_samples = int(sample_rate * fade_duration)
        fade = np.linspace(1, 0, fade_samples, dtype=np.float32)

        # Convert byte buffer to numpy array and make it writable
        audio_data = np.frombuffer(buffer, dtype=dtype).copy()

        # Apply fade-out
        audio_data[-fade_samples:] = (audio_data[-fade_samples:].astype(np.float32) * fade).astype(dtype)

        # Convert numpy array back to byte buffer
        return audio_data.tobytes()
    except Exception as e:
        print(e)