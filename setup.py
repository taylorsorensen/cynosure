import os
import zipfile
from urllib.request import urlretrieve

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_DIR = os.path.join(os.path.dirname(__file__), "vosk-model")

def download_and_unzip():
    zip_path = "vosk-model.zip"
    if not os.path.exists(MODEL_DIR):
        print("Downloading Vosk model...")
        urlretrieve(MODEL_URL, zip_path)
        print("Unzipping...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(MODEL_DIR)
        os.remove(zip_path)
        print(f"Model ready at {MODEL_DIR}")
    else:
        print("Vosk model already exists.")

if __name__ == "__main__":
    download_and_unzip()
