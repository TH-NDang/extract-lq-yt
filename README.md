# extract-lq-yt

Trích xuất khung hình từ livestream **Liên Quân Mobile** trên YouTube bằng GitHub Actions, **không dùng cookie**. Đầu ra là GitHub Actions Artifact ZIP gồm ảnh có timestamp, contact sheets để duyệt nhanh, metadata và dữ liệu tham chiếu từ `TH-NDang/aov-project`.

> Giai đoạn 1: trích ảnh và lập chỉ mục; **chưa tự nhận diện Pick/Ban/trang bị**. Các khung hình sẽ được đối chiếu với bộ ảnh tham chiếu ở giai đoạn phân tích thị giác tiếp theo.

## Chạy thử

1. Mở **Actions → Extract AOV YouTube Frames → Run workflow**.
2. Để `video_url=https://www.youtube.com/watch?v=XicevhyRvL0`.
3. Chọn `mode=test`, `clip_start=00:20:00`, `clip_end=00:21:00`.
4. Sau khi hoàn tất, tải artifact `aov-frames-<video-id>-<run-id>` trong workflow run.

## Các chế độ

| mode | Chất lượng tối đa | Mỗi ảnh | Phạm vi |
|---|---:|---:|---|
| `test` | 720p | 5 giây | 1 phút, mặc định 20:00–21:00 |
| `scan` | 480p | 15 giây | Toàn bộ livestream nếu bỏ trống clip |
| `detail` | 1080p | 2 giây | **Bắt buộc** nhập clip_start và clip_end |

`max_frames` giới hạn số ảnh để tránh artifact quá lớn (mặc định 1800). Quét toàn bộ livestream hàng giờ tiêu tốn thời gian/đĩa GitHub runner; dùng `test` trước. Scan dùng để tìm đoạn Pick/Ban / kết quả. Sau đó chạy `detail` theo từng khoảng để thu ảnh rõ.

## Dữ liệu tham chiếu

Nguồn GitHub:

- `TH-NDang/aov-project/resources/Lien-Quan-v3/data/heroes.json`: `heroes[].id/name/head/listHead`.
- `.../data/trang-bi.json`: `items[].id/name/image`.
- `.../data/phu-hieu.json`: `items[].id/name/image.file`.
- `.../assets/hero/head`, `assets/trang-bi`, `assets/phu-hieu/icon`: hình ảnh gốc lưu bằng Git LFS.

Workflow chỉ tải các **JSON** để tạo `references/reference-index.json` và `references/reference-report.json`, tránh kéo hàng trăm ảnh LFS vào mỗi lần chạy. Muốn truy cập nội dung ảnh LFS thật, phải checkout `aov-project` với Git LFS (không đọc nhầm pointer ~130 byte thành ảnh). Khi có ảnh trên Google Drive, có thể dùng nguồn Drive cho bước đối chiếu.

Phép bổ trợ / bảng ngọc chưa có bộ tham chiếu hoàn chỉnh trong thư mục nói trên; pipeline không tự bịa kết quả.

## Định dạng artifact

```text
out/
  video.json
  report.json
  frames/
    frame_000000.jpg
    ...
    index.jsonl
  contact-sheets/
    page_001.jpg
    ...
  references/
    reference-index.json
    reference-report.json
```

Mỗi dòng `index.jsonl` có `time_seconds` (timestamp trên video YouTube), `time_hhmmss`, đường dẫn ảnh, kích thước. Timestamp được **ước lượng theo tần suất trích ảnh**; nếu cắt video bằng `--download-sections` thì cộng offset `clip_start`. Luôn dùng ảnh đối chứng để xác nhận Pick/Ban.

## Giới hạn

- YouTube có thể chặn GitHub-hosted IP / yêu cầu PO Token ngay cả khi URL công khai. Không sử dụng cookie; workflow sẽ báo lỗi thay vì vượt cơ chế truy cập.
- `yt-dlp -F` hoạt động không đảm bảo `yt-dlp` tải thành công.
- `--download-sections` cần FFmpeg; độ dài clip thực tế có thể lệch ít giây tại keyframe.
- Workflow không tự chép ảnh/video có bản quyền sang kho công khai hay Release.
- Artifact có thời hạn lưu trữ theo GitHub Actions; hiện cấu hình 14 ngày. Không lưu nguyên video trong artifact.

## Chạy cục bộ (tùy chọn)

```bash
python -m pip install -r requirements.txt
python scripts/extract.py --url "https://www.youtube.com/watch?v=XicevhyRvL0" --mode test --start 00:20:00 --end 00:21:00 --out out
python scripts/references.py --out out/references
```

Yêu cầu: Python 3.11+, FFmpeg/ffprobe trên PATH, kết nối YouTube.

## Bảo mật

Workflow chỉ nhận URL YouTube; không dùng cookie hoặc token từ trình duyệt. Quyền GitHub Actions: `contents: read`. Dữ liệu từ `aov-project` được tham chiếu qua GitHub public raw URLs, không cần Google Drive token.
