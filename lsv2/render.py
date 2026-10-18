import numpy as np
from .config import METERS, LEVELS

def render(range_m):
    # utils.cpp::normalizar: resolution = meters*100/256 (cm per grey level); value = (int)(255 - r*100/resolution),
    # clamped to [0, 255]; r < 0 (no return) -> 0. float32 arithmetic and truncation reproduce the C++ bit-exact.
    resolution = np.float32(METERS * 100 / LEVELS)
    v = (np.float32(255) - range_m.astype(np.float32) * np.float32(100) / resolution).astype(np.int32)
    v = np.clip(v, 0, 255).astype(np.uint8)
    v[range_m < 0] = 0
    return v
