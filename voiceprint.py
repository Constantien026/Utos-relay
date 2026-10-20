"""UTOS voiceprint: text-independent speaker check, offline, no signup.
Enroll once with 3x ~5s natural speech. Verify per command.
Needs: pip install vosk numpy  +  python download_voice_models.py
"""
import os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SPK_MODEL = os.path.join(HERE, "models", "vosk-model-spk-0.4")
ASR_MODEL = os.path.join(HERE, "models", "vosk-model-small-en-us-0.15")
PROFILE = os.path.join(HERE, "voice_profile.npy")
_models = None

def _models_get():
    """ASR + speaker models, loaded once (new vosk needs an ASR model
    to hang the speaker embedding on via SetSpkModel)."""
    global _models
    if _models is None:
        from vosk import Model, SpkModel
        _models = (Model(ASR_MODEL), SpkModel(SPK_MODEL))
    return _models

def _make_rec():
    from vosk import KaldiRecognizer
    asr, spk = _models_get()
    rec = KaldiRecognizer(asr, 16000)
    rec.SetSpkModel(spk)
    return rec

def xvector(pcm16_16k: bytes) -> np.ndarray:
    rec = _make_rec()
    step = 16000 * 2  # 1s chunks
    res = ""
    for i in range(0, len(pcm16_16k), step):
        if rec.AcceptWaveform(pcm16_16k[i:i + step]):
            res = rec.Result()
    if not res:
        res = rec.FinalResult()
    try:
        vec = np.array(json.loads(res).get("spk", []), dtype=np.float32)
    except Exception:
        vec = np.zeros(0, dtype=np.float32)
    n = np.linalg.norm(vec)
    return vec / n if n > 0 else vec

def enroll(samples: list) -> float:
    """samples: list of pcm bytes. Saves avg voiceprint. Returns 100.0."""
    vecs = [xvector(s) for s in samples if len(s) > 16000 * 2 * 2]
    if not vecs:
        raise ValueError("too short — speak ~5s each")
    avg = np.mean(vecs, axis=0)
    avg = avg / np.linalg.norm(avg)
    np.save(PROFILE, avg)
    return 100.0

def verify(pcm16_16k: bytes, threshold: float = 0.65) -> tuple:
    """Returns (match: bool, score: float)."""
    if not os.path.exists(PROFILE):
        return (False, 0.0)
    prof = np.load(PROFILE)
    v = xvector(pcm16_16k)
    if v.size == 0 or np.linalg.norm(v) == 0:
        # no usable audio captured - don't lock the boss out over a glitch
        return (True, -1.0)
    score = float(np.dot(prof, v))
    return (score >= threshold, score)

def has_profile() -> bool:
    return os.path.exists(PROFILE)
