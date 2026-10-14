#!/usr/bin/env python3
"""Extract reviewable frames from a public YouTube VOD without cookies."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MODES = {
    "test": {"height": 720, "interval": 5},
    "scan": {"height": 480, "interval": 15},
    "detail": {"height": 1080, "interval": 2},
}


def clock_to_sec(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        raise ValueError("Time must be MM:SS or HH:MM:SS")
    numbers = [int(p) for p in parts]
    if len(numbers) == 2:
        minutes, seconds = numbers
        if seconds >= 60:
            raise ValueError("Seconds must be below 60")
        return minutes * 60 + seconds
    hours, minutes, seconds = numbers
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutes and seconds must be below 60")
    return hours * 3600 + minutes * 60 + seconds


def timestamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 3600:02}:{(seconds % 3600) // 60:02}:{seconds % 60:02}"


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or "")[-3000:] if capture else ""
        raise RuntimeError(f"Command failed ({completed.returncode}): {command[0]} {detail}")
    return completed


def no_cookie_flags() -> list[str]:
    return ["--ignore-config", "--no-cookies", "--no-cookies-from-browser", "--no-playlist"]


def metadata(url: str) -> dict:
    command = [sys.executable, "-m", "yt_dlp", *no_cookie_flags(),
               "--skip-download", "--dump-single-json", url]
    response = run(command, capture=True)
    source = json.loads(response.stdout)
    keys = ("id", "title", "description", "channel", "channel_id", "uploader",
            "upload_date", "duration", "webpage_url", "live_status", "availability")
    info = {key: source.get(key) for key in keys}
    info["captured_at"] = datetime.now(timezone.utc).isoformat()
    info["requested_url"] = url
    return info


def probe_video(video: Path) -> dict:
    raw = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_entries", "format=duration:stream=width,height,codec_name,codec_type",
               str(video)], capture=True).stdout
    return json.loads(raw)


def find_video(work: Path) -> Path:
    files = [p for p in work.glob("video.*")
             if p.is_file() and p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not files:
        raise FileNotFoundError("yt-dlp did not produce a video file")
    return max(files, key=lambda p: p.stat().st_size)


def download(url: str, work: Path, height: int, start: int | None,
             end: int | None) -> Path:
    # The fallback is video-only. Audio is unnecessary for image recognition.
    formats = (f"bv[ext=mp4][height<={height}]/"
               f"bv[height<={height}]/b[height<={height}]")
    command = [sys.executable, "-m", "yt_dlp", *no_cookie_flags(),
               "--no-progress", "-f", formats,
               "-o", str(work / "video.%(ext)s")]
    if start is not None or end is not None:
        section = f"*{timestamp(start or 0)}-"
        if end is not None:
            section += timestamp(end)
        command.extend(["--download-sections", section])
    command.append(url)
    run(command)
    return find_video(work)


def contact_sheets(rows: list[dict], out: Path) -> list[str]:
    sheets = out / "contact-sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    labels = []
    width, image_height, text_height = 240, 135, 30
    columns, sheet_rows = 5, 8
    page_size = columns * sheet_rows
    font = ImageFont.load_default()
    for page_num, offset in enumerate(range(0, len(rows), page_size), 1):
        page = rows[offset:offset + page_size]
        canvas = Image.new("RGB", (columns * width, sheet_rows * (image_height + text_height)), "white")
        painter = ImageDraw.Draw(canvas)
        for idx, row in enumerate(page):
            left = (idx % columns) * width
            top = (idx // columns) * (image_height + text_height)
            with Image.open(out / row["file"]) as image:
                image.thumbnail((width - 4, image_height - 4))
                canvas.paste(image.convert("RGB"), (left + (width-image.width)//2, top+2))
            painter.text((left+6, top+image_height+3),
                         f'{row["time_hhmmss"]}  frame {row["frame_index"]}', fill="black", font=font)
        name = f"page_{page_num:03d}.jpg"
        canvas.save(sheets / name, "JPEG", quality=82, optimize=True)
        labels.append(f"contact-sheets/{name}")
    return labels


def extract(video: Path, out: Path, offset: int, base_interval: int,
            max_frames: int) -> dict:
    probe = probe_video(video)
    duration = float(probe.get("format", {}).get("duration") or 0)
    # Increase spacing on long videos instead of truncating the later matches.
    interval = max(base_interval, math.ceil(duration / max_frames)) if duration else base_interval
    frame_dir = out / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
         "-y", "-i", str(video), "-vf", f"fps=1/{interval}",
         "-q:v", "3", "-frames:v", str(max_frames),
         str(frame_dir / "frame_%06d.jpg")])
    image_files = sorted(frame_dir.glob("frame_*.jpg"))
    if not image_files:
        raise RuntimeError("FFmpeg produced zero frames")
    rows = []
    for idx, path in enumerate(image_files):
        time_seconds = offset + idx * interval
        rows.append({
            "frame_index": idx,
            "file": f"frames/{path.name}",
            "time_seconds": time_seconds,
            "time_hhmmss": timestamp(time_seconds),
            "timestamp_basis": "estimated_from_fps_and_clip_offset",
        })
    with (frame_dir / "index.jsonl").open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    pages = contact_sheets(rows, out)
    return {
        "video_file_bytes": video.stat().st_size,
        "downloaded_duration_seconds": duration,
        "interval_seconds": interval,
        "image_count": len(rows),
        "contact_sheets": pages,
        "frame_first": rows[0],
        "frame_last": rows[-1],
        "input_video": {
            "streams": [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--mode", choices=MODES, default="test")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--max-frames", type=int, default=1800)
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--work", type=Path, default=Path("working"))
    args = parser.parse_args()

    out, work = args.out, args.work
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    report = {"status": "started", "mode": args.mode, "url": args.url}
    try:
        if not re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", args.url):
            raise ValueError("Only youtube.com and youtu.be URLs are accepted")
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("ffmpeg and ffprobe must be installed")
        if not 1 <= args.max_frames <= 10000:
            raise ValueError("--max-frames must be from 1 to 10000")

        start = clock_to_sec(args.start)
        end = clock_to_sec(args.end)
        if args.mode == "test":
            start = 20 * 60 if start is None else start
            end = (start + 60) if end is None else end
        elif args.mode == "detail" and (start is None or end is None):
            raise ValueError("Detail mode requires both --start and --end")
        if end is not None and end <= (start or 0):
            raise ValueError("--end must be greater than --start")
        report.update({"clip_start_seconds": start or 0, "clip_end_seconds": end,
                       "max_frames": args.max_frames})
        info = metadata(args.url)
        (out / "video.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        video = download(args.url, work, MODES[args.mode]["height"], start, end)
        result = extract(video, out, start or 0, MODES[args.mode]["interval"], args.max_frames)
        report.update({"status": "success", **result})
        print(f"Extracted {result['image_count']} frames; {len(result['contact_sheets'])} sheets")
        return 0
    except Exception as exc:
        report.update({"status": "failed", "error": str(exc),
                       "traceback": traceback.format_exc()[-6000:]})
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        (out / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
