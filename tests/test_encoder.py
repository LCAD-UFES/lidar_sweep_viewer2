import os, tempfile, unittest, numpy as np
from lsv2.encoder import encode, decode

class EncoderTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        ramp = np.tile(np.arange(2650) % 256, (64, 1)).astype(np.uint8)
        self.frames = np.stack([ramp] + [rng.integers(0, 256, (64, 2650), dtype=np.uint8) for _ in range(21)])

    def test_lossless_roundtrip_is_bit_exact(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "clip.mp4"); size = encode(self.frames, p, "lossless", 10)
            self.assertGreater(size, 0); self.assertFalse(os.path.exists(p + ".part.mp4"))
            np.testing.assert_array_equal(decode(p), self.frames)

    def test_lsv1_compat_keeps_full_range(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "clip.mp4"); encode(self.frames, p, "lsv1-compat", 10)
            y = decode(p)
            self.assertEqual(y.shape, self.frames.shape)
            self.assertLess(int(y[0].min()), 8); self.assertGreater(int(y[0].max()), 247)   # ramp survives: no 16..235 squeeze

if __name__ == "__main__": unittest.main()
