import os, shutil, subprocess, sys
import numpy as np, av

# Measured 2026-10-18 on 22 real frames (DESIGN.md "Validation"):
# lossless: gray -qp 0 decodes bit-exact (max |diff| = 0), smallest file.
# lsv1-compat: the lsv1 reference videos are yuv420p, crf 23, keyint = clip length (ffmpeg 4.2 / x264 core 155) with the
# grey values stored raw in luma (Y in 0..245) and no range flag; ffmpeg >= 7 would squeeze gray to 16..235 when converting
# to yuv420p, so the scale filter keeps the values and setrange=limited stops any further conversion while x264 omits the
# range flag exactly like the reference (setrange=unspecified triggers the squeeze again; measured).
# "{keyint}" is replaced by the clip length at encode time.
PROFILES = {
    "lossless": ["-c:v", "libx264", "-qp", "0", "-pix_fmt", "gray"],
    "lsv1-compat": ["-vf", "scale=in_range=full:out_range=full,setrange=limited",
                    "-c:v", "libx264", "-crf", "23", "-g", "{keyint}", "-pix_fmt", "yuv420p"],
}

def ffmpeg_path():
    bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "ffmpeg")   # PyInstaller one-file bundle (_bundle/build.sh)
    p = bundled if os.path.isfile(bundled) else shutil.which("ffmpeg")
    if not p: raise FileNotFoundError("ffmpeg not on PATH")
    return p

def encode(frames, path, profile, fps):
    # frames: uint8 [n, H, W]; writes path atomically; returns file size in bytes
    frames = np.ascontiguousarray(frames, dtype=np.uint8); n, h, w = frames.shape
    tmp = f"{path}.part.mp4"
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", *[a.format(keyint=n) for a in PROFILES[profile]], "-y", tmp]
    subprocess.run(cmd, input=frames.tobytes(), check=True)
    os.replace(tmp, path)
    return os.path.getsize(path)

def decode(path):
    # luma plane of every frame as uint8 [n, H, W], no range conversion (what the pixels really hold)
    out = []
    with av.open(path) as container:
        for fr in container.decode(video=0):
            p = fr.planes[0]
            out.append(np.frombuffer(p, dtype=np.uint8, count=fr.height * p.line_size).reshape(fr.height, p.line_size)[:, :fr.width].copy())
    return np.stack(out)
