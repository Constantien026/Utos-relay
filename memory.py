"""UTOS memory: facts, taught answers, recent history. Local JSON, no signup.
- remember that <fact> / my name is <X> / forget <word>
- teach: reply to unknown with 'teach: question => answer' NOT needed;
  instead: 'remember that <question> means <answer>' or just 'remember <answer>' right after confusion.
  Simpler rule used by pc_agent: 'remember that X is Y' stores fact X=Y.
  'X means Y' inside a chat message teaches Q&A pair.
"""
import os, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
MEM = os.path.join(HERE, "memory.json")

def _load():
    try:
        with open(MEM, encoding="utf-8") as f:
            d = json.load(f)
            d.setdefault("facts", {})
            d.setdefault("learned", {})
            d.setdefault("history", [])
            return d
    except Exception:
        return {"facts": {}, "learned": {}, "history": []}

def _save(d):
    try:
        with open(MEM, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

def remember_fact(k, v):
    d = _load(); d["facts"][k.lower()] = v; _save(d)

def forget(word):
    d = _load(); n = 0
    for store in ("facts", "learned"):
        for k in [k for k in d[store] if word.lower() in k.lower()]:
            d[store].pop(k, None); n += 1
    _save(d); return n

def teach(q, a):
    d = _load(); d["learned"][q.lower().strip()] = a.strip(); _save(d)

def lookup_learned(q):
    d = _load()
    ql = q.lower().strip()
    if ql in d["learned"]:
        return d["learned"][ql]
    # fuzzy: all words of stored Q present
    for k, v in d["learned"].items():
        words = [w for w in k.split() if len(w) > 3]
        if words and all(w in ql for w in words):
            return v
    return None

def facts_text():
    d = _load()
    if not d["facts"]:
        return ""
    return "Known facts: " + "; ".join(f"{k}={v}" for k, v in d["facts"].items()) + "."

def push_history(who, text):
    d = _load()
    d["history"].append({"who": who, "text": text[:300], "at": int(time.time())})
    d["history"] = d["history"][-12:]
    _save(d)

def set_pending(q):
    d = _load(); d["pending"] = q[:200]; _save(d)

def take_pending():
    d = _load()
    q = d.pop("pending", "")
    _save(d)
    return q

def history_text():
    d = _load()
    return "\n".join(f"{h['who']}: {h['text']}" for h in d["history"][-8:])
