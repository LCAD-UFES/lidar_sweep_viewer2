import numpy as np, pyarrow.parquet as pq, pyarrow.compute as pc
from .config import TOP_LASER, RI_HEIGHT, RI_WIDTH

# Waymo Open Dataset v2 lidar component (https://github.com/waymo-research/waymo-open-dataset, v2 parquet schema)
TS, LASER = "key.frame_timestamp_micros", "key.laser_name"
VALUES, SHAPE = "[LiDARComponent].range_image_return1.values", "[LiDARComponent].range_image_return1.shape"
RANGE_CHANNEL = 0   # range image channels: range, intensity, elongation, is_in_no_label_zone

def top_range_frames(path):
    # [(timestamp_micros, range in metres as float32 [H, W])] of the TOP laser, first return, sorted by time; -1 = no return
    frames = []
    for batch in pq.ParquetFile(path).iter_batches(batch_size=8, columns=[TS, LASER, VALUES, SHAPE]):
        keep = pc.equal(batch.column(LASER), TOP_LASER)
        if not pc.any(keep).as_py(): continue
        b = batch.filter(keep)
        values, shapes = b.column(VALUES), b.column(SHAPE).values.to_numpy().reshape(-1, 3)
        flat, offsets = values.values.to_numpy(zero_copy_only=False), values.offsets.to_numpy()
        for ts, k in zip(b.column(TS).to_pylist(), range(len(b))):
            h, w, c = shapes[k]
            if (h, w) != (RI_HEIGHT, RI_WIDTH): raise ValueError(f"{path}: TOP range image is {h}x{w}, expected {RI_HEIGHT}x{RI_WIDTH}")
            frames.append((ts, flat[offsets[k]:offsets[k + 1]].reshape(h, w, c)[..., RANGE_CHANNEL].astype(np.float32)))
    frames.sort(key=lambda f: f[0])
    return frames
