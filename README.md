# AudioSep Desktop Client

A standalone Windows desktop application (`.exe`) that lets you:
1. Upload an **MP4 video**
2. Enter a **natural language description** of the sound you want to extract (e.g., `"dog barking"`, `"keyboard typing"`, `"speech"`)
3. Receive an isolated **WAV audio file** powered by the [AudioSep](https://github.com/Audio-AGI/AudioSep) model

The desktop client handles **video-to-audio extraction (FFmpeg)** locally and offloads the heavy AI inference to a GPU machine on your **local network (LAN)**.

---

## Architecture

```
[Local PC - no GPU required]          [LAN GPU Machine]
┌──────────────────────────┐          ┌──────────────────────┐
│  AudioSepClient.exe       │ ──WAV──► │  lan_server.py       │
│  (PySide6 Desktop App)    │ ◄─WAV── │  (FastAPI + AudioSep) │
│  + FFmpeg (local)         │          └──────────────────────┘
└──────────────────────────┘
```

---

## Project Structure

```
audiosep_client/
├── desktop_app/
│   ├── main.py                 # Entry point
│   ├── build.py                # PyInstaller packaging script
│   ├── requirements.txt
│   ├── core/
│   │   └── audio_processor.py  # FFmpeg + HTTP logic
│   └── gui/
│       └── main_window.py      # PySide6 GUI
└── lan_server/
    └── lan_server.py           # GPU-side FastAPI server (run on the GPU machine)
```

---

## Quick Start (Development)

### 1. Local Desktop App

```bash
cd desktop_app
python -m venv venv
venv\Scripts\activate           # Windows
pip install -r requirements.txt
python main.py
```

> ⚠️ **FFmpeg** must be installed and available in your system PATH.

### 2. GPU Server (on the LAN machine)

```bash
cd lan_server
pip install fastapi uvicorn httpx
# Clone AudioSep and download checkpoint weights first
# Then uncomment the model loading lines inside lan_server.py
uvicorn lan_server:app --host 0.0.0.0 --port 8001
```

### 3. Packaging to .exe

```bash
cd desktop_app
python build.py
# Output: desktop_app/dist/AudioSepClient/AudioSepClient.exe
```

---

## Configuration

In the app, go to **Settings → Set LAN Server IP / URL** to enter the full URL of your GPU machine, e.g.:

```
http://192.168.1.100:8001/separate
```

This setting is **persisted** between restarts using `QSettings`.

---

## Dependencies

### Desktop App (`desktop_app/requirements.txt`)
- `PySide6` — GUI framework (Qt for Python)
- `httpx` — Async HTTP client
- `pyinstaller` — Packaging to `.exe`

### LAN Server
- `fastapi` + `uvicorn` — Web server
- `PyTorch` + AudioSep model — AI inference (requires CUDA GPU)

---

## Credits
- **AudioSep** model: [Audio-AGI/AudioSep](https://github.com/Audio-AGI/AudioSep) — *"Separate Anything You Describe"*
