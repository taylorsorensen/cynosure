# Elysia: Local AI Control Panel

## Setup
1. Download Vosk model (e.g., small-en-us) to ./vosk-model
2. Install deps: `pip install -r backend/requirements.txt`
3. Pull model: `ollama pull elysia:latest`
4. Run Ollama server.
5. Start backend: `python backend/main.py`
6. Start frontend: `cd frontend && npm start`
7. Monitor: `bash utils/watchdog.sh`

## Features
- Expressive TTS with prosody annotations.
- Local STT via Vosk.
- Hierarchical memory for fluid convos.
- Buffered TTS streaming to frontend for playback/viz.
- UI: Animated avatar + real-time waveform (mic/TTS).

For RPi5: Use small Vosk model; test buffering if stutters.
