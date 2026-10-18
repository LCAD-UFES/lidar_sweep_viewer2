import os, unittest
import numpy as np
from lsv2.reader import top_range_frames
from lsv2.render import render

# lsv1 sample output (stacked PNGs): <segment>_<n>.png holds frames 16n..16n+15 stacked top to bottom, 64 rows each.
# Set LSV2_ORACLE_PNG and LSV2_ORACLE_PARQUET to run; skipped otherwise.
PNG, PARQUET = os.environ.get("LSV2_ORACLE_PNG", ""), os.environ.get("LSV2_ORACLE_PARQUET", "")

@unittest.skipUnless(os.path.exists(PNG) and os.path.exists(PARQUET), "oracle files not configured")
class OracleTest(unittest.TestCase):
    def test_bit_exact_against_legacy_png(self) -> None:
        from PIL import Image
        img = np.asarray(Image.open(PNG).convert("L"))
        n = int(os.path.splitext(PNG)[0].rsplit("_", 1)[1])
        frames = [render(r) for _, r in top_range_frames(PARQUET)]
        h = len(frames[0])
        for k in range(len(img) // h):
            np.testing.assert_array_equal(frames[16 * n + k], img[k * h:(k + 1) * h], err_msg=f"strip {k}")

if __name__ == "__main__": unittest.main()
