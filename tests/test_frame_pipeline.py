"""End-to-end FFmpeg frame extraction test using an entirely synthetic video."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.extract import extract


class FramePipelineTest(unittest.TestCase):
    def test_extract_synthetic_video_and_timestamp_index(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg tools unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "synthetic.mp4"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=2",
                 "-t", "9", "-an", "-c:v", "mpeg4", "-q:v", "4", str(video)],
                check=True,
            )
            out = root / "out"
            result = extract(video, out, offset=1200, base_interval=2, max_frames=100)
            self.assertGreaterEqual(result["image_count"], 4)
            self.assertLessEqual(result["image_count"], 6)
            self.assertGreaterEqual(len(result["contact_sheets"]), 1)
            manifest = (out / "frames" / "index.jsonl").read_text(encoding="utf-8")
            rows = [json.loads(line) for line in manifest.splitlines()]
            self.assertEqual(len(rows), result["image_count"])
            self.assertEqual(rows[0]["time_seconds"], 1200)
            self.assertEqual(rows[0]["time_hhmmss"], "00:20:00")
            self.assertEqual(rows[1]["time_seconds"], 1202)
            for row in rows:
                self.assertTrue((out / row["file"]).is_file())
            for file in result["contact_sheets"]:
                self.assertTrue((out / file).is_file())


if __name__ == "__main__":
    unittest.main()
