# pyright: reportUnknownMemberType=false
# pyarrow-stubs types ListArray.values/offsets and iter_batches' list parameters as bare generics; the numpy views taken
# from them are cast to concrete dtypes below, which is where the real contract lives.
from typing import cast
import numpy as np, numpy.typing as npt, pyarrow as pa, pyarrow.parquet as pq
from .config import TOP_LASER, RI_HEIGHT, RI_WIDTH

# Waymo Open Dataset v2 lidar component (https://github.com/waymo-research/waymo-open-dataset, v2 parquet schema)
TS, LASER = "key.frame_timestamp_micros", "key.laser_name"
VALUES, SHAPE = "[LiDARComponent].range_image_return1.values", "[LiDARComponent].range_image_return1.shape"
RANGE_CHANNEL = 0   # range image channels: range, intensity, elongation, is_in_no_label_zone

Frame = tuple[int, npt.NDArray[np.float32]]   # (timestamp_micros, range in metres [H, W]; -1 = no return)

def top_range_frames(path: str) -> list[Frame]:
    # frames of the TOP laser, first return, sorted by time
    frames: list[Frame] = []
    for batch in pq.ParquetFile(path).iter_batches(batch_size=8, columns=[TS, LASER, VALUES, SHAPE]):
        laser = cast(npt.NDArray[np.int8], batch.column(LASER).to_numpy())
        top = np.flatnonzero(np.equal(laser, TOP_LASER))
        if top.size == 0: continue
        b = batch.take(top)
        values = cast("pa.ListArray[pa.ListScalar[pa.DataType]]", b.column(VALUES))   # stub-only generic: quoted so it is not evaluated at run time
        flat = cast(npt.NDArray[np.float32], values.values.to_numpy(zero_copy_only=False))
        offsets = cast(list[int], values.offsets.to_numpy().tolist())
        shapes = cast(list[list[int]], b.column(SHAPE).to_pylist())
        timestamps = cast(list[int], b.column(TS).to_pylist())
        for k, ts in enumerate(timestamps):
            h, w, c = shapes[k]
            if (h, w) != (RI_HEIGHT, RI_WIDTH): raise ValueError(f"{path}: TOP range image is {h}x{w}, expected {RI_HEIGHT}x{RI_WIDTH}")
            image = flat[offsets[k]:offsets[k + 1]].reshape(h, w, c)
            frames.append((ts, image[..., RANGE_CHANNEL].astype(np.float32)))
    frames.sort(key=lambda f: f[0])
    return frames
