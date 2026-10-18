import json, os
from dataclasses import dataclass
from typing import cast
from .encoder import PROFILES
from .jsonio import from_dict

METERS, LEVELS = 75.0, 256           # lsv1 utils.cpp::normalizar(meters=75) on 8-bit grey: the render contract, not a job option
RI_HEIGHT, RI_WIDTH = 64, 2650       # Waymo TOP lidar range image (dataset.proto RangeImage)
TOP_LASER, LASERS_PER_FRAME = 1, 5   # dataset.proto LaserName: TOP=1 of 5 lasers, one parquet row each per frame
FRAMES_PER_SEGMENT_GUESS = 198       # ~20 s at 10 Hz; used only when the source cannot count frames
INITIAL_THROUGHPUT = 10.5e6          # B/s, a typical home link; replaced by calibration after the first segment
INITIAL_SECONDS_PER_SEGMENT = 10.0   # guess; replaced by calibration
INITIAL_WORKER_BYTES = float(1 << 30)   # conservative; replaced by measured max RSS
INITIAL_BYTES_PER_CLIP: dict[str, float] = {"lossless": 300e3, "lsv1-compat": 100e3}   # order of magnitude; replaced by calibration

@dataclass
class Job:
    segments: list[str]
    cache_dir: str
    cache_budget_bytes: int
    output_dir: str
    source: dict[str, str]
    cpu_workers: int = 1
    memory_budget_bytes: int = 0
    gpu_budget: int = 0
    profile: str = "lossless"
    verify_lossless: bool = True
    download_parallel: int = 1
    clip_frames: int = 22            # lsv1 reference dataset: 22-frame clips
    fps: int = 10                    # lsv1 reference dataset: 10 fps, the Waymo lidar sweep rate
    prefix: str = ""                 # video name prefix, e.g. "train" -> train_<segment>_<clip>.mp4; lets slices share an output_dir

def _abspath(p: str, base: str) -> str: return os.path.abspath(os.path.join(base, os.path.expanduser(os.path.expandvars(p))))   # relative to the job file

def load_job(path: str) -> Job:
    with open(path) as f: raw = cast(object, json.load(f))
    if not isinstance(raw, dict): raise ValueError(f"{path}: the job file must hold a JSON object")
    raw = cast(dict[object, object], raw)
    base = os.path.dirname(os.path.abspath(path))
    segments = raw.get("segments")
    if isinstance(segments, str):
        with open(_abspath(segments, base)) as f: raw["segments"] = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    job = from_dict(Job, raw, path)
    job.cache_dir, job.output_dir = _abspath(job.cache_dir, base), _abspath(job.output_dir, base)
    if "credentials" in job.source: job.source["credentials"] = _abspath(job.source["credentials"], base)
    if job.gpu_budget != 0: raise ValueError("gpu_budget must be 0: no stage uses a GPU")
    if job.profile not in PROFILES: raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    if job.cpu_workers < 1 or job.download_parallel < 1: raise ValueError("cpu_workers and download_parallel must be >= 1")
    if job.clip_frames < 1 or job.fps < 1: raise ValueError("clip_frames and fps must be >= 1")
    if "/" in job.prefix or " " in job.prefix: raise ValueError("prefix must not contain '/' or spaces")
    if not job.segments: raise ValueError("segments is empty")
    if len(set(job.segments)) != len(job.segments): raise ValueError("segments has duplicates")
    return job
