import csv, glob, json, os, resource, time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait, FIRST_COMPLETED
import numpy as np
from . import state
from .source import make_source, cache_path, available
from .reader import top_range_frames
from .render import render
from .encoder import encode, decode
from .planner import effective_workers, calibrate, format_plan

INDEX_HEADER = ["video", "segment", "source", "clip", "first_timestamp_micros", "last_timestamp_micros", "profile", "verified"]

def process_segment(sid, obj, path, output_dir, profile, verify, clip_frames, fps, prefix):
    # worker process: parquet -> clips of clip_frames; the trailing partial clip is dropped (DESIGN.md)
    t0 = time.time()
    frames = [(ts, render(r)) for ts, r in top_range_frames(path)]
    n_clips, rows, clip_bytes = len(frames) // clip_frames, [], []
    for c in range(n_clips):
        chunk = frames[c * clip_frames:(c + 1) * clip_frames]
        name, arr = "_".join(filter(None, [prefix, sid, f"{c:03d}"])) + ".mp4", np.stack([f for _, f in chunk])
        clip_bytes.append(encode(arr, os.path.join(output_dir, name), profile, fps))
        verified = ""
        if profile == "lossless" and verify:
            if not np.array_equal(decode(os.path.join(output_dir, name)), arr): raise RuntimeError(f"{name}: lossless round trip is not bit-exact")
            verified = "yes"
        rows.append([name, sid, obj, c, chunk[0][0], chunk[-1][0], profile, verified])
    return {"frames": len(frames), "clips": n_clips, "dropped_frames": len(frames) - n_clips * clip_frames, "rows": rows,
            "process_seconds": time.time() - t0, "max_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, "clip_bytes": clip_bytes}

def download(src, obj, dst):
    t0 = time.time(); src.fetch(obj, dst)
    return time.time() - t0

def write_index(output_dir):
    # every state file in the dir, not only this plan's: slices with different prefixes may share an output_dir
    rows = []
    for p in sorted(glob.glob(os.path.join(output_dir, "state", "*.json"))):
        with open(p) as f: rows += json.load(f).get("rows", [])
    tmp = os.path.join(output_dir, "index.csv.tmp")
    with open(tmp, "w", newline="") as f: w = csv.writer(f); w.writerow(INDEX_HEADER); w.writerows(rows)
    os.replace(tmp, os.path.join(output_dir, "index.csv"))

def run(plan, log=print):
    job, out, cache = plan["job"], plan["job"]["output_dir"], plan["job"]["cache_dir"]
    os.makedirs(out, exist_ok=True); os.makedirs(cache, exist_ok=True)
    os.environ["CUDA_VISIBLE_DEVICES"] = ""   # gpu_budget is 0 by contract: no worker may see a GPU
    src, ids = make_source(job["source"]), [s["id"] for s in plan["segments"]]
    done = {sid for sid in ids if state.load(out, sid)["status"] == "done"}
    ready, to_download = deque(), deque()
    for s in plan["segments"]:
        if s["id"] in done: continue
        st = state.load(out, s["id"])
        if available(cache, s["id"], s["size"]):
            state.update(out, s["id"], status="downloaded", object=s["object"], size=s["size"], downloaded_by_pipeline=st.get("downloaded_by_pipeline", False))
            ready.append(s)
        else: to_download.append(s)
    used, workers, measurements, failed = 0, effective_workers(job, plan["calibration"]), [], []
    stamp = lambda: time.strftime("%H:%M:%S")
    log(f"[{stamp()}] {len(done)} done, {len(ready)} in cache, {len(to_download)} to download; {workers} worker(s)")
    with ThreadPoolExecutor(job["download_parallel"]) as dl, ProcessPoolExecutor(workers) as pp:
        dl_futs, pp_futs = {}, {}
        def start_downloads():
            nonlocal used
            while to_download and len(dl_futs) < job["download_parallel"] and used + to_download[0]["size"] <= job["cache_budget_bytes"]:
                s = to_download.popleft(); used += s["size"]
                state.update(out, s["id"], status="downloading", object=s["object"], size=s["size"], downloaded_by_pipeline=True)
                dl_futs[dl.submit(download, src, s["object"], cache_path(cache, s["id"]))] = s
                log(f"[{stamp()}] download  {s['id']} ({s['size']/1e6:.0f} MB)")
        def start_processing():
            while ready and len(pp_futs) < workers:
                s = ready.popleft(); state.update(out, s["id"], status="processing")
                pp_futs[pp.submit(process_segment, s["id"], s["object"], cache_path(cache, s["id"]), out, job["profile"], job["verify_lossless"], job["clip_frames"], job["fps"], job["prefix"])] = s
                log(f"[{stamp()}] process   {s['id']}")
        start_downloads(); start_processing()
        while dl_futs or pp_futs:
            finished, _ = wait(list(dl_futs) + list(pp_futs), return_when=FIRST_COMPLETED)
            for f in finished:
                if f in dl_futs:
                    s = dl_futs.pop(f)
                    try: s["download_seconds"] = f.result()
                    except Exception as e:
                        used -= s["size"]; failed.append(s["id"]); state.update(out, s["id"], status="failed", error=f"download: {e!r}")
                        log(f"[{stamp()}] FAILED download {s['id']}: {e!r}"); continue
                    state.update(out, s["id"], status="downloaded", download_seconds=s["download_seconds"]); ready.append(s)
                    log(f"[{stamp()}] got       {s['id']} in {s['download_seconds']:.1f} s ({s['size']/1e6/s['download_seconds']:.1f} MB/s)")
                else:
                    s = pp_futs.pop(f)
                    try: r = f.result()
                    except Exception as e:
                        failed.append(s["id"]); state.update(out, s["id"], status="failed", error=f"process: {e!r}")
                        log(f"[{stamp()}] FAILED process {s['id']}: {e!r}"); continue
                    if state.load(out, s["id"]).get("downloaded_by_pipeline"):
                        os.remove(cache_path(cache, s["id"])); used -= s["size"]
                    state.update(out, s["id"], status="done", **r); done.add(s["id"]); write_index(out)
                    measurements.append({"size": s["size"], "download_seconds": s.get("download_seconds"), **r})
                    log(f"[{stamp()}] done      {s['id']}: {r['frames']} frames -> {r['clips']} clips ({r['dropped_frames']} dropped) in {r['process_seconds']:.1f} s")
                    if len(measurements) == 1:
                        calibrate(plan, measurements); log("\n" + format_plan(plan, skip=done) + "\n")
            start_downloads(); start_processing()
    if to_download: raise RuntimeError(f"cache budget could not fit the remaining segments: {[s['id'] for s in to_download]}")
    if failed: raise RuntimeError(f"{len(failed)} segment(s) failed: {failed}")
    log(f"[{stamp()}] all {len(done)} segments done; index at {os.path.join(out, 'index.csv')}")
    return calibrate(plan, measurements) if measurements else plan
