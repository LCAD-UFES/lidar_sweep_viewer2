import json, os, time
from dataclasses import asdict, dataclass, field, replace
from typing import cast
from .jsonio import from_dict

IndexRow = list[str | int]   # one index.csv row: video, segment, source, clip, first_ts, last_ts, profile, verified

# one JSON per segment under <output_dir>/state/; status: listed -> downloading -> downloaded -> processing -> done | failed
@dataclass
class State:
    id: str
    status: str = "listed"
    object: str = ""
    size: int = 0
    downloaded_by_pipeline: bool = False
    updated: float = 0.0
    download_seconds: float = 0.0
    frames: int = 0
    clips: int = 0
    dropped_frames: int = 0
    process_seconds: float = 0.0
    max_rss: int = 0
    clip_bytes: list[int] = field(default_factory=list)
    rows: list[IndexRow] = field(default_factory=list)
    error: str = ""

def _path(output_dir: str, sid: str) -> str: return os.path.join(output_dir, "state", f"{sid}.json")

def load(output_dir: str, sid: str) -> State:
    p = _path(output_dir, sid)
    if not os.path.exists(p): return State(id=sid)
    with open(p) as f: return from_dict(State, cast(object, json.load(f)), p)

def save(output_dir: str, st: State) -> None:
    p = _path(output_dir, st.id); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w") as f: json.dump(asdict(st), f, indent=1)
    os.replace(p + ".tmp", p)

def update(output_dir: str, sid: str, **changes: object) -> State:
    st = replace(load(output_dir, sid), updated=time.time(), **changes)
    save(output_dir, st)
    return st
