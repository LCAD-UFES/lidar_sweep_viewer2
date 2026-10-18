import json, time
from collections.abc import Collection
from dataclasses import asdict, dataclass
from typing import cast
from .config import (Job, FRAMES_PER_SEGMENT_GUESS, INITIAL_THROUGHPUT, INITIAL_SECONDS_PER_SEGMENT,
                     INITIAL_WORKER_BYTES, INITIAL_BYTES_PER_CLIP)
from .source import make_source, available
from .jsonio import from_dict

MB = 1e6

@dataclass
class Segment:
    id: str
    object: str          # provenance string from the source (e.g. gs://bucket/path)
    size: int
    frames: int | None   # None when the source cannot count without fetching
    clips: int
    cached: bool
    download_seconds: float = 0.0   # filled by the runner

@dataclass
class Calibration:
    calibrated: bool
    throughput: float          # B/s
    seconds_per_segment: float
    worker_bytes: float        # peak RSS of one worker
    bytes_per_clip: float

@dataclass
class Plan:
    job: Job
    segments: list[Segment]
    calibration: Calibration
    created: float

@dataclass
class Measurement:
    size: int
    download_seconds: float   # 0 when the segment was already cached
    process_seconds: float
    max_rss: int
    clip_bytes: list[int]

@dataclass
class Estimate:
    segments: int
    to_download: int
    download_bytes: int
    fit_in_cache: int
    workers: int
    clips: int
    output_bytes: float
    t_download: float
    t_process: float
    t_total: float
    bound: str

def make_plan(job: Job) -> Plan:
    src = make_source(job.source); segments: list[Segment] = []
    for sid in job.segments:
        obj, size = src.resolve(sid)
        frames = src.frames(obj)
        clips = (frames if frames is not None else FRAMES_PER_SEGMENT_GUESS) // job.clip_frames
        segments.append(Segment(sid, obj, size, frames, clips, available(job.cache_dir, sid, size)))
    too_big = [s.id for s in segments if s.size > job.cache_budget_bytes]
    if too_big: raise ValueError(f"cache_budget_bytes smaller than a single segment: {too_big}")
    cal = Calibration(False, INITIAL_THROUGHPUT, INITIAL_SECONDS_PER_SEGMENT, INITIAL_WORKER_BYTES, INITIAL_BYTES_PER_CLIP[job.profile])
    return Plan(job, segments, cal, time.time())

def effective_workers(job: Job, cal: Calibration) -> int:
    by_memory = int(job.memory_budget_bytes // cal.worker_bytes) if job.memory_budget_bytes else job.cpu_workers
    return max(1, min(job.cpu_workers, by_memory))

def estimate(plan: Plan, skip: Collection[str] = ()) -> Estimate:
    job, cal = plan.job, plan.calibration
    segs = [s for s in plan.segments if s.id not in skip]
    to_download = [s for s in segs if not s.cached]
    workers = effective_workers(job, cal)
    download_bytes = sum(s.size for s in to_download)
    t_download = download_bytes / cal.throughput / job.download_parallel
    t_process = len(segs) * cal.seconds_per_segment / workers
    first = to_download[0].size / cal.throughput if to_download else 0.0
    clips = sum(s.clips for s in segs)
    fits, used = 0, 0
    for s in to_download:
        if used + s.size > job.cache_budget_bytes: break
        used += s.size; fits += 1
    return Estimate(len(segs), len(to_download), download_bytes, fits, workers, clips, clips * cal.bytes_per_clip,
                    t_download, t_process, max(t_download + cal.seconds_per_segment, t_process + first),
                    "download" if t_download >= t_process else "processing")

def calibrate(plan: Plan, measurements: list[Measurement]) -> Plan:
    downloaded = [m for m in measurements if m.download_seconds > 0]
    cal = plan.calibration
    if downloaded: cal.throughput = sum(m.size for m in downloaded) / sum(m.download_seconds for m in downloaded)
    cal.seconds_per_segment = sum(m.process_seconds for m in measurements) / len(measurements)
    cal.worker_bytes = float(max(m.max_rss for m in measurements))
    clips = [b for m in measurements for b in m.clip_bytes]
    if clips: cal.bytes_per_clip = sum(clips) / len(clips)
    cal.calibrated = True
    return plan

def format_plan(plan: Plan, skip: Collection[str] = ()) -> str:
    job, e, cal = plan.job, estimate(plan, skip), plan.calibration
    tag = "calibrated" if cal.calibrated else "UNCALIBRATED (initial guesses; re-printed after the first segment)"
    lines = [f"lsv2 plan: {e.segments} segments, profile {job.profile}, output {job.output_dir}", ""]
    lines.append(f"{'segment':42s} {'size MB':>8s} {'frames':>6s} {'clips':>5s}  status")
    for s in plan.segments:
        status = "done" if s.id in skip else "cached" if s.cached else "download"
        lines.append(f"{s.id:42s} {s.size/MB:8.1f} {s.frames if s.frames is not None else '?':>6} {s.clips:5d}  {status}")
    lines += ["",
              f"cache: {job.cache_dir}  budget {job.cache_budget_bytes/MB:.0f} MB  ->  {e.fit_in_cache} of {e.to_download} downloads fit at once",
              f"download: {e.download_bytes/MB:.0f} MB at {cal.throughput/MB:.1f} MB/s x{job.download_parallel}  ->  {e.t_download/60:.1f} min",
              f"processing: {e.workers} worker(s) ({job.cpu_workers} cpu, memory budget {job.memory_budget_bytes/MB:.0f} MB, {cal.worker_bytes/MB:.0f} MB each) at {cal.seconds_per_segment:.1f} s/segment  ->  {e.t_process/60:.1f} min",
              f"output: {e.clips} clips of {job.clip_frames} frames at {job.fps} fps, ~{e.output_bytes/MB:.0f} MB at {cal.bytes_per_clip/1e3:.0f} kB/clip",
              f"total: ~{e.t_total/60:.1f} min, {e.bound}-bound  [{tag}]"]
    return "\n".join(lines)

def save_plan(plan: Plan, path: str) -> None:
    with open(path, "w") as f: json.dump(asdict(plan), f, indent=1)

def load_plan(path: str) -> Plan:
    with open(path) as f: return from_dict(Plan, cast(object, json.load(f)), path)
