from kokoro import KPipeline
import numpy as np
import torch
import json
import os

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

pipeline = KPipeline(lang_code='a')

def preload_tts():
    print("Pre-loading TTS model...")
    try:
        _ = list(pipeline(" ", voice=config['tts_voice']))
        print("TTS model loaded successfully.")
    except Exception as e:
        print(f"Could not pre-load TTS model: {e}")

def generate_audio_chunks(text):
    generator = pipeline(text, voice=config['tts_voice'])
    for _, _, audio in generator:
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        chunk = audio.astype(np.float32)
        yield chunk
