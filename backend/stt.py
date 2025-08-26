from vosk import Model, KaldiRecognizer
import pyaudio
import json
import os

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

model = Model(config['stt_model_path'])
rec = KaldiRecognizer(model, 16000)

def listen():
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)
    stream.start_stream()
    print("Listening...")
    while True:
        data = stream.read(4000)
        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get('text', '')
            if text:
                print(f"User: {text}")
                stream.stop_stream()
                stream.close()
                p.terminate()
                return text
