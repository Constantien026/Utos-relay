"""UTOS PC Agent - runs on your laptop, polls cloud relay (works on any WiFi).
Usage:
  pip install -r requirements-utos.txt
  python pc_agent.py --cloud http://127.0.0.1:5001 --user solo
For different-WiFi demo, set --cloud to your Render URL.
"""
import argparse, time, os, sys, base64, io
import requests

try:
    import psutil
except Exception:
    psutil = None

def do_status(args=""):
    if not psutil:
        return "psutil not installed"
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory().percent
    try:
        bat = psutil.sensors_battery()
        bat_s = f"{int(bat.percent)}% {'charging' if bat.power_plugged else 'discharging'}" if bat else "no battery sensor"
    except Exception:
        bat_s = "n/a"
    return f"CPU {cpu}% | RAM {mem}% | Battery {bat_s}"

def do_lock(args=""):
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "PC locked."
        else:
            os.system("loginctl lock-session || gnome-screensaver-command -l || pmset displaysleepnow")
            return "Lock sent."
    except Exception as e:
        return f"lock failed: {e}"

def do_screenshot(args=""):
    try:
        from mss import mss
        with mss() as sct:
            shot = sct.grab(sct.monitors[1])
            from PIL import Image
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return ("data:image/jpeg;base64," + b64, "image")
    except Exception:
        try:
            import pyautogui
            buf = io.BytesIO()
            pyautogui.screenshot().convert("RGB").save(buf, format="JPEG", quality=60)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return ("data:image/jpeg;base64," + b64, "image")
        except Exception as e:
            return (f"screenshot failed: {e}. pip install mss pillow pyautogui", "text")

def find_brave():
    import shutil
    cands = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        shutil.which("brave") or "",
        shutil.which("brave.exe") or "",
    ]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return ""

def open_uwp(keyword, fallback_url=""):
    """Launch Microsoft Store app matching keyword, e.g. Facebook. Returns (ok, msg)."""
    import subprocess
    try:
        ps = (f"$p = Get-AppxPackage *{keyword}* | Select-Object -First 1; "
              "if ($p) { $p.PackageFamilyName }")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=10)
        fam = (r.stdout or "").strip().splitlines()
        fam = [x.strip() for x in fam if x.strip()]
        if not fam:
            return (False, f"no Store app matching '{keyword}'")
        # try launch via shell:appsFolder
        for f in fam:
            for cmd in (f'explorer.exe shell:appsFolder\\{f}!App',
                        f'explorer.exe shell:appsFolder\\{f}!{f}'):
                try:
                    subprocess.Popen(cmd, shell=True)
                    return (True, f"Opened {keyword} app.")
                except Exception:
                    continue
        return (False, f"found {fam[0]} but launch failed")
    except Exception as e:
        return (False, f"uwp err: {e}")

def do_open(args=""):
    a = (args or "").lower().strip()
    import subprocess, webbrowser
    targets = {
        "brave": find_brave() or r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "vscode": "code", "notepad": "notepad",
        "explorer": "explorer", "cmd": "cmd",
    }
    if a in ("brave-browser", "brave browser"):
        a = "brave"
    # Per-app preference: Store app for some, browser for others.
    # "<name> app" forces Store app, "<name> web" forces browser.
    force_app = a.endswith(" app")
    force_web = a.endswith(" web")
    base = a[:-4].strip() if (force_app or force_web) else a
    APP_SEARCH = {"facebook": "Facebook", "fb": "Facebook",
                  "messenger": "Messenger", "instagram": "Instagram",
                  "tiktok": "TikTok", "spotify": "Spotify",
                  "netflix": "Netflix", "telegram": "Telegram"}
    APP_FIRST = {"facebook", "fb", "messenger", "instagram"}  # open Store app by default
    key = APP_SEARCH.get(base, base)
    if force_app or (base in APP_FIRST and not force_web):
        ok, msg = open_uwp(key)
        if ok:
            return msg
        if force_app:
            return f"{msg}. Try '{base} web' for browser."
        # else fall through to browser URL below
    shorts = {
        "yt music": "https://music.youtube.com",
        "youtube music": "https://music.youtube.com",
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "drive": "https://drive.google.com",
        "facebook": "https://www.facebook.com",
        "fb": "https://www.facebook.com",
        "facebook web": "https://www.facebook.com",
        "messenger": "https://www.messenger.com",
        "messenger web": "https://www.messenger.com",
        "instagram": "https://www.instagram.com",
        "ig": "https://www.instagram.com",
        "tiktok": "https://www.tiktok.com",
        "x": "https://x.com",
        "twitter": "https://x.com",
        "github": "https://github.com",
    }
    if base in shorts:
        show = a  # keep what user typed for the reply
        url = shorts[base]
        brave = find_brave()
        # 1) try Brave directly
        if brave:
            try:
                subprocess.Popen([brave, url])
                return f"Opened {show} in Brave."
            except Exception as e1:
                err1 = str(e1)
            else:
                err1 = ""
        else:
            err1 = f"Brave exe not found. Checked Program Files + LocalAppData + PATH."
        # 2) fallback: default browser always works
        try:
            webbrowser.open(url)
            return f"Brave not found, opened {show} in default browser instead. ({err1})"
        except Exception as e2:
            return f"open {show} failed. {err1} Browser fallback: {e2}"
    try:
        if a in targets:
            t = targets[a]
            if os.name == "nt" and os.path.exists(t):
                os.startfile(t)  # noqa
            else:
                subprocess.Popen(t, shell=True)
            return f"Opened {a}."
        elif a.startswith("http"):
            try:
                brave = find_brave()
                if brave:
                    subprocess.Popen([brave, a])
                    return f"Opened {a} in Brave."
                webbrowser.open(a)
                return f"Opened {a}."
            except Exception as e:
                return f"open failed: {e}"
        elif a:
            return f"I don't know how to open '{a}', boss. Try open + brave / vscode / notepad, or add a shortcut."
        return "Say open + brave / vscode / notepad."
    except Exception as e:
        return f"open failed: {e}"

def strip_wake(q):
    import re
    q = q.strip()
    for _ in range(6):
        nq = re.sub(r"^(hey|ay|eh|oh|hi|hello)\b[\s,]*", "", q, flags=re.I).strip()
        nq = re.sub(r"^(utos|utan|utus)\b[\s,]*", "", nq, flags=re.I).strip()
        nq = re.sub(r"^(please\s+)?(can you|could you|will you|would you)\s+", "", nq, flags=re.I).strip()
        if nq == q:
            break
        q = nq
    return q

def do_media(action):
    try:
        import pyautogui
        keys = {"pause": "playpause", "resume": "playpause", "playpause": "playpause",
                "next": "nexttrack", "previous": "prevtrack", "prev": "prevtrack",
                "volume up": "volumeup", "volume down": "volumedown", "mute": "volumemute"}
        a = action.lower()
        if a in ("pause", "resume"):
            pyautogui.press("playpause")
            return "Paused." if a == "pause" else "Resumed, boss."
        if a in keys:
            pyautogui.press(keys[a])
            return f"Done: {a}, boss."
        return f"Unknown media cmd {action}."
    except Exception as e:
        return f"media failed: {e}"

def do_play(query, where="music"):
    import subprocess, urllib.parse, webbrowser
    q = (query or "").strip()
    if not q:
        return "What should I play, boss?"
    safe = urllib.parse.quote(q)
    if where == "youtube":
        url = f"https://www.youtube.com/results?search_query={safe}"
        label = "YouTube"
    else:
        url = f"https://music.youtube.com/search?q={safe}"
        label = "YT Music"
    brave = find_brave()
    try:
        if brave:
            subprocess.Popen([brave, url])
        else:
            webbrowser.open(url)
        return f"Playing '{q}' on {label} — tap the first result, boss."
    except Exception as e:
        return f"play failed: {e}"

def try_command(q):
    """Natural-language -> real action. Returns reply or None."""
    import re
    t = strip_wake(q.lower()).strip()
    # open X [and play Y] — "open" may sit anywhere ("open up yt music and play me ...")
    m = re.search(r"open(?:\s+up)?\s+(.+?)(?:\s+and\s+play\s+(.+))?$", t)
    if m:
        target, song = m.group(1).strip(), (m.group(2) or "").strip()
        song = re.sub(r"^(me|us)\s+", "", song).strip()
        yt_alias = {"yt", "yt music", "youtube music", "music", "youtube"}
        if song and song not in ("some music", "something", "anything"):
            r1 = do_open(target if target not in ("yt",) else "yt music")
            r2 = do_play(song, where="youtube" if "youtube" in target and "music" not in target else "music")
            return f"{r1} {r2}"
        # plain open ("open up youtube music", "play me some music" lands below)
        if target in yt_alias or "youtube music" in target:
            return do_open("yt music")
        if target and target not in ("it", "that", "this", "my laptop", "my pc", "my computer",
                                     "up", "for me", "for me please", "please"):
            return do_open(target)
        if "music" in t:
            return do_open("yt music")
        return None
    # play X [on Y] / "play me some music"
    if re.search(r"\bplay\b", t):
        if re.search(r"play\s+(me\s+)?(some\s+)?(music|something)\s*$", t):
            return do_open("yt music")
    m = re.search(r"play\s+(.+?)(?:\s+on\s+(youtube|yt music|yt|music))?\s*$", t)
    if m:
        song, where = m.group(1).strip(), (m.group(2) or "music").strip()
        if song in ("it", "that", "the one", "the song"):
            return "Which song, boss? Say play + title."
        w = "youtube" if where in ("youtube", "yt") and "music" not in where else "music"
        return do_play(song, where=w)
    # media keys
    if any(k in t for k in ("pause the music", "pause music", "pause it")):
        return do_media("pause")
    if any(k in t for k in ("resume", "continue playing")):
        return do_media("resume")
    if "next song" in t or ("next" in t and "song" in t):
        return do_media("next")
    if "previous song" in t or "last song" in t:
        return do_media("previous")
    if "volume up" in t:
        return do_media("volume up")
    if "volume down" in t:
        return do_media("volume down")
    if "mute" in t:
        return do_media("mute")
    # direct system verbs
    if t in ("lock", "lock pc", "lock my pc", "lock it"):
        return do_lock()
    if t in ("screenshot", "take a screenshot", "screenshot it"):
        return "__SCREENSHOT__"
    if t in ("status", "pc status", "how is my pc"):
        return do_status()
    return None

PERSONAS = {
    "Jarvis":   ("loyal and witty, calls user 'boss'", "Yes boss. "),
    "Butler":   ("formal and precise, calls user 'sir'", "Certainly, sir. "),
    "Buddy":    ("casual and hyped, calls user 'bro'", "Got you, bro! "),
    "Professor":("patient teacher, explains simply with one example", ""),
    "Pirate":   ("rowdy pirate, says 'arr' once per reply", "Arr! "),
}

def style(text, persona):
    pre = PERSONAS.get(persona, PERSONAS["Jarvis"])[1]
    if pre and not text.lower().startswith(pre.strip().lower()[:3]):
        return pre + text
    return text

def do_chat(cmd_full, persona="Jarvis"):
    import datetime
    raw = cmd_full[5:].strip() if cmd_full.lower().startswith("chat ") else cmd_full.strip()
    acted = try_command(raw)
    if acted == "__SCREENSHOT__":
        return "__SCREENSHOT__"
    if acted:
        return style(acted, persona)
    q = raw
    import memory as mem
    # teach / remember / forget
    import re as _re
    m = _re.match(r"remember that (.+?) is (.+)", q, flags=_re.I)
    if m:
        mem.remember_fact(m.group(1).strip(), m.group(2).strip())
        return style(f"Noted, I'll remember {m.group(1).strip()}.", persona)
    m = _re.match(r"my name is (\w+)", q, flags=_re.I)
    if m:
        mem.remember_fact("name", m.group(1))
        return style(f"Nice to meet you, {m.group(1)}.", persona)
    m = _re.match(r"forget (.+)", q, flags=_re.I)
    if m:
        n = mem.forget(m.group(1).strip())
        return style(f"Forgot {n} thing(s) about '{m.group(1).strip()}'.", persona)
    m = _re.match(r"(.+?)\s+means\s+(.+)", q, flags=_re.I)
    if m and len(m.group(1)) < 60:
        mem.teach(m.group(1).strip(), m.group(2).strip())
        return style(f"Learned: '{m.group(1).strip()}'. I'll answer that from now on.", persona)
    taught = mem.lookup_learned(q)
    if taught:
        return style(taught, persona)
    # fast local intents (no API needed, always works)
    local = offline_answer(cmd_full, persona)
    # if offline brain knew it (not the generic fallback), return it
    if not local.startswith("Got it:"):
        mem.push_history("boss", q); mem.push_history("utos", local)
        return style(local, persona)
    key = os.environ.get("GEMINI_KEY", "")
    if not key:
        return local + " (Tip: set GEMINI_KEY on PC for full Jarvis answers.)"
    pstyle = PERSONAS.get(persona, PERSONAS["Jarvis"])[0]
    for model in ("gemini-flash-latest", "gemini-1.5-flash", "gemini-2.0-flash"):
        try:
            import json, urllib.request
            sys = (f"You are UTOS, {pstyle}. "
                   f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}. "
                   + (mem.facts_text() + " " if mem.facts_text() else "")
                   + ("Recent chat:\n" + mem.history_text() + "\n" if mem.history_text() else "")
                   + "You can control his PC (status, lock, screenshot, open apps). If asked to do that, say you did it. "
                   + "Keep replies 1-3 sentences.")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            body = json.dumps({"contents": [{"parts": [{"text": sys + "\nBoss says: " + q}]}]}).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.loads(r.read().decode())
                ans = j["candidates"][0]["content"]["parts"][0]["text"][:1200]
                mem.push_history("boss", q); mem.push_history("utos", ans)
                return style(ans, persona)
        except Exception as e:
            print(f"[UTOS] {model} failed: {e}")
            continue
    return local

def do_weather(place="Manila"):
    try:
        import json, urllib.request, urllib.parse
        q = urllib.parse.quote(place or "Manila")
        with urllib.request.urlopen(
            f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=en&format=json",
            timeout=10) as r:
            g = json.loads(r.read().decode())
        if not g.get("results"):
            return f"Couldn't find '{place}'."
        loc = g["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = f"{loc.get('name','')}, {loc.get('country','')}".strip(", ")
        with urllib.request.urlopen(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m&timezone=auto",
            timeout=10) as r:
            w = json.loads(r.read().decode())["current"]
        codes = {0:"clear",1:"mostly clear",2:"partly cloudy",3:"overcast",45:"foggy",48:"foggy",
                 51:"light drizzle",61:"rain",71:"snow",80:"showers",95:"thunderstorm"}
        desc = codes.get(w.get("weather_code", -1), "cloudy")
        return (f"{name}: {w['temperature_2m']}°C, feels {w['apparent_temperature']}°C, "
                f"{desc}, humidity {w['relative_humidity_2m']}%, wind {w['wind_speed_10m']} kph.")
    except Exception as e:
        return f"Weather offline: {e}"

def do_ram():
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                procs.append((p.info["memory_info"].rss, p.info["name"] or "?"))
            except Exception:
                pass
        procs.sort(reverse=True)
        total = psutil.virtual_memory()
        top = ", ".join(f"{n} {r // 1048576}MB" for r, n in procs[:5])
        tip = "Close unused Brave tabs" if any("brave" in n.lower() for _, n in procs[:3]) else "Biggest app first if you need room"
        return (f"RAM {total.percent}% used. Top: {top}. {tip}, boss.")
    except Exception as e:
        return f"RAM check failed: {e}"

def offline_answer(q, persona="Jarvis"):
    import datetime, re
    ql = q.lower()
    now = datetime.datetime.now()
    if "ram" in ql and any(w in ql for w in ("high", "why", "usage", "much", "full", "%")):
        return style(do_ram(), persona)
    if any(w in ql for w in ("weather", "temperature", "temp ", "umuulan", "mainit")):
        # extract place after "in", default Manila NCR
        place = "Manila"
        if " in " in ql:
            place = ql.split(" in ", 1)[1].split(" now")[0].split(" today")[0].strip(" ?.") or place
        return do_weather(place)
    if any(w in ql for w in ("what day", "day is today", "today's date", "todays date", "what date")):
        return f"Today is {now.strftime('%A, %B %d, %Y')}."
    if any(w in ql for w in ("what time", "time is it", "current time")):
        return f"It's {now.strftime('%I:%M %p')}."
    if "who are you" in ql or "your name" in ql:
        return "I am UTOS - Universal Task & OS Assistant. Utos mo, sundin ko. Your personal Jarvis, boss."
    if "enroll" in ql and "voice" in ql:
        return "Voice enroll is off, boss. Use Settings > Voice PIN lock instead — only your code unlocks me."
    if any(w in ql for w in ("how are you", "kamusta")):
        return "Running smooth, boss. All systems nominal. How can I serve you?"
    if "thank" in ql or "salamat" in ql:
        return "Always a pleasure, boss."
    if "joke" in ql:
        return "Why did the PC go to therapy? Too many unresolved issues, boss."
    if any(w in ql for w in ("good morning", "good afternoon", "good evening", "good night")):
        return f"{now.strftime('%I:%M %p')} on {now.strftime('%A')}, boss. What is the order?"
    if "open" in ql and any(w in ql for w in ("facebook", "youtube", "brave", "vscode", "music")):
        return "On it — use the quick action or say open + name, boss. I will launch it on your PC."
    bank = {
        "ip address": "An IP address is your device's address on a network, e.g. 192.168.1.10. IPv4 = 4 numbers, IPv6 is longer.",
        "subnet": "A subnet mask splits an IP into network + host parts. 255.255.255.0 = first 24 bits are network.",
        "thesis": "Tip: back up thesis.docx to Drive + USB. Want me to locate the file?",
        "schedule": "Demo schedule: IT Capstone 9AM, Networking Lab 1PM. Edit pc_agent.py to load your real sched.json.",
        "brave": "Brave is open. Anything else, boss?",
        "hello": "Hello boss. Online and ready. Try status, screenshot, or ask me the time.",
        "hi": "Hi boss. What is the order?",
    }
    for k, v in bank.items():
        if k in ql:
            return v
    qq = ql[5:] if ql.startswith("chat ") else ql
    return f"Got it: '{qq}'. I can do status | lock | screenshot | open brave | or answer time, date, IP, subnet."

ENROLL_SAMPLES = []

def run_job(job):
    import base64
    cmd = job.get("cmd", "")
    args = job.get("args", "")
    persona = job.get("persona", "Jarvis")
    # voice-ID gate (free, offline, no signup). Phone attaches 16kHz mono PCM b64.
    # Enroll via cmd voice_enroll (3 samples). Check others if profile exists.
    try:
        import voiceprint as vp
        has_vp = vp.has_profile()
    except Exception:
        has_vp = False
        vp = None
    if cmd == "voice_enroll":
        try:
            raw = base64.b64decode(job.get("voice", ""))
            ENROLL_SAMPLES.append(raw)
            if len(ENROLL_SAMPLES) >= 3:
                vp.enroll(ENROLL_SAMPLES)
                ENROLL_SAMPLES.clear()
                return ("Voice enrolled. Only your voice unlocks me now, boss.", "text")
            return (f"Sample {len(ENROLL_SAMPLES)}/3 saved. Speak again.", "text")
        except Exception as e:
            return (f"enroll failed: {e}", "text")
    if cmd == "voice_status":
        return (f"voice profile: {'enrolled' if has_vp else 'none'}", "text")
    if has_vp and job.get("voice"):
        try:
            import base64 as _b
            ok, score = vp.verify(_b.b64decode(job["voice"]))
            print(f"[UTOS] voice score {score:.2f}")
            if not ok:
                return ("Voice not recognized, boss. Ignoring.", "text")
        except Exception as e:
            print("[UTOS] voice verify err:", e)
    if cmd == "status":
        return (do_status(args), "text")
    if cmd == "lock":
        return (do_lock(args), "text")
    if cmd == "screenshot":
        return do_screenshot(args)
    if cmd == "open":
        return (do_open(args), "text")
    if cmd.startswith("chat ") or cmd == "chat":
        full = cmd if cmd != "chat" else f"chat {args}"
        r = do_chat(full, persona)
        if r == "__SCREENSHOT__":
            return do_screenshot(args)
        return (r, "text")
    # allow "chat <question>" pushed as cmd with space
    if cmd.startswith("chat"):
        r = do_chat(cmd, persona)
        if r == "__SCREENSHOT__":
            return do_screenshot(args)
        return (r, "text")
    return (f"Unknown cmd '{cmd}'. Try status, lock, screenshot, open brave, chat hi", "text")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", default="http://127.0.0.1:5001")
    ap.add_argument("--user", default="solo")
    a = ap.parse_args()
    cloud = a.cloud.rstrip("/")
    user = a.user
    print(f"[UTOS] polling {cloud} as user={user}")
    print("[UTOS] v7 personas+memory+follow (if you don't see v7, you run old file)")
    while True:
        try:
            requests.post(f"{cloud}/api/utos/heartbeat", json={"user_id": user}, timeout=8)
            r = requests.get(f"{cloud}/api/utos/poll", params={"user_id": user}, timeout=10)
            job = r.json()
            if job.get("cmd"):
                print("[UTOS] job:", job)
                out, typ = run_job(job)
                # truncate huge images? keep, cloud is in-memory demo
                requests.post(f"{cloud}/api/utos/result",
                              json={"cmd_id": job["cmd_id"], "result": out, "type": typ}, timeout=15)
                print("[UTOS] done", job["cmd_id"], typ, len(str(out)))
        except Exception as e:
            print("[UTOS] poll err:", e)
        time.sleep(2)

if __name__ == "__main__":
    main()
