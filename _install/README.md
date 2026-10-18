# Installing lsv2 on a new machine

`conda.sh` builds the conda environment from a **manifest**, `deps.<host>.tsv`, and contains no package list of its own. It is the installer of `LCAD-UFES/mae_st_lcad` (branch `installer`, v1.2.0) with only its final verification and project strings changed; the manifest format and the recipe for writing one are documented there and in the header of `deps.linux-x86_64.tsv`.

```sh
cd _install
./conda.sh deps.linux-x86_64.tsv --dry-run     # print every command, run nothing
./conda.sh deps.linux-x86_64.tsv               # menu: rename env, show manifest, check resolution, install
./conda.sh deps.linux-x86_64.tsv --yes         # install directly
```

Run it from this directory: the last row installs the repository itself with `pip install -e ..`. The preamble compares this host with the manifest's `#!target` line; a divergence is a prompt to copy the manifest to `deps.<host>.tsv` and adjust, never to edit `conda.sh`. `lsv2` compiles nothing and uses no GPU, so the `gpu`, `sm` and `cuda` fields are informational.

After installing, the script verifies the imports, that `ffmpeg` has `libx264` with the `gray` pixel format, and runs the unit tests. A successful install also writes `lock.<tag>.txt` (a `pip freeze`, for pinning the manifest on a new host) and a log under `logs/`; both are git-ignored.
