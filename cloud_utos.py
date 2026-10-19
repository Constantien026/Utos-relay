"""UTOS Cloud Relay - works on any WiFi (phone on data, PC on school WiFi).
Run locally:  python cloud_utos.py
Deploy:       same as voltgo-backend (gunicorn cloud_utos:app)
Phone -> POST /api/utos/push -> PC polls GET /api/utos/poll -> PC POST /api/utos/result
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime, uuid, os, json, urllib.request

app = Flask(__name__)
CORS(app)

# user_id -> {"cmd_id":..., "cmd":..., "args":..., "status":"pending", "at":...}
PENDING = {}
# cmd_id -> {"result":..., "type":"text|image", "at":...}
RESULTS = {}
# user_id -> last heartbeat iso
SEEN = {}

def now():
    return datetime.datetime.now().isoformat()

def pc_online(user_id):
    """PC agent heartbeats every 2s, so fresh = online."""
    last = SEEN.get(user_id)
    if not last:
        return False
    try:
        dt = datetime.datetime.fromisoformat(last)
        return (datetime.datetime.now() - dt).total_seconds() < 20
    except Exception:
        return False

PERSONA_STYLE = {
    "Jarvis": "dry, loyal, cinematic butler-mechanic who calls the user 'boss'",
    "Butler": "formal, polished British butler who calls the user 'sir'",
    "Buddy": "casual, energetic best friend",
    "Professor": "warm patient teacher who explains with a quick example",
    "Pirate": "cheerful ship's captain with light pirate slang",
}

def cloud_answer(q, persona):
    """Answer from the cloud when the PC is asleep - works 24/7 like a normal AI chatbot."""
    key = os.environ.get("GEMINI_KEY", "").strip().strip('"')
    style = PERSONA_STYLE.get(persona, PERSONA_STYLE["Jarvis"])
    sys = (f"You are UTOS, {style}. Today is {datetime.datetime.now():%A, %B %d, %Y %I:%M %p}. "
           "The user's PC is currently OFF/asleep, so you cannot control it - chat normally; "
           "if they ask for PC actions (open apps, music, volume...), tell them to wake the laptop. "
           "Keep replies 1-3 sentences.")
    import time
    last_err = ""
    for attempt in (range(2) if key else []):  # no key? straight to keyless fallback
        for model, to in (("gemini-flash-latest", 25), ("gemini-flash-lite-latest", 40)):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                body = json.dumps({"contents": [{"parts": [{"text": sys + "\nBoss says: " + q}]}]}).encode()
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=to) as r:
                    j = json.loads(r.read().decode())
                return j["candidates"][0]["content"]["parts"][0]["text"][:1200]
            except Exception as e:
                last_err = str(e)[:120]
                if "404" in last_err:
                    continue  # dead model name - next
                break  # 503/timeout - wait, then retry the round
        time.sleep(2 * (attempt + 1))
    # last resort: free keyless brain (Pollinations) - still answers with PC off
    try:
        import urllib.parse
        prompt = urllib.parse.quote(sys + "\nBoss says: " + q, safe="")
        with urllib.request.urlopen(f"https://text.pollinations.ai/{prompt}?model=openai", timeout=30) as r:
            return r.read().decode()[:1200]
    except Exception as e:
        last_err = f"{last_err} | pollinations: {str(e)[:80]}"
    print("[relay] cloud_answer failed:", last_err)
    return None

@app.route("/")
def health():
    return jsonify({"ok": True, "service": "UTOS relay", "time": now()})

@app.route("/api/utos/push", methods=["POST"])
def push():
    d = request.json or {}
    user_id = d.get("user_id", "solo").strip() or "solo"
    cmd = d.get("cmd", "").strip().lower()
    if not cmd:
        return jsonify({"error": "empty cmd"}), 400
    cmd_id = uuid.uuid4().hex[:8]
    # PC asleep? Chats still get answered by the cloud brain; PC actions report offline.
    if not pc_online(user_id):
        if cmd == "chat" or cmd.startswith("chat "):
            q = (cmd[5:].strip() if cmd.startswith("chat ") else (d.get("args", "") or "").strip())
            ans = cloud_answer(q, d.get("persona", "Jarvis")) or \
                "I can't reach the cloud brain right now, boss. Try again in a moment."
            RESULTS[cmd_id] = {"result": "☁️ " + ans, "type": "text", "at": now(), "cloud": True}
            return jsonify({"cmd_id": cmd_id, "status": "cloud"})
        RESULTS[cmd_id] = {"result": "PC is offline, boss - that one needs the laptop awake. I can still chat though.",
                           "type": "text", "at": now(), "cloud": True}
        return jsonify({"cmd_id": cmd_id, "status": "pc_offline"})
    PENDING[user_id] = {"cmd_id": cmd_id, "user_id": user_id, "cmd": cmd,
                        "args": d.get("args", ""), "voice": d.get("voice", ""),
                        "persona": d.get("persona", "Jarvis"),
                        "status": "pending", "at": now()}
    return jsonify({"cmd_id": cmd_id, "status": "queued"})

@app.route("/api/utos/poll")
def poll():
    user_id = request.args.get("user_id", "solo")
    SEEN[user_id] = now()  # polling itself proves the PC agent is alive
    job = PENDING.get(user_id)
    if not job:
        return jsonify({"cmd": None})
    return jsonify(job)

@app.route("/api/utos/result", methods=["POST"])
def result():
    d = request.json or {}
    cmd_id = d.get("cmd_id", "")
    if not cmd_id:
        return jsonify({"error": "no cmd_id"}), 400
    RESULTS[cmd_id] = {"result": d.get("result", ""), "type": d.get("type", "text"), "at": now()}
    # clear pending if it matches
    for uid, job in list(PENDING.items()):
        if job.get("cmd_id") == cmd_id:
            PENDING.pop(uid, None)
    return jsonify({"ok": True})

@app.route("/api/utos/result/<cmd_id>")
def get_result(cmd_id):
    r = RESULTS.get(cmd_id)
    if not r:
        return jsonify({"done": False})
    return jsonify({"done": True, **r})

@app.route("/api/utos/heartbeat", methods=["POST"])
def heartbeat():
    d = request.json or {}
    user_id = d.get("user_id", "solo")
    SEEN[user_id] = now()
    return jsonify({"ok": True, "at": SEEN[user_id]})

@app.route("/api/utos/status")
def status():
    user_id = request.args.get("user_id", "solo")
    last = SEEN.get(user_id)
    return jsonify({"online": pc_online(user_id), "last_seen": last, "has_pending": user_id in PENDING})

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
