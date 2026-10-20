"""Download free offline models for UTOS voice-ID (no signup).
STT not needed on PC (phone does it). Speaker model only (~13MB).
Run: python download_voice_models.py
"""
import os, urllib.request, zipfile

MODELS = {
    "vosk-model-spk-0.4": "https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip",
    "vosk-model-small-en-us-0.15": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
}
HERE = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(HERE, "models")

def get(name, url):
    out = os.path.join(DST, name)
    if os.path.exists(out):
        print(name, "exists, skip")
        return
    os.makedirs(DST, exist_ok=True)
    z = os.path.join(DST, name + ".zip")
    print("downloading", name, "...")
    urllib.request.urlretrieve(url, z)
    with zipfile.ZipFile(z) as f:
        f.extractall(DST)
    os.remove(z)
    print("ok", out)

if __name__ == "__main__":
    for n, u in MODELS.items():
        get(n, u)
    print("pip install vosk numpy")
