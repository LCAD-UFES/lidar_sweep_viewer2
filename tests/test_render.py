import unittest, numpy as np
from lsv2.render import render

class RenderTest(unittest.TestCase):
    def test_synthetic_ranges(self):
        # expected values from utils.cpp::normalizar by hand: trunc(255 - r*256/75), r<0 -> 0, clamp
        r = np.array([-1.0, 0.0, 37.5, 74.995, 75.0, 100.0, 0.29, 0.30], dtype=np.float32)
        self.assertEqual(render(r).tolist(), [0, 255, 127, 0, 0, 0, 254, 253])

    def test_shape_and_dtype(self):
        r = np.full((64, 2650), 10.0, dtype=np.float32)
        v = render(r)
        self.assertEqual((v.shape, v.dtype), ((64, 2650), np.uint8))
        self.assertEqual(int(v[0, 0]), int(255 - 10 * 256 / 75))   # the C++ truncates the whole expression: 220, not 221

if __name__ == "__main__": unittest.main()
