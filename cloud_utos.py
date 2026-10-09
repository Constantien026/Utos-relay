"""UTOS Cloud Relay - works on any WiFi (phone on data, PC on school WiFi).
Run locally:  python cloud_utos.py
Deploy:       same as voltgo-backend (gunicorn cloud_utos:app)
Phone -> POST /api/utos/push -> PC polls GET /api/utos/poll -> PC POST /api/utos/result
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime, uuid

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
    PENDING[user_id] = {"cmd_id": cmd_id, "user_id": user_id, "cmd": cmd,
                        "args": d.get("args", ""), "voice": d.get("voice", ""),
                        "persona": d.get("persona", "Jarvis"),
                        "status": "pending", "at": now()}
    return jsonify({"cmd_id": cmd_id, "status": "queued"})

@app.route("/api/utos/poll")
def poll():
    user_id = request.args.get("user_id", "solo")
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
    online = False
    if last:
        try:
            dt = datetime.datetime.fromisoformat(last)
            online = (datetime.datetime.now() - dt).total_seconds() < 15
        except Exception:
            pass
    return jsonify({"online": online, "last_seen": last, "has_pending": user_id in PENDING})

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
