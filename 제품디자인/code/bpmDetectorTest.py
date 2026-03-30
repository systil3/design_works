import pyaudiowpatch as pyaudio
import numpy as np
import librosa
import sounddevice as sd

print(sd.query_devices())
RECORD_SECONDS = 5

with pyaudio.PyAudio() as p:
    # Get the default loopback device info
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback

    else:
        print("Default loopback output device not found 😭")
        exit()

    # Set the input device index for stereo mix recording
    # You may need to adjust this based on your system's available input devices
    input_device_index = p.get_default_input_device_info()["index"]

    sample_rate = int(default_speakers['defaultSampleRate'])
    chunk = sample_rate * RECORD_SECONDS

    # Open the stream with 2 channels for stereo recording
    stream = p.open(format=pyaudio.paFloat32,
                    channels=2,
                    rate=sample_rate,
                    input=True,
                    input_device_index=input_device_index,
                    frames_per_buffer=chunk)

    print(f"Recording {RECORD_SECONDS} seconds from {default_speakers['index']}: {default_speakers['name']} 🎤")
    sound = stream.read(chunk)
    print("Recording complete 🎹")

    stream.stop_stream()
    stream = p.open(format=pyaudio.paFloat32,
                    channels=2,
                    rate=sample_rate,
                    output=True,
                    frames_per_buffer=chunk)
    #print("Recording Result : ")
    #stream.write(sound)

    np_sound = np.frombuffer(sound, dtype=np.float32)
    tempo, beat_frames = librosa.beat.beat_track(y=np_sound, sr=sample_rate)
    if tempo < 100:
        print(f'Estimated tempo: {round(tempo)} or {round(tempo * 2)} bpm')
    else:
        print(f'Estimated tempo: {round(tempo)} bpm')

    stream.close()