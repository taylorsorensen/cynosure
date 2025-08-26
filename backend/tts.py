# layer5one/elysia/Elysia-b9bc56dcb4aef6efd1e5df74a126d6c7729dc06b/backend/tts.py
from kokoro import KPipeline
import numpy as np
import torch
import json
import os

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

# Initialize the pipeline globally
pipeline = KPipeline(lang_code='a')

def preload_tts():
    """Warms up the TTS model by generating a short, silent audio clip."""
    print("Pre-loading TTS model...")
    try:
        # Generate a silent sample to load the model into memory
        _ = list(pipeline(" ", voice=config['tts_voice']))
        print("TTS model loaded successfully.")
    except Exception as e:
        print(f"Could not pre-load TTS model: {e}")


def generate_audio_chunks(text):
    """Generates audio chunks from text using the pre-loaded pipeline."""
    generator = pipeline(text, voice=config['tts_voice'])
    for _, _, audio in generator:
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        chunk = audio.astype(np.float32)
        yield chunk
