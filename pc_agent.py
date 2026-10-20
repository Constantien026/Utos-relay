"""UTOS PC Agent - runs on your laptop, polls cloud relay (works on any WiFi).
Usage:
  pip install -r requirements-utos.txt
  python pc_agent.py --cloud http://127.0.0.1:5001 --user solo
For different-WiFi demo, set --cloud to your Render URL.
"""
import argparse, time, os, sys, base64, io, threading
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

def do_volume(spec):
    import re
    s = (spec or "").lower()
    try:
        from pycaw.pycaw import AudioUtilities
        dev = AudioUtilities.GetSpeakers()
        if "mute" in s and "unmute" not in s:
            dev.EndpointVolume.SetMute(1, None)
            return "Muted, boss."
        if "unmute" in s:
            dev.EndpointVolume.SetMute(0, None)
            return "Unmuted, boss."
        m = re.search(r"(\d+)\s*%?", s)
        if m:
            lvl = max(0, min(100, int(m.group(1)))) / 100
            dev.EndpointVolume.SetMasterVolumeLevelScalar(lvl, None)
            return f"Volume {int(lvl * 100)}%, boss."
        cur = getattr(dev, "volume_percent", None)
        if callable(cur):
            cur = cur()
        return f"Volume {cur}%, boss. Say volume + number."
    except Exception as e:
        return f"volume failed ({e}). Try volume up / down / mute."

def do_brightness(spec):
    import re
    try:
        import screen_brightness_control as sbc
        m = re.search(r"(\d+)\s*%?", spec or "")
        if m:
            lvl = max(0, min(100, int(m.group(1))))
            sbc.set_brightness(lvl)
            return f"Brightness {lvl}%, boss."
        cur = sbc.get_brightness()
        return f"Brightness {cur[0] if cur else '?'}%. Say brightness + number."
    except Exception as e:
        return f"brightness failed ({e})."

def find_openrgb():
    import shutil
    cands = [shutil.which("openrgb") or "",
             r"C:\Program Files\OpenRGB\OpenRGB.exe",
             os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "OpenRGB.exe")]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return ""

def do_kb(spec):
    import re, subprocess
    m = re.search(r"(\d+)\s*%?", spec or "")
    lvl = max(0, min(100, int(m.group(1)) if m else 100))
    # ASUS TUF (this machine): OpenRGB drives the Aura keyboard, free, no signup.
    orb = find_openrgb()
    if orb:
        try:
            subprocess.Popen([orb, "--device", "0", "--mode", "Static",
                              "--brightness", str(lvl)], shell=False)
            return f"Keyboard backlight {lvl}%, boss."
        except Exception as e:
            return f"OpenRGB call failed ({e}). Is it running once for setup?"
    return ("TUF keyboards need OpenRGB (free): install it, run once to detect "
            "the Aura keyboard, then say brightness again. Quick manual: Fn+F7, "
            "or Armoury Crate / G-Helper, boss.")

def word_num(t):
    import re
    m = re.search(r"(\d+)", t)
    if m:
        return max(1, min(20, int(m.group(1))))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "couple": 2, "few": 3}
    for w, n in words.items():
        if re.search(rf"\b{w}\b", t):
            return n
    return 1

def focus_brave():
    """Focus existing Brave window WITHOUT opening a new one. Returns True if focused."""
    try:
        import pygetwindow as _gw
        for title in ("YouTube Music", "youtube music", " - Brave", "Brave"):
            try:
                wins = _gw.getWindowsWithTitle(title)
            except Exception:
                wins = []
            for w in wins:
                try:
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                    return True
                except Exception:
                    continue
    except Exception:
        pass
    return False

def do_tabs(direction, n=1):
    try:
        import pyautogui, time
        pyautogui.FAILSAFE = False
        if not focus_brave():
            return "Brave isn't open, boss. Open it first."
        time.sleep(0.6)
        for _ in range(max(1, min(20, n))):
            if direction == "back":
                pyautogui.hotkey("ctrl", "shift", "tab")
            else:
                pyautogui.hotkey("ctrl", "tab")
            time.sleep(0.25)
        return f"Moved {n} tab(s) {direction}, boss."
    except Exception as e:
        return f"tab move failed: {e}"

def do_power(action, timer=30):
    import subprocess
    try:
        if action == "cancel":
            subprocess.Popen("shutdown /a", shell=True)
            return "Shutdown cancelled, boss. We're staying on."
        if action == "restart":
            subprocess.Popen(f"shutdown /r /t {timer}", shell=True)
            return f"Restarting in {timer}s, boss. Say cancel shutdown to stop it."
        if action == "sleep":
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
            return "Sleeping now, boss."
        subprocess.Popen(f"shutdown /s /t {timer}", shell=True)
        return f"Shutting down in {timer}s, boss. Say cancel shutdown to stop it."
    except Exception as e:
        return f"power failed: {e}"

def do_media(action):
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
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

def resolve_song(query):
    """Best watch URL for query via yt-dlp. Fuzzy-picks from top 5."""
    try:
        from yt_dlp import YoutubeDL
        with YoutubeDL({"quiet": True, "noplaylist": True, "socket_timeout": 12}) as y:
            info = y.extract_info(f"ytsearch5:{query}", download=False)
            entries = [e for e in (info.get("entries") or []) if e and e.get("webpage_url")]
            if not entries:
                return None
            import re
            qwords = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
            def score(e):
                t = (e.get("title") or "").lower()
                s = sum(2 for w in qwords if w in t)
                if "official" in t:
                    s += 1
                return s
            entries.sort(key=score, reverse=True)
            return entries[0]["webpage_url"]
    except Exception as ex:
        print("[UTOS] resolve failed:", ex)
    return None

def do_play(query, where="music"):
    import subprocess, urllib.parse, webbrowser
    q = (query or "").strip()
    if not q:
        return "What should I play, boss?"
    # pinned songs: "remember song <name> is <url>"
    try:
        import memory as _mem, re as _re
        d = _mem._load()
        for k, v in d.get("facts", {}).items():
            if k.startswith("song:") and k[5:] and all(
                    w in q.lower() for w in _re.findall(r"[a-z0-9]+", k[5:]) if len(w) > 2):
                url = v if v.startswith("http") else v
                import subprocess as _sp, webbrowser as _wb
                _b = find_brave()
                if _b:
                    _sp.Popen([_b, "--autoplay-policy=no-user-gesture-required", url])
                else:
                    _wb.open(url)
                return f"Now playing '{q}', boss."
    except Exception:
        pass
    url = resolve_song(q)
    if url:
        if where != "youtube" and "youtube.com" in url:
            url = url.replace("www.youtube.com/watch", "music.youtube.com/watch", 1)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}autoplay=1"
        try:
            import memory as _mem2
            if (_mem2._load().get("facts", {}).get("captions", "") == "on"
                    or "caption" in q.lower() or "subtitle" in q.lower()):
                url += "&cc_load_policy=1&cc_lang_pref=en"
        except Exception:
            pass
        brave = find_brave()
        # no-user-gesture flag: autoplay=1 actually plays without a click
        flag = "--autoplay-policy=no-user-gesture-required"
        try:
            # reuse the existing Brave tab (navigate it) so old + new never overlap
            navigated = False
            if brave:
                try:
                    import pyautogui as _pg
                    _pg.FAILSAFE = False
                    if not focus_brave():
                        raise RuntimeError("no Brave window")
                    import time as _t
                    _t.sleep(1.0)
                    _pg.hotkey("ctrl", "l")
                    _t.sleep(0.4)
                    _pg.typewrite(url, interval=0.005)
                    _pg.press("enter")
                    navigated = True
                except Exception as _e:
                    print("[UTOS] tab-reuse failed, new tab:", _e)
            if not navigated:
                if brave:
                    subprocess.Popen([brave, flag, url])
                else:
                    webbrowser.open(url)
            return f"Now playing '{q}', boss."
        except Exception as e:
            return f"play failed: {e}"
    safe = urllib.parse.quote(q)
    fallback = (f"https://www.youtube.com/results?search_query={safe}"
                if where == "youtube" else f"https://music.youtube.com/search?q={safe}")
    try:
        if find_brave():
            subprocess.Popen([find_brave(), fallback])
        else:
            webbrowser.open(fallback)
    except Exception:
        pass
    return f"Couldn't auto-resolve '{q}' — opened the search, tap the first result, boss."

def try_command(q, persona="Jarvis"):
    """Natural-language -> real action. Returns reply or None."""
    import re
    t = strip_wake(q.lower()).strip()
    # open X [and play Y] — "open" may sit anywhere ("open up yt music and play me ...")
    m = re.search(r"open(?:\s+up)?\s+(.+?)(?:\s+and\s+play\s+(.+))?$", t)
    if m:
        target, song = m.group(1).strip(), (m.group(2) or "").strip()
        song = re.sub(r"^(me|us)\s+", "", song).strip()
        target = re.sub(r"\s+(for me( please)?|please|up)\s*$", "", target).strip()
        if "new tab" in target:
            try:
                import pyautogui
                pyautogui.FAILSAFE = False
                os.startfile(find_brave() or "brave")
                import time as _t
                _t.sleep(0.8)
                pyautogui.hotkey("ctrl", "t")
                return "New tab, boss."
            except Exception as e:
                return f"new tab failed: {e}"
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
        if re.search(r"play\s+(me\s+)?(some\s+|any\s*)?(music|something|anything)(\s+please)?\s*$", t):
            return do_open("yt music")
    m = re.search(r"play\s+(.+?)(?:\s+on\s+(youtube|yt music|yt|music))?\s*$", t)
    if m:
        song, where = m.group(1).strip(), (m.group(2) or "music").strip()
        if song.lower() in ("the music", "music", "my music"):
            return do_media("resume")
        if song in ("it", "that", "the one", "the song"):
            return "Which song, boss? Say play + title."
        w = "youtube" if where in ("youtube", "yt") and "music" not in where else "music"
        return do_play(song, where=w)
    # tab navigation: "go back 3 tabs", "next tab", "close tab", "new tab"
    if re.search(r"\b(new)\s+tab\b", t) and "open" not in t:
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            os.startfile(find_brave() or "brave")
            import time as _t
            _t.sleep(0.8)
            pyautogui.hotkey("ctrl", "t")
            return "New tab, boss."
        except Exception as e:
            return f"new tab failed: {e}"
    if re.search(r"\b(close|kill)\b.*\btab\b", t) or re.search(r"\btab\b.*\bclose\b", t):
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            os.startfile(find_brave() or "brave")
            import time as _t
            _t.sleep(0.8)
            pyautogui.hotkey("ctrl", "w")
            return "Closed that tab, boss."
        except Exception as e:
            return f"close tab failed: {e}"
    if re.search(r"\b(back|left|previous|prev)\b", t) and "tab" in t:
        return do_tabs("back", word_num(t))
    if re.search(r"\b(forward|next|right)\b", t) and "tab" in t:
        return do_tabs("forward", word_num(t))
    # captions toggle: "captions on/off", "turn on subtitles"
    if re.search(r"\b(captions?|subtitles?|cc)\b", t):
        if re.search(r"\b(on|enable|show)\b", t):
            try:
                import memory as _mem3
                _mem3.remember_fact("captions", "on")
            except Exception:
                pass
            focus_brave()
            try:
                import pyautogui as _pg2, time as _t2
                _pg2.FAILSAFE = False
                _t2.sleep(0.6)
                _pg2.press("c")
            except Exception:
                pass
            return style("Captions on — and I'll keep them on, boss.", persona)
        if re.search(r"\b(off|disable|hide)\b", t):
            try:
                import memory as _mem4
                _mem4.remember_fact("captions", "off")
            except Exception:
                pass
            focus_brave()
            try:
                import pyautogui as _pg3, time as _t3
                _pg3.FAILSAFE = False
                _t3.sleep(0.6)
                _pg3.press("c")
            except Exception:
                pass
            return style("Captions off, boss.", persona)
    # power: shutdown / restart / sleep / cancel (30s safety timer)
    if re.search(r"\bcancel\b.*\bshut ?down\b", t) or re.search(r"\babort\b.*\bshut ?down\b", t):
        return do_power("cancel")
    m = re.search(r"\bshut ?down\b(?:\s+in\s+(\d+)\s*(?:min|m)?)?", t)
    if m or re.search(r"\bturn off\b.*\b(laptop|pc|computer)\b", t):
        mins = 0
        if m and m.group(1):
            mins = max(0, min(120, int(m.group(1))))
        return do_power("shutdown", mins * 60 if mins else 30)
    if re.search(r"\brestart\b|\breboot\b", t):
        return do_power("restart")
    if re.search(r"\bsleep\b", t) and re.search(r"\b(laptop|pc|computer|it|now)\b", t):
        return do_power("sleep")
    # media keys
    if re.search(r"\bstop\b", t) and not re.search(r"\bstop watching\b", t):
        return do_media("pause")
    if re.search(r"\bpause\b", t):
        return do_media("pause")
    if any(k in t for k in ("resume", "continue playing", "unpause", "keep playing", "start the music", "start music")):
        return do_media("resume")
    if t.strip() in ("play", "start", "play music", "start music"):
        return do_media("resume")
    if t.strip() in ("play", "play music", "play the music", "play it"):
        return do_media("resume")
    if "next song" in t or "change the music" in t or "next music" in t or "next track" in t or ("next" in t and "song" in t):
        return do_media("next")
    if "previous song" in t or "last song" in t or "previous music" in t or "last music" in t or "previous track" in t or "last track" in t:
        return do_media("previous")
    if "volume up" in t:
        return do_media("volume up")
    if "volume down" in t:
        return do_media("volume down")
    if "mute" in t and "unmute" not in t:
        return do_media("mute")
    if "unmute" in t:
        return do_volume("unmute")
    if "volume" in t or "vol " in t + " " or re.match(r"^(vol|volume)\b", t):
        return do_volume(t)
    if "keyboard" in t and ("backlight" in t or "light" in t or "brightness" in t):
        return do_kb(t)
    if "brightness" in t or "dim the screen" in t or "brighten" in t:
        return do_brightness(t)
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

def _gemini_key():
    import re
    k = os.environ.get("GEMINI_KEY", "").strip().strip('"')
    if k:
        return k
    for name in (".gemini_key", "UTOS_AutoStart.bat"):
        try:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            with open(p, encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            m = re.search(r'GEMINI_KEY="?([A-Za-z0-9._-]{10,})"?', txt)
            if m:
                return m.group(1)
        except Exception:
            pass
    return ""
def do_chat(cmd_full, persona="Jarvis"):
    import datetime
    raw = cmd_full[5:].strip() if cmd_full.lower().startswith("chat ") else cmd_full.strip()
    acted = try_command(raw, persona)
    if acted == "__SCREENSHOT__":
        return "__SCREENSHOT__"
    if acted:
        return style(acted, persona)
    q = raw
    import memory as mem
    # real-time learning FIRST: correction right after a miss ("no, ...", "the answer is ...")
    import re as _re
    import re as _re2
    pend0 = mem.take_pending()
    m0 = _re2.match(r"(?:no[,.]?\s+|wrong[,.]?\s+|actually\s+|i meant\s+)(.+)", q, flags=_re2.I)
    m02 = _re2.match(r"(?:the answer is\s+)(.+)", q, flags=_re2.I)
    if (m0 or m02) and pend0:
        correction = (m0 or m02).group(1).strip()
        if len(correction) > 2:
            # "no, X means Y" -> still a teachable pair about X
            mm = _re.match(r"(.+?)\s+means\s+(.+)", correction, flags=_re.I)
            if mm and len(mm.group(1)) < 60:
                mem.teach(pend0 + " / " + mm.group(1).strip(), mm.group(2).strip())
                mem.teach(mm.group(1).strip(), mm.group(2).strip())
            else:
                mem.teach(pend0, correction)
            return style("My bad — learned. Ask me again anytime.", persona)
    if pend0:
        mem.set_pending(pend0)  # keep for one more turn
    # teach / remember / forget
    m = _re.match(r"remember that (.+?) is (.+)", q, flags=_re.I)
    if m:
        k = m.group(1).strip()
        if k.lower().startswith("song "):
            k = "song:" + k[5:].strip()
        mem.remember_fact(k, m.group(2).strip())
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
    key = _gemini_key()
    if not key:
        return local + " (Tip: set GEMINI_KEY on PC for full Jarvis answers.)"
    pstyle = PERSONAS.get(persona, PERSONAS["Jarvis"])[0]
    for model in ("gemini-flash-latest", "gemini-flash-lite-latest"):
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
                # cache stable answers so offline-me still knows them later
                if not _re.search(r"\b(time|date|today|weather|temperature|ram|status|battery)\b", q, flags=_re.I):
                    d = mem._load()
                    learned = d.get("learned", {})
                    if len(learned) < 100:
                        learned[q.lower().strip()] = ans
                        d["learned"] = learned
                        try:
                            import json as _js
                            with open(mem.MEM, "w", encoding="utf-8") as _f:
                                _js.dump(d, _f, ensure_ascii=False, indent=1)
                        except Exception:
                            pass
                return style(ans, persona)
        except Exception as e:
            print(f"[UTOS] {model} failed: {e}")
            continue
    # Gemini down / demand spike? free keyless brain still answers
    try:
        import urllib.parse
        prompt = urllib.parse.quote(sys + "\nBoss says: " + q, safe="")
        with urllib.request.urlopen(f"https://text.pollinations.ai/{prompt}?model=openai", timeout=30) as r:
            ans = r.read().decode()[:1200]
            mem.push_history("boss", q); mem.push_history("utos", ans)
            return style(ans, persona)
    except Exception as e:
        print(f"[UTOS] pollinations failed: {e}")
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
    import memory as _mem9
    _mem9.set_pending(qq)
    return f"Got it: '{qq}'. I can do status | lock | screenshot | open brave | or answer time, date, IP, subnet."

ENROLL_SAMPLES = []

def run_job(job):
    import base64
    cmd = job.get("cmd", "")
    args = job.get("args", "")
    persona = job.get("persona", "Jarvis")
    if cmd == "shutdown":
        a = (args or "").lower()
        import re as _re2
        if "cancel" in a or "abort" in a:
            return (style(do_power("cancel"), persona), "text")
        if "restart" in a or "reboot" in a:
            return (style(do_power("restart"), persona), "text")
        if "sleep" in a:
            return (style(do_power("sleep"), persona), "text")
        m = _re2.search(r"(\d+)", a)
        if m:
            return (style(do_power("shutdown", max(0, min(7200, int(m.group(1)) * 60))), persona), "text")
        return (style(do_power("shutdown", 30), persona), "text")
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

# ---------------- Monitor tab: live mirror + touch (LAN direct, cloudflared tunnel for data) ----
MON = {"lan": "", "tunnel": "", "port": 8555, "w": 1920, "h": 1080}
PRIV = {"on": False}  # "Second screen only": phone drives, PC monitor stays dark

def _mon_power(on):
    try:
        import ctypes
        # WM_SYSCOMMAND=0x0112, SC_MONITORPOWER=0xF170, -1=on, 2=off
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1 if on else 2)
    except Exception:
        pass

def _privacy_loop():
    """Keep the PC monitor dark while the phone is the only screen; any real
    (physical) input at the PC wakes it, our injected input re-dims it.
    Auto-expires after 45s without a keepalive so a dead phone can't leave
    the PC dark forever."""
    while True:
        if PRIV["on"]:
            if time.time() - PRIV.get("at", 0) > 45:
                PRIV["on"] = False
                _mon_power(True)
            else:
                _mon_power(False)
        time.sleep(2)

def _win_id(title):
    import hashlib
    return hashlib.md5(title.encode("utf-8", "ignore")).hexdigest()[:8]

def _wid_of(w):
    """stable id = the window handle (titles change - music players put the
    track name in the title - which used to silently break Extend mid-song)."""
    h = getattr(w, "_hWnd", None) or getattr(w, "_handle", None)
    return str(h) if h else _win_id(w.title)

def _wid_match(w, wid):
    if not wid:
        return False
    if _wid_of(w) == wid:
        return True
    try:
        return _win_id(w.title) == wid  # legacy ids from older app versions
    except Exception:
        return False

def _windows_list():
    out = []
    seen = set()
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            try:
                wid = _wid_of(w)
                if w.visible and w.title and w.width > 80 and w.height > 80 and wid not in seen:
                    seen.add(wid)
                    out.append({"id": wid, "title": w.title[:70]})
            except Exception:
                continue
    except Exception:
        pass
    return out

def _window_handle(wid):
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            try:
                if _wid_match(w, wid):
                    h = getattr(w, "_hWnd", None) or getattr(w, "_handle", None)
                    if h:
                        return h
            except Exception:
                continue
    except Exception:
        pass
    return None

def _win_client_point(hwnd, nx, ny):
    """normalized frame coords -> client-area pixels of that window."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    org = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(org))
    sx = rect.left + int(nx * (rect.right - rect.left))
    sy = rect.top + int(ny * (rect.bottom - rect.top))
    return sx - org.x, sy - org.y

def _win_touch(wid, d):
    """Click/drag INSIDE a specific window via posted messages - the laptop's
    foreground and global cursor are never involved."""
    import ctypes
    hwnd = _window_handle(wid)
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    nx = max(0.0, min(1.0, float(d.get("x", 0))))
    ny = max(0.0, min(1.0, float(d.get("y", 0))))
    cx, cy = _win_client_point(hwnd, nx, ny)
    lp = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
    act = d.get("action", "click")
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
    WM_RBUTTONDOWN, WM_RBUTTONUP, MK_LBUTTON = 0x0204, 0x0205, 0x0001
    if act == "down":
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    elif act == "move":
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, MK_LBUTTON, lp)
    elif act == "up":
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    elif act == "right":
        user32.PostMessageW(hwnd, WM_RBUTTONDOWN, 0, lp)
        user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lp)
    else:
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    return True

def _win_scroll(wid, dy):
    import ctypes
    from ctypes import wintypes
    hwnd = _window_handle(wid)
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    # aim right-of-center: the video player swallows wheel events, while
    # lists/scrollbars (in almost every app) live on the right side
    cr = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    org = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(org))
    sx = org.x + int(cr.right * 0.85)
    sy = org.y + int(cr.bottom * 0.45)
    lp = ((sy & 0xFFFF) << 16) | (sx & 0xFFFF)
    notches = max(-10, min(10, int(dy / 40)))
    wparam = ((notches * 120) & 0xFFFF) << 16
    user32.PostMessageW(hwnd, 0x020A, wparam, lp)  # WM_MOUSEWHEEL
    return True

_VK = {"esc": 0x1B, "escape": 0x1B, "enter": 0x0D, "return": 0x0D, "tab": 0x09,
       "backspace": 0x08, "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27,
       "down": 0x28, "home": 0x24, "end": 0x23, "delete": 0x2E, "pageup": 0x21,
       "pagedown": 0x22, "shift": 0x10, "ctrl": 0x11, "alt": 0x12}

def _win_key(wid, key, text=""):
    """Post key/char messages straight into a window (no focus steal)."""
    import ctypes
    hwnd = _window_handle(wid)
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
    if key:
        vk = _VK.get(key.lower())
        if vk is None and len(key) == 1:
            vk = ord(key.upper())
        if vk:
            user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
            user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
    if text:
        for ch in text:
            user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
    return True

def _window_raise(wid):
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            try:
                if _wid_match(w, wid):
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

_PARK = {}      # wid -> (left, top) of where the window really lives
_PARK_SEEN = {} # wid -> last time the phone streamed this window
_PARK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parked.json")

def _park_watchdog():
    """phone stopped streaming a parked window (app closed / lost link) ->
    bring it back to the laptop so nothing stays stranded off-screen."""
    while True:
        time.sleep(20)
        now = time.time()
        for wid in list(_PARK.keys()):
            seen = _PARK_SEEN.get(wid, 0)
            if now - seen > 90:
                if _win_unpark(wid):
                    print(f"[UTOS] parked window {wid} came home (phone stopped streaming)")

def _park_save():
    try:
        json.dump(_PARK, open(_PARK_FILE, "w"))
    except Exception:
        pass

def _win_park(wid):
    """Give the window to the phone: slide it off the laptop screen except a
    2px sliver at the right edge. The sliver keeps DWM compositing the window
    (fully off-screen / 'invisible' windows stop rendering -> frozen feed),
    so the phone gets a truly LIVE picture while the laptop is free."""
    import ctypes
    from ctypes import wintypes
    hwnd = _window_handle(wid)
    if not hwnd or wid in _PARK:
        return False
    user32 = ctypes.windll.user32
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    _PARK[wid] = (r.left, r.top)
    screen_w = user32.GetSystemMetrics(0)  # primary screen width
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
    ok = user32.SetWindowPos(hwnd, 0, screen_w - 2, 100, 0, 0,
                             SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
    if not ok:
        _PARK.pop(wid, None)
        return False
    _park_save()
    return True

def _win_unpark(wid):
    import ctypes
    from ctypes import wintypes
    hwnd = _window_handle(wid)
    pos = _PARK.pop(wid, None)
    _park_save()
    if not hwnd or not pos:
        return False
    user32 = ctypes.windll.user32
    try:
        DWMWA_CLOAKED = 14
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CLOAKED, ctypes.byref(ctypes.c_int(0)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass
    SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
    user32.SetWindowPos(hwnd, 0, pos[0], pos[1], 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
    return True

def _park_restore_all():
    """crash safety: never leave a window stranded off-screen."""
    global _PARK
    try:
        if os.path.exists(_PARK_FILE):
            _PARK = json.load(open(_PARK_FILE))
    except Exception:
        _PARK = {}
    for wid in list(_PARK.keys()):
        _win_unpark(wid)

def _grab_window(wid):
    """PrintWindow capture: reads a window's own content even when it is
    covered by other windows - so Extend never has to touch the PC screen.
    Returns a PIL Image, or None (some GPU/protected windows refuse)."""
    try:
        import ctypes
        from ctypes import wintypes
        import numpy as _np
        import pygetwindow as gw
        hwnd = None
        for w in gw.getAllWindows():
            if _wid_match(w, wid):
                hwnd = getattr(w, "_hWnd", None) or getattr(w, "_handle", None) or getattr(w, "_hwnd", None)
                if hwnd:
                    break
        if not hwnd:
            return None
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None
        hwnd_dc = user32.GetWindowDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        gdi32.SelectObject(mem_dc, bmp)
        # 2 = PW_RENDERFULLCONTENT (works for Chrome/Brave/Electron too)
        ok = user32.PrintWindow(hwnd, mem_dc, 2)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = width
        bi.biHeight = -height  # top-down
        bi.biPlanes = 1
        bi.biBitCount = 32
        buf = ctypes.create_string_buffer(width * height * 4)
        got = gdi32.GetDIBits(mem_dc, bmp, 0, height, buf, ctypes.byref(bi), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
        if not ok or got == 0:
            return None
        arr = _np.frombuffer(buf.raw, dtype=_np.uint8).reshape(height, width, 4)[:, :, :3]
        from PIL import Image
        img = Image.fromarray(arr[:, :, ::-1])  # BGRA -> RGB
        # all-black usually means the window refused (game/anti-cheat) -> caller falls back
        if img.convert("L").getextrema()[1] < 8:
            return None
        return img
    except Exception as e:
        print("[UTOS] PrintWindow failed:", e)
        return None

def _window_rect(wid):
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            try:
                if _wid_match(w, wid) and w.width > 0 and w.height > 0:
                    return {"left": int(w.left), "top": int(w.top),
                            "width": int(w.width), "height": int(w.height)}
            except Exception:
                continue
    except Exception:
        pass
    return None

def _lan_ip():
    """All candidate IPs, best first: home LAN > 10.x > 172.x > Tailscale (100.x). Comma-joined."""
    import socket
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        if not s.getsockname()[0].startswith("127."):
            ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = i[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    def score(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            return 2
        if ip.startswith("100."):
            return 3  # Tailscale - works anywhere if the phone runs Tailscale too
        return 4
    return ",".join(sorted(ips, key=score))

def _type_text(txt):
    import subprocess, pyautogui
    try:
        # clipboard + paste: handles unicode that pyautogui.write can't
        ps = "Set-Clipboard -Value '" + txt.replace("'", "''") + "'"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pyautogui.hotkey("ctrl", "v")
        return
    except Exception:
        pass
    try:
        pyautogui.write(txt, interval=0.02)
    except Exception:
        pass

def _start_monitor_server():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import json as _json
    import urllib.parse as _up
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except Exception:
        pyautogui = None
    try:
        from mss import mss as _mss
        with _mss() as _s:
            MON["w"], MON["h"] = _s.monitors[1]["width"], _s.monitors[1]["height"]
            MON["left"], MON["top"] = _s.monitors[1]["left"], _s.monitors[1]["top"]
    except Exception:
        MON["left"], MON["top"] = 0, 0

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, obj, code=200):
            b = _json.dumps(obj).encode()
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_OPTIONS(self):
            self.send_response(200)
            self._cors()
            self.end_headers()

        def do_GET(self):
            try:
                u = _up.urlparse(self.path)
                if u.path == "/info":
                    self._json({"w": MON["w"], "h": MON["h"], "agent": "utos-monitor"})
                    return
                if u.path == "/windows":
                    self._json({"windows": _windows_list()})
                    return
                if u.path == "/frame":
                    qs = _up.parse_qs(u.query)
                    try:
                        w = max(320, min(1600, int(qs.get("w", ["960"])[0])))
                    except Exception:
                        w = 960
                    try:
                        q = max(20, min(85, int(qs.get("q", ["55"])[0])))
                    except Exception:
                        q = 55
                    # extend mode: the window's OWN pixels (even when covered) -
                    # the PC screen is left alone entirely
                    region = {"left": MON.get("left", 0), "top": MON.get("top", 0),
                              "width": MON["w"], "height": MON["h"]}
                    wid = (qs.get("wid", [""])[0] or "").strip()
                    if wid:
                        _PARK_SEEN[wid] = time.time()
                    img = None
                    if wid:
                        img = _grab_window(wid)
                        if img is None:
                            wr = _window_rect(wid)
                            if wr and wr["width"] > 40 and wr["height"] > 40:
                                region = wr
                    from mss import mss
                    from PIL import Image, ImageDraw
                    if img is None:
                        with mss() as sct:
                            shot = sct.grab(region)
                            img = Image.frombytes("RGB", shot.size, shot.rgb)
                    if img.width > w:
                        img = img.resize((w, int(img.height * w / img.width)), Image.BILINEAR)
                    if pyautogui and img is not None and not wid:
                        try:
                            r = img.width / float(region["width"])
                            px, py = pyautogui.position()
                            cx = int((px - region["left"]) * r)
                            cy = int((py - region["top"]) * r)
                            if 0 <= cx < img.width and 0 <= cy < img.height:
                                ImageDraw.Draw(img).ellipse((cx - 7, cy - 7, cx + 7, cy + 7),
                                                            outline=(0, 255, 136), width=3)
                        except Exception:
                            pass
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=q)
                    b = buf.getvalue()
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                    return
                self._json({"err": "unknown"}, 404)
            except Exception as e:
                try:
                    self._json({"err": str(e)}, 500)
                except Exception:
                    pass

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                try:
                    d = _json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    d = {}
                path = _up.urlparse(self.path).path
                if path == "/touch":
                    wid = str(d.get("wid", "")).strip()
                    if wid and _win_touch(wid, d):
                        self._json({"ok": True, "win": True})
                        return
                    nx = max(0.0, min(1.0, float(d.get("x", 0))))
                    ny = max(0.0, min(1.0, float(d.get("y", 0))))
                    px, py = int(nx * (MON["w"] - 1)), int(ny * (MON["h"] - 1))
                    act = d.get("action", "click")
                    if pyautogui:
                        if act == "move":
                            pyautogui.moveTo(px, py)
                        elif act == "down":
                            pyautogui.moveTo(px, py)
                            pyautogui.mouseDown()
                        elif act == "up":
                            pyautogui.moveTo(px, py)
                            pyautogui.mouseUp()
                        elif act == "right":
                            pyautogui.rightClick(px, py)
                        elif act == "double":
                            pyautogui.doubleClick(px, py)
                        else:
                            pyautogui.click(px, py)
                    self._json({"ok": True})
                    return
                if path == "/scroll":
                    wid = str(d.get("wid", "")).strip()
                    dy = int(d.get("dy", 0))
                    if wid and _win_scroll(wid, dy):
                        self._json({"ok": True, "win": True})
                        return
                    if pyautogui:
                        pyautogui.scroll(max(-10, min(10, int(dy / 40))))
                    self._json({"ok": True})
                    return
                if path == "/key":
                    wid = str(d.get("wid", "").strip() if d.get("wid") else "")
                    k = str(d.get("key", ""))
                    txt = str(d.get("text", ""))
                    # plain keys/typing go into the Extend window (no focus steal);
                    # combos like alt+tab are system-level -> global path
                    if wid and not ("+" in k):
                        if _win_key(wid, k, txt):
                            self._json({"ok": True, "win": True})
                            return
                    if pyautogui:
                        if k:
                            if "+" in k:
                                pyautogui.hotkey(*k.split("+"))
                            else:
                                pyautogui.press(k)
                        if txt:
                            _type_text(txt)
                    self._json({"ok": True})
                    return
                if path == "/display":
                    m = str(d.get("mode", "on"))
                    if m == "privacy":
                        PRIV["on"] = True
                        PRIV["at"] = time.time()
                        _mon_power(False)
                    elif m == "raise":
                        _window_raise(str(d.get("wid", "")))
                    elif m == "park":
                        ok = _win_park(str(d.get("wid", "")))
                        self._json({"ok": ok})
                        return
                    elif m == "unpark":
                        ok = _win_unpark(str(d.get("wid", "")))
                        self._json({"ok": ok})
                        return
                    else:
                        PRIV["on"] = False
                        if m == "on":
                            _mon_power(True)
                    self._json({"ok": True})
                    return
                self._json({"err": "unknown"}, 404)
            except Exception as e:
                try:
                    self._json({"err": str(e)}, 500)
                except Exception:
                    pass

    srv = ThreadingHTTPServer(("0.0.0.0", MON["port"]), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    threading.Thread(target=_park_watchdog, daemon=True).start()
    print(f"[UTOS] monitor server on :{MON['port']} ({MON['w']}x{MON['h']})")
    return srv

def _start_tunnel():
    """cloudflared quick tunnel = public https URL so the phone can mirror on mobile data. No signup."""
    import re
    import subprocess
    import urllib.request
    exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudflared.exe")
    if not os.path.exists(exe):
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        print("[UTOS] downloading cloudflared (one time)...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "UTOS"})
            with urllib.request.urlopen(req, timeout=600) as r, open(exe + ".tmp", "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(exe + ".tmp", exe)
            print("[UTOS] cloudflared ready")
        except Exception as e:
            print("[UTOS] cloudflared download failed:", e)
            return
    try:
        p = subprocess.Popen([exe, "tunnel", "--url", f"http://127.0.0.1:{MON['port']}", "--no-autoupdate"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        print("[UTOS] tunnel spawn failed:", e)
        return
    for raw in p.stdout:
        try:
            line = raw.decode("utf-8", "ignore")
        except Exception:
            continue
        m = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
        if m and m.group(1) != MON["tunnel"]:
            MON["tunnel"] = m.group(1)
            print("[UTOS] tunnel up:", m.group(1))
        elif "ERR" in line and not MON["tunnel"]:
            print("[UTOS] tunnel:", line.strip()[:200])

def start_monitor():
    MON["lan"] = _lan_ip()
    try:
        threading.Thread(target=_start_monitor_server, daemon=True).start()
    except Exception as e:
        print("[UTOS] monitor server failed:", e)
    threading.Thread(target=_privacy_loop, daemon=True).start()
    threading.Thread(target=_start_tunnel, daemon=True).start()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", default="http://127.0.0.1:5001")
    ap.add_argument("--user", default="solo")
    a = ap.parse_args()
    cloud = a.cloud.rstrip("/")
    user = a.user
    _park_restore_all()   # crash safety: windows parked off-screen come home
    start_monitor()
    print(f"[UTOS] polling {cloud} as user={user}")
    print("[UTOS] v7 personas+memory+follow (if you don't see v7, you run old file)")
    while True:
        try:
            requests.post(f"{cloud}/api/utos/heartbeat",
                          json={"user_id": user, "lan": MON["lan"], "tunnel": MON["tunnel"],
                                "w": MON["w"], "h": MON["h"], "mon": MON["port"]},
                          timeout=8)
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
