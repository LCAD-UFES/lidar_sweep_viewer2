# lidar_sweep_viewer2: design record

Frozen on 2026-10-17, built on 2026-10-18. Scope changes are accepted only if they are corrective (the design is incoherent or infeasible at that point) and make delivery faster, or if they are very quick to implement and bring a substantive gain. Everything else is deferred. Changes accepted after the freeze are marked with their date.

## Goal

Produce the MAE-ST video dataset from Waymo Open Dataset segments, reproducibly, on any Linux machine with user-space installs only, replacing the first-generation pipeline `LCAD-UFES/lidar_sweep_viewer` ("lsv1"). The lsv1 repository is not modified; it is the historical reference. Its vendored `sapiens/` directory belongs to an earlier, unrelated experiment and is out of scope.

## Inputs: one JSON job file

All inputs live in a single JSON file the user writes; nothing is passed as loose CLI flags except file paths. Keys:

- `segments`: list of Waymo segment ids (provenance), or a path to a text file with one id per line
- `cache_dir`, `cache_budget_bytes`: the dataset entry point (may already hold segments) and the cap on what the pipeline downloads into it
- `source`: `{"type": "gcs", "bucket": ..., "component": ..., "credentials": "<path to a credentials json>"}`; other types plug in later. Credentials are always user-supplied; the tool never logs in
- `cpu_workers`, `memory_budget_bytes`, `gpu_budget` (must be 0; anything else is an error)
- `output_dir`: one flat folder of videos
- `profile`: `lossless` (default) or `lsv1-compat`
- `verify_lossless`: default true; decode every lossless clip back and assert bit-exactness
- `download_parallel`: default 1 (a single stream already saturates a typical home link)
- `clip_frames`, `fps` (added 2026-10-18 by request): defaults 22 and 10; the compat profile's keyint follows the clip length
- `prefix` (added 2026-10-18 by request): video name prefix so disjoint slices (train/val/test) can share one `output_dir`; `index.csv` is rebuilt from every state file in the dir

The package is `lsv2`; the CLI entry point is `lsv2`.

## Segment source (pluggable)

The pipeline never owns authentication or knows how segments arrive. The cache dir is the single entry point: a segment present and complete in the cache is ready, whatever put it there. Acquisition is a source module with a small interface used by the planner and the runner:

- `resolve(segment_id) -> (object, size)`: a provenance string and the exact byte size, used by `plan` for cache fitting and estimates
- `fetch(object, dst)`: makes the file complete in the cache, atomically
- `frames(object)`: optional; frame count without fetching, for exact clip counts in the plan

First and only module: runtime download from the Waymo GCS bucket, using a credentials file the user provides. The module boundary is designed so that future sources (local mirror, offline cache-only, other storage) plug in without touching planner, workers or encoder. Files already in the cache with the right size are used and never deleted; only files the pipeline fetched are deleted after processing.

## Commands

- `lsv2 plan job.json [-o plan.json]`: resolves each segment at the source (object, exact size, frame count), computes how many fit the cache, estimated output size and time. Time estimates are marked uncalibrated (initial throughput 10.5 MB/s, initial seconds per segment a guess) and the plan states plainly which resource bounds the run. Writes `plan.json`: the resolved job plus the per-segment table. Nothing is downloaded.
- `lsv2 run plan.json [--yes]`: prints the plan, asks for confirmation once (skipped by `--yes`), executes. After the first segment completes it re-prints the plan calibrated with measured throughput, processing time, peak worker memory and bytes per clip, and continues without a second confirmation. Resumable: per-segment state on disk; done segments are skipped on restart.

No split of any kind: lsv2 converts point clouds to grey images to MP4 and stops. A split is one job per slice with disjoint segments and a distinguishing prefix. The `training/validation/testing` folders of the Waymo bucket are only where the source finds a file; the resolved object path is recorded as provenance and means nothing else.

## Pipeline per segment (unit of work)

1. download the segment into the cache (first segment alone, then overlapped with processing; a download starts only when its exact size fits the free cache budget)
2. read the TOP lidar range image, first return, range channel, float32, for every frame
3. render uint8 grey: `r < 0 -> 0`, else `trunc(255 - r * 256 / 75)`, clamped to [0, 255] (provenance: lsv1 `utils.cpp::normalizar`, `meters = 75`; the constant is computed in code)
4. encode clips of `clip_frames` frames at `fps`, 2650x64; drop the trailing partial clip
   - `lossless`: H.264 `-qp 0 -pix_fmt gray` (bit-exact through PyAV, verified per clip)
   - `lsv1-compat`: libx264 `-crf 23 -g <clip_frames> -pix_fmt yuv420p` with the grey values kept raw in luma (see "Encoding facts")
   - the encoder is written here; no external script is a dependency
5. delete the segment from the cache if the pipeline fetched it, which frees budget for the next download
6. append to `index.csv` in the output dir: video file, segment id, source object path, clip index, first and last `timestamp_micros`, profile, verified flag; videos are named `[<prefix>_]<segment_id>_<clip:03d>.mp4`

Out of scope: `train.csv`/`val.csv`/`test.csv`. That is the ML side's job (`LCAD-UFES/mae_st_lcad` builds its csvs in the `absolute_path label` format from a folder of videos). The output contract is a flat folder of videos plus the provenance index.

## Data source decision (resolved 2026-10-17)

Perception v2 parquet, `lidar` component per segment: `gs://waymo_open_dataset_v_2_0_1/<folder>/lidar/<id>.parquet`. Verified on segment `17993467596234560701_4940_000_4960_000`: rendering `range_image_return1[..., 0]` of `key.laser_name == 1` (TOP) with the lsv1 formula reproduces 16 lsv1 sample frames bit-exact. Facts measured on that file: 198 frames x 5 lasers = 990 rows, shape (64, 2650, 4), no-return value is exactly -1 (never -2), range max 74.995. Parquet reading needs pyarrow only (no pandas, no TensorFlow), so the pipeline is portable to aarch64. The v1 tfrecord fallback is dropped. Sizes: v2 lidar 134-191 MB per segment vs v1 800-1265 MB. Measured GCS throughput on a home link: ~10.5 MB/s, so ~17 s per segment.

lsv1 sample convention: `<id>_<k>.png` holds frames `16k .. 16k+15` stacked top to bottom, 64 rows each, pure grey. Source segment of the lsv1 reference videos (checked 2026-10-18): of the 8 sample segments the two with 199 frames were rendered and compared against frame 0 of the first reference video in every orientation; mean error 52-65 grey levels, i.e. a different scene. The source segment is not among the sample segments and the per-frame reproduction check is therefore not possible; documented in the README.

## Encoding facts (measured 2026-10-18)

The lsv1 reference mp4s store the grey values raw in luma (Y 0..245) with no range flag; ffmpeg 9 squeezes gray to 16..235 when converting to yuv420p unless told otherwise, so `lsv1-compat` is `scale=in_range=full:out_range=full,setrange=limited` + `-crf 23 -g <clip_frames>`, which gives the same x264 settings (keyint = clip length, bframes 3, ref 3), the same flags, MAE 2.9 vs source (crf noise) and ~770 kB per 22-frame clip like the reference. `setrange=unspecified` triggers the squeeze again. `lossless` is `-qp 0 -pix_fmt gray`: bit-exact through PyAV, including its rgb24 conversion (R=G=B=Y exactly), ~1.2 MB per clip. The lsv1 files, through PyAV rgb24, come out range-expanded by up to 20 levels: that is what MAE-ST actually trained on with lsv1 data.

Measured on the first end-to-end run (8 segments, 71 clips, 1 min 28 s): 7.7 s per segment of processing, ~600 MB peak per worker, 10.5 MB/s download. Download-bound, as predicted; one or two workers suffice.

Toolchain (all conda-forge, pinned in `_install/deps.linux-x86_64.tsv`): python 3.14, google-cloud-sdk, google-cloud-storage, pyarrow, numpy, pillow (tests only), ffmpeg 9 (gpl build, libx264), av, tmux, pyinstaller (bundle only). Credentials: a user ADC file from `gcloud auth application-default login`, consumed by `google-cloud-storage`; the client is created with a placeholder project because user ADC carries none.

## Validation (acceptance)

- unit test of the render formula on synthetic ranges (`tests/test_render.py`)
- encoder round trip: lossless bit-exact, compat keeps full range (`tests/test_encoder.py`)
- oracle: lsv1 sample PNGs against the v2 render, bit-exact (`tests/test_oracle.py`, needs the sample files)
- empirical checks on the first real segment: invalid-pixel value, 64x2650 grid, orientation
- reproduction check against the lsv1 reference videos: not possible, their source segment is unknown
- first-run job: the 8 sample segments (`jobs/segments.txt`), the only ones with lsv1 output to compare against

## Deliverable

- pipeline package + CLI (`plan`, `run`), with the segment source as a separate module
- manifest-driven installer (same pattern as `_install/conda.sh` + `deps.<host>.tsv` in `LCAD-UFES/mae_st_lcad`, branch `installer`); the primary install path, also for aarch64
- a self-contained x86_64 executable (PyInstaller bundle with ffmpeg inside), built last, time-boxed; the user still supplies credentials (gcloud is not bundled). Built and verified on 2026-10-18: 191 MB, runs with no PATH, same clips as the environment install
- the segment list used for the first dataset (`jobs/segments.txt`) and a shipped example job (`jobs/example.json`)
- README (user manual) and CONTRIBUTING (code map, source interface, provenance and validation)

## Build-day order (as executed)

1. recon; identify the reference-video segment among the two 199-frame candidates (not found)
2. reader + render as package modules, unit test of the formula, oracle check from the package
3. encoder, both profiles, settled by measurement on real frames; provenance index
4. orchestrator (cache byte budget, worker pool, state, resume); `plan`
5. end-to-end runs on the 8 sample segments, both profiles; README; installer; bundle
