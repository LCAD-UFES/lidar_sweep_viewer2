import json, os, time

# one JSON per segment under <output_dir>/state/; status: listed -> downloading -> downloaded -> processing -> done | failed
def _path(output_dir, sid): return os.path.join(output_dir, "state", f"{sid}.json")

def load(output_dir, sid):
    p = _path(output_dir, sid)
    if not os.path.exists(p): return {"id": sid, "status": "listed"}
    with open(p) as f: return json.load(f)

def save(output_dir, st):
    p = _path(output_dir, st["id"]); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w") as f: json.dump(st, f, indent=1)
    os.replace(p + ".tmp", p)

def update(output_dir, sid, **fields):
    st = load(output_dir, sid); st.update(fields, updated=time.time()); save(output_dir, st)
    return st
