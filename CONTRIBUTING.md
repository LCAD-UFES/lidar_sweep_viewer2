# Contributing to lsv2

`README.md` is the user manual. This file is for people changing the code. `DESIGN.md` is the frozen design the code implements; a change that departs from it needs a reason recorded there.

## Code map

```
lidar_sweep_viewer2/
  pyproject.toml          package metadata; entry point lsv2 = lsv2.cli:main
  lsv2/
    cli.py                argparse: `plan` and `run`
    config.py             Job dataclass (every job key, defaults), domain constants, load_job() with validation
    planner.py            make_plan(), estimate(), calibrate(), format_plan(), save_plan()/load_plan()
    runner.py             run(): the orchestrator; process_segment(): the worker; write_index()
    source/__init__.py    Source interface, cache_path(), available(), make_source() registry
    source/gcs.py         GcsSource: Waymo bucket via google-cloud-storage
    reader.py             top_range_frames(): parquet -> [(timestamp, range float32 [64, 2650])]
    render.py             render(): the lsv1 grey formula
    encoder.py            PROFILES, encode() (raw grey -> ffmpeg -> mp4), decode() (mp4 -> luma), ffmpeg_path()
    state.py              load()/save()/update(): one JSON per segment, atomic
  tests/                  unittest: test_render, test_encoder, test_oracle (needs LSV2_ORACLE_PNG/PARQUET)
  jobs/                   example.json, segments.txt
  _install/               conda.sh + deps.<host>.tsv: manifest-driven installer
  _bundle/                entry.py + build.sh: PyInstaller one-file executable
```

Control and data flow, from the job file to the clips:

```
job.json ──load_job──▶ Job ──make_plan──▶ plan.json
                              │  for each segment id:
                              │    source.resolve(id) -> (object, size)
                              │    source.frames(object) -> frame count
                              │    available(cache_dir, id, size) -> cached?
                              ▼
plan.json ──run──▶ main loop (one thread)
     │   download thread(s): source.fetch(object, cache/<id>.parquet)      bounded by cache_budget_bytes
     │   worker process(es): process_segment(id, cache/<id>.parquet, ...)   bounded by cpu/memory budget
     │        reader.top_range_frames(parquet) ─▶ render.render(range) ─▶ chunks of clip_frames
     │        encoder.encode(chunk, out/<id>_<clip>.mp4, profile, fps) ─▶ [encoder.decode == chunk if lossless]
     │   on worker completion: delete the parquet if the pipeline fetched it; state.update(done, rows=...)
     │                         write_index(out) from all state files; after the first: planner.calibrate() + format_plan()
     ▼
out/<id>_<clip>.mp4, out/index.csv, out/state/<id>.json
```

What depends on what: `cli` -> `config`, `planner`, `runner`; `planner` -> `config`, `source`; `runner` -> `source`, `reader`, `render`, `encoder`, `state`, `planner`; `config` -> `encoder` (profile names); `reader`, `render`, `source/gcs` -> `config` (constants). `encoder`, `state` and the `source` interface import nothing from the package, and `reader`, `render`, `encoder`, `state` do not import each other, so each can be tested alone.

Run the tests with `python -m unittest discover -s tests -v`. The oracle test is the acceptance test for anything touching `reader.py` or `render.py`; the encoder round-trip test is the one for `encoder.py`.

## Adding a segment source

A source is a class in `lsv2/source/` implementing the interface in `lsv2/source/__init__.py`:

| method | contract |
|---|---|
| `resolve(segment_id) -> (object, size)` | `object` is a provenance string naming where the file comes from (it is written to `index.csv`); `size` is the exact byte count. Raise `FileNotFoundError` if the segment does not exist |
| `fetch(object, dst)` | make `dst` complete, atomically: write to `dst + ".part"` and rename. Resumability across runs comes from the pipeline comparing the file size to `size`, so a partial file is simply fetched again |
| `frames(object) -> int or None` | optional; the frame count without fetching, when the source can tell cheaply. `None` makes the planner use an average |

The constructor receives every key of the job's `source` object except `type`, as keyword arguments. Register the class in `make_source` under a new `type` name. Nothing else changes: the planner, the cache budget, the workers and the encoder only see the cache directory and the `(object, size)` pairs. Use `source/gcs.py` as the model; it is 30 lines.

Candidates: a local mirror directory (`resolve` stats the file, `fetch` copies or hard-links); an offline cache-only source (`resolve` stats the cache itself, `fetch` is a no-op, for machines without bucket access); Perception v1 tfrecords (needs a TensorFlow-free reader: the TOP range image is a zlib-compressed `MatrixFloat` inside each `Frame` proto, and the file is ~1 GB per segment).

## Conventions

- Portability is a hard constraint: no machine-specific paths, user names or hostnames in tracked files. Paths come from the job file or environment variables.
- Repository content names no person and no machine; the first-generation pipeline is "lsv1".
- Installers are manifest-driven: a new machine gets a new `_install/deps.<host>.tsv`, never an edited `conda.sh`.
- Comments record provenance of formulas and constants, not what the code does. Domain constants are computed (`75 * 100 / 256`), not pasted.
- README paragraphs are single lines; line breaks separate paragraphs only.

## Provenance and validation

lsv1 (`LCAD-UFES/lidar_sweep_viewer`) did in three steps what `lsv2` does in one:

1. `utilities/save_waymo_perception_data.py` (Waymo Perception v1 tfrecord, TensorFlow) converted the TOP range image to xyz points and wrote them back as a `.bin` per frame whose 4th float is, despite the comment, the range. The mask `range != -2` removes nothing, so all 64x2650 points stay in grid order; both quirks are load-bearing for the next step.
2. `show_point_cloud` (C++, OpenCV) reshaped those points back into the 64x2650 grid and wrote a PNG with `utils.cpp::normalizar`: `value = trunc(255 - range * 100 / resolution)`, `resolution = 75 * 100 / 256`, clamped to [0, 255], `range < 0` (no return) -> 0. It only wrote PNGs while showing a window, and its build depends on a lab-specific stack.
3. PNG -> mp4: no code exists in any repository. Forensics of the lsv1 reference videos gave the settings of the `lsv1-compat` profile: H.264 High, yuv420p, crf 23, keyint equal to the clip length, bframes 3, ref 3, 10 fps, grey values raw in luma, no range flag (ffmpeg 4.2, x264 core 155).

`lsv2` reads the range channel of the first return of the TOP laser from the Perception v2 parquet `lidar` component (`[LiDARComponent].range_image_return1`, `key.laser_name == 1`) with pyarrow, applies the same formula in float32 with truncation, and encodes. Verified on 2026-10-17/18:

- the render is bit-exact against the only lsv1 output available, a sample of PNGs of 16 stacked 64-row frames named `<segment>_<n>.png` holding frames `16n..16n+15` of 8 segments (`tests/test_oracle.py`);
- no-return pixels are exactly `-1` in the v2 data (never `-2`); the v2 range image is 64x2650x4; a segment has 196-199 frames;
- `lossless` decodes bit-exact through PyAV, including its `rgb24` conversion; `lsv1-compat` reproduces the reference files' flags and x264 settings, with a mean error of ~3 grey levels against the source (crf noise) and the same ~0.77 MB per clip;
- the source segment of the lsv1 reference videos (199 frames from one segment) is not among the 8 sample segments: both 199-frame candidates were rendered and compared in every orientation and are a different scene. The per-frame reproduction check against those videos could therefore not be run.

The lsv1 repository also vendors a copy of Meta's Sapiens. It belongs to an earlier experiment (a single-image MAE trained on the same stacked PNGs, hence the 2650x1024 sample images) and has nothing to do with this pipeline.
