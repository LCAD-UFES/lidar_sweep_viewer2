import os, tempfile, unittest
from typing import override
import numpy as np, numpy.typing as npt
from lsv2.encoder import encode, decode

class EncoderTest(unittest.TestCase):
    frames: npt.NDArray[np.uint8] = np.empty(0, dtype=np.uint8)

    @override
    def setUp(self) -> None:
        rng = np.random.default_rng(0)
        ramp = np.tile(np.arange(2650) % 256, (64, 1)).astype(np.uint8)
        self.frames = np.stack([ramp] + [rng.integers(0, 256, (64, 2650), dtype=np.uint8) for _ in range(21)])

    def test_lossless_roundtrip_is_bit_exact(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "clip.mp4"); size = encode(self.frames, p, "lossless", 10)
            self.assertGreater(size, 0); self.assertFalse(os.path.exists(p + ".part.mp4"))
            np.testing.assert_array_equal(decode(p), self.frames)

    def test_lsv1_compat_keeps_full_range(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "clip.mp4"); _ = encode(self.frames, p, "lsv1-compat", 10)
            y = decode(p)
            self.assertEqual(y.shape, self.frames.shape)
            self.assertLess(int(np.min(y[:1])), 8); self.assertGreater(int(np.max(y[:1])), 247)   # ramp survives: no 16..235 squeeze

if __name__ == "__main__": unittest.main()
