# lidar_sweep_viewer2 (`lsv2`)

Converts Waymo Open Dataset lidar sweeps into the video dataset that `LCAD-UFES/mae_st_lcad` trains on: each 20 s segment becomes short greyscale H.264 clips (by default 22 frames at 10 fps, 2650x64) of the TOP lidar range image. It reproduces, bit-exact, the range images that the first-generation pipeline `LCAD-UFES/lidar_sweep_viewer` ("lsv1") produced, and it replaces that pipeline. `CONTRIBUTING.md` covers the internals; `DESIGN.md` is the design record.

## What you need

- Linux x86_64 or aarch64, no sudo. Everything installs into a conda environment, or runs from the self-contained executable.
- Access to the input segments through one of the sources in "Input datasets". Today that means a Google account that has accepted the Waymo Open Dataset license (https://waymo.com/open) and the credentials file it produces.
- Disk for the cache: one segment is 150-190 MB in the format `lsv2` reads; the budget you set bounds the total.

## Install

```sh
cd lidar_sweep_viewer2/_install
./conda.sh deps.linux-x86_64.tsv     # menu; --dry-run prints every command, --yes installs directly
conda activate lsv2
```

`_install/conda.sh` contains no package list: it reads a manifest, `_install/deps.<host>.tsv`, which pins every package and says why. A new machine gets a new manifest (copy `deps.linux-x86_64.tsv`, edit the `#!target` line and the rows that differ), never an edited script. `_install/README.md` explains the manifest.

Developer install into an existing environment that already has ffmpeg (libx264), numpy, pyarrow, av and google-cloud-storage:

```sh
pip install -e .
python -m unittest discover -s tests -v
```

### Self-contained executable

`_bundle/build.sh` builds a single ~190 MB file, `dist/lsv2`, with Python, every library and `ffmpeg` inside (PyInstaller; `pyinstaller` is an optional row of the manifest). It runs on the platform it was built on with no conda, no PATH and no installation, and it produces the same clips as the environment install. Credentials are still yours to supply.

# Input datasets

`lsv2` does not know where segments come from. Between the job file and the processing pipeline sits a *source*: a module that answers three questions for a segment id, "where is it and how big is it", "is it in the cache", and optionally "how many frames does it have". Everything downstream (planning, the cache budget, the workers, the encoder) only ever sees the cache directory: a segment file that is complete there is ready to process, whatever put it there. This is what makes sources interchangeable. The job's `source.type` selects the module, and the rest of `source` is that module's own configuration.

`plan` uses the source to resolve every segment before anything is downloaded, which is how it reports exact byte sizes, frame counts and cache fitting. `run` uses it to fetch segments into the cache, one at a time by default, as the budget allows. A source never writes outside the cache directory and never deletes anything; deletion is the pipeline's decision, and it only deletes files it fetched itself.

One source exists today, `gcs`. Others (a local mirror, an offline cache-only mode, Perception v1 tfrecords) are additions to `lsv2/source/`, described in `CONTRIBUTING.md`; they would not change the job file beyond the `source` object.

## Source `gcs`: the Waymo Open Dataset bucket

Downloads, at run time, the Perception v2 `lidar` parquet of each segment from Google Cloud Storage, using credentials you provide.

```json
"source": {"type": "gcs", "bucket": "waymo_open_dataset_v_2_0_1", "credentials": "~/.config/gcloud/application_default_credentials.json"}
```

| key | meaning |
|---|---|
| `type` | `gcs` |
| `bucket` | the bucket name; default `waymo_open_dataset_v_2_0_1` (Perception v2.0.1) |
| `component` | the v2 component to fetch; default `lidar`, the only one `lsv2` reads |
| `credentials` | path to the credentials JSON (required) |

**Credentials.** `lsv2` never logs in by itself; it only consumes a credentials file. Produce it once, on any machine, with the account that holds the Waymo license:

```sh
gcloud auth application-default login     # gcloud comes with the manifest (google-cloud-sdk)
```

This writes `~/.config/gcloud/application_default_credentials.json`; the "quota project" warning is harmless for reading. A service-account JSON works the same way if that account was granted access. Keep the file out of the repository and out of the job file; the job only carries its path.

**Where files are found.** The source looks for `<folder>/<component>/<segment>.parquet` under the bucket's `training`, `validation` and `testing` folders, in that order. Those folders are the official benchmark split, which `lsv2` does not use for anything: the folder is only where the file lives, and the resolved object path goes into `index.csv` as provenance.

**About file sizes.** The Waymo download page quotes ~1 GB per segment: that is Perception v1, one tfrecord holding the 5 lidars, the 5 camera JPEG streams and the labels. `lsv2` reads Perception v2, the same data re-exported as one parquet file per component and segment, and fetches only the `lidar` component, which is 150-190 MB per segment. The TOP range image is identical in both, which the validation against lsv1 output (produced from v1) confirmed bit-exact.

**Files already in the cache.** If `cache_dir` already holds `<segment>.parquet` with the exact size the bucket reports (from an earlier run, a copy from another machine), `plan` marks the segment `cached` and `run` processes it without downloading and never deletes it. The bucket is still consulted for sizes and frame counts, so credentials are still required.

# Run

Write a job file; `jobs/example.json` shows every key with the defaults, on the 8 segments of `jobs/segments.txt`. Paths may use `~` and `$VARS`; relative paths are relative to the job file. Keys:

| key | meaning |
|---|---|
| `segments` | list of Waymo segment ids, or a path to a text file with one id per line (`jobs/segments.txt`) |
| `cache_dir`, `cache_budget_bytes` | where segments wait for processing, and the most bytes `lsv2` may download into it at once |
| `source` | see "Input datasets" |
| `output_dir` | one flat folder for the clips, `index.csv` and `state/` |
| `cpu_workers`, `memory_budget_bytes` | processing workers; the memory budget divided by the measured peak per worker caps the count. `0` = no memory cap |
| `gpu_budget` | must be `0`: no stage uses a GPU, and workers run with the GPU hidden |
| `profile` | `lossless` (default) or `lsv1-compat`, see "Encoding profiles" |
| `verify_lossless` | decode every lossless clip back and abort unless it is bit-exact (default `true`, costs milliseconds) |
| `download_parallel` | concurrent downloads (default 1; one stream already saturates a home link) |
| `clip_frames`, `fps` | frames per clip and frame rate (defaults 22 and 10, the lsv1 reference dataset). The frame size, 2650x64, is the Waymo TOP range image and is not a parameter; the grey mapping is the lsv1 formula and is not a parameter either |
| `prefix` | prepended to every video name: `train` gives `train_<segment>_<clip>.mp4` (default empty). Jobs with different prefixes and disjoint segments may share an `output_dir`; `index.csv` then lists all of them, which is how train/val/test slices are kept in one folder for the ML side's csvs |

```sh
lsv2 plan job.json -o plan.json    # resolves every segment at the source (exact sizes, frame counts); downloads nothing
lsv2 run plan.json                 # prints the plan, asks once, runs; --yes skips the question (tmux)
```

`run` downloads the first segment alone, then keeps one download in flight while workers process what has arrived; a download starts only when its size fits the free cache budget, and a segment is deleted from the cache as soon as its clips are written (only if `lsv2` downloaded it). After the first segment the plan is re-printed with measured throughput, seconds per segment, peak worker memory and bytes per clip. The run is resumable: `state/<segment>.json` records every step, and a restarted `run` skips finished segments. For long runs use `tmux` and `tee`.

Typical numbers on a 10 MB/s link: 17 s to download and 7 s to process one segment, so the run is download-bound and one or two workers are enough; peak worker memory is about 600 MB.

## Output contract

- `[<prefix>_]<segment_id>_<clip>.mp4`: `clip_frames` consecutive sweeps of the segment in time order at `fps`, 2650x64 grey. The trailing partial clip of a segment is dropped (with 22-frame clips, a 198-frame segment gives 9 clips and 0 frames lost; 199 frames give 9 clips and 1 lost).
- `index.csv`: `video, segment, source, clip, first_timestamp_micros, last_timestamp_micros, profile, verified`.
- `state/`: one JSON per segment (status, sizes, timings, clip sizes, errors). Safe to delete after the run.

`lsv2` makes no train/val/test split and writes no `train.csv`: that is the ML side's job (`mae_st_lcad` builds its csvs, format `absolute_path label`, from a folder of videos). A split is one job per slice with disjoint segments and a distinguishing `prefix`.

## Encoding profiles

| profile | ffmpeg | what the decoder sees |
|---|---|---|
| `lossless` | `libx264 -qp 0 -pix_fmt gray` | exactly the rendered grey values (verified per clip); PyAV's `rgb24` conversion returns R=G=B=Y with zero error. ~1.2 MB per 22-frame clip |
| `lsv1-compat` | `scale=in_range=full:out_range=full,setrange=limited`, `libx264 -crf 23 -g <clip_frames> -pix_fmt yuv420p` | a file like the lsv1 reference videos: lossy (crf 23), grey values stored raw in luma with no range flag, same x264 settings (keyint = clip length, bframes 3, ref 3). ~0.77 MB per 22-frame clip, the same as the reference |

The lsv1 reference videos carry the grey values raw in luma but no range flag, so a decoder that converts to RGB (as MAE-ST's PyAV path does) expands 16..235 to 0..255 and shifts values by up to 20 levels. `lsv1-compat` reproduces the file, and therefore that behaviour; `lossless` is tagged full range and comes through unchanged. Training on `lossless` therefore changes the input distribution relative to a run on lsv1 data. Choose knowingly.

> **Provenance.** The grey image is lsv1's: `value = trunc(255 - range * 100 / resolution)` with `resolution = 75 * 100 / 256`, clamped to [0, 255], no return -> 0, applied to the first return of the TOP laser. `lsv2` computes it directly from the Perception v2 parquet instead of lsv1's tfrecord -> points -> `.bin` -> C++ viewer -> PNG chain, and the result is bit-exact against the lsv1 PNG sample (`tests/test_oracle.py`). The video settings come from forensics of the lsv1 reference videos, whose source segment is unknown. Details in `CONTRIBUTING.md`.
