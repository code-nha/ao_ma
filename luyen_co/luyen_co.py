"""luyen_co — lọc các frame có một người cụ thể trong folder ảnh/video CCTV.

Ý tưởng: cho 1 ảnh tham chiếu rõ nhất của người cần tìm, quét toàn bộ folder
(video + ảnh), giữ lại đúng những frame có người đó với góc mặt và dáng đi
đa dạng nhất.

Ví dụ:
  python luyen_co.py --input "D:\\cctv\\cam1" --ref "D:\\ref\\anh_ro_nhat.jpg"
  python luyen_co.py --input D:\\cctv --ref ref.jpg --fps 3 --limit 200
  python luyen_co.py --input D:\\cctv --ref ref.jpg --check      # chỉ phân tích ảnh tham chiếu

Kết quả trong thư mục --out:
  crops/          ảnh crop quanh người (mỗi frame 1 ảnh, 1 người)
  metadata.jsonl  nguồn, thời điểm, bbox, điểm khớp, góc đầu, pose
  report.csv      số ảnh theo từng file nguồn
  summary.txt     thống kê + phân bố điểm khớp + độ phủ góc
  sheet.jpg       bảng ảnh xem nhanh để kiểm tra bằng mắt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# console Windows mặc định cp1252 sẽ chết với tiếng Việt khi bị pipe/redirect
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from core.onnx_models import log           # noqa: E402
from core.pipeline import Config, Pipeline  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Lọc frame của một người trong folder ảnh/video CCTV theo ảnh tham chiếu.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", required=True, type=Path, help="folder chứa ảnh và video cần quét")
    p.add_argument("--ref", required=True, type=Path, help="ảnh tham chiếu rõ nhất của người cần tìm")
    p.add_argument("--out", type=Path, default=Path("out"), help="thư mục xuất kết quả")
    p.add_argument("--clean", action="store_true",
                   help="xoá ảnh cũ trong <out>/crops trước khi ghi kết quả mới")
    p.add_argument("--check", action="store_true", help="chỉ phân tích ảnh tham chiếu rồi thoát")

    g = p.add_argument_group("lấy mẫu")
    g.add_argument("--fps", type=float, default=2.0, help="số frame lấy mỗi giây của video")
    g.add_argument("--start", type=float, default=0.0, help="bắt đầu từ giây thứ")
    g.add_argument("--end", type=float, default=0.0, help="kết thúc ở giây thứ (0 = hết video)")
    g.add_argument("--max-frames", type=int, default=0, help="giới hạn số frame mỗi video (0 = không)")
    p.add_argument("--recursive", action="store_true", help="quét cả thư mục con")
    p.add_argument("--include-ref", action="store_true",
                   help="vẫn xử lý ảnh tham chiếu nếu nó nằm trong folder quét (mặc định bỏ qua)")

    g = p.add_argument_group("ngưỡng khớp danh tính")
    g.add_argument("--face-th", type=float, default=0.45, help="cosine ArcFace tối thiểu coi là đúng người")
    g.add_argument("--body-th", type=float, default=0.72, help="cosine CLIP toàn thân tối thiểu khi không thấy mặt")
    g.add_argument("--color-th", type=float, default=0.3,
                   help="tương quan màu áo/quần tối thiểu khi so khớp toàn thân "
                        "(chống nhầm người mặc áo khác màu cùng nền; 0 = tắt)")

    g = p.add_argument_group("lọc chất lượng")
    g.add_argument("--min-person", type=int, default=64, help="chiều cao tối thiểu của người (px)")
    g.add_argument("--min-person-score", type=float, default=0.5,
                   help="ngưỡng tin cậy tối thiểu của detection người")
    g.add_argument("--max-overlap", type=float, default=0.35,
                   help="bỏ frame có người khác chồng lên người mục tiêu quá mức này (IoU), "
                        "0 = tắt kiểm tra")
    g.add_argument("--max-other-area", type=float, default=0.10,
                   help="bỏ frame mà người khác chiếm quá tỉ lệ này diện tích crop, "
                        "để mỗi ảnh chỉ có 1 người (0 = tắt)")
    g.add_argument("--min-blur", type=float, default=25.0, help="phương sai Laplacian tối thiểu (chống ảnh mờ)")
    g.add_argument("--crop-margin", type=float, default=0.12, help="nới bbox khi crop (tỉ lệ cạnh)")

    g = p.add_argument_group("xuất ảnh")
    g.add_argument("--save", choices=["full", "crop", "both"], default="full",
                   help="full = giữ nguyên frame (có bối cảnh, dễ truy ra camera nào); "
                        "crop = chỉ ảnh quanh người; both = cả hai")
    g.add_argument("--min-yaw", type=float, default=20.0,
                   help="chênh góc đầu tối thiểu (độ) để giữ thêm một ảnh")
    g.add_argument("--min-pose", type=float, default=0.10,
                   help="chênh pose (keypoint chuẩn hoá, 0–1) tối thiểu để giữ thêm một ảnh; "
                        "đặt 0 để tắt lọc đa dạng")
    g.add_argument("--confirm-window", type=float, default=0.0,
                   help="giây: giới hạn khoảng cách tới mốc đã khớp mặt khi nhận frame quay lưng "
                        "(0 = không giới hạn, dựa vào neo ngoại hình của cả video)")
    g.add_argument("--anchor-th", type=float, default=0.60,
                   help="cosine tối thiểu với neo ngoại hình của video khi nhận frame quay lưng")
    g.add_argument("--select", choices=["coverage", "diversity"], default="coverage",
                   help="coverage = đảm bảo đủ góc (mặt trái/phải/thẳng + sau lưng); "
                        "diversity = chỉ giữ frame khác nhau quá ngưỡng --min-yaw/--min-pose")
    g.add_argument("--per-bucket", type=int, default=1,
                   help="số ảnh tối đa cho mỗi nhóm góc khi dùng --select coverage")

    g = p.add_argument_group("lọc trùng & đa dạng")
    g.add_argument("--dup-sim", type=float, default=0.97, help="cosine coi là trùng hẳn (bỏ bớt)")
    g.add_argument("--min-gap", type=float, default=0.35, help="khoảng cách giây tối thiểu giữa 2 ảnh cùng track")
    g.add_argument("--limit", type=int, default=0,
                   help="chỉ giữ N ảnh đa dạng nhất (0 = giữ hết sau lọc trùng)")
    g.add_argument("--min-track", type=int, default=3,
                   help="track phải có ít nhất chừng này frame mới được xét khi không thấy mặt")
    g.add_argument("--allow-body-only", action="store_true",
                   help="nhận cả track không có frame nào khớp mặt, chỉ dựa vào toàn thân "
                        "(dễ nhầm người mặc giống; dùng khi CCTV không bao giờ thấy mặt)")

    g = p.add_argument_group("hiệu năng")
    g.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    g.add_argument("--imgsz", type=int, default=640, help="kích thước input YOLO")
    g.add_argument("--tiles", type=int, default=1,
                   help="chia frame thành lưới tiles×tiles trước khi detect (1 = tắt); "
                        "dùng 2 cho CCTV góc rộng/4K có người rất nhỏ, chậm hơn ~4 lần")
    g.add_argument("--conf", type=float, default=0.35, help="ngưỡng tin cậy phát hiện người")
    g.add_argument("--face-conf", type=float, default=0.5, help="ngưỡng tin cậy phát hiện mặt")
    g.add_argument("--sheet", type=int, default=60, help="số ảnh trong sheet.jpg (0 = không xuất)")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.input.is_dir():
        log(f"lỗi: --input không phải thư mục: {args.input}")
        return 2
    if not args.ref.is_file():
        log(f"lỗi: không thấy ảnh tham chiếu: {args.ref}")
        return 2

    cfg = Config(
        ref=args.ref, out=args.out, fps=args.fps,
        face_th=args.face_th, body_th=args.body_th, color_th=args.color_th,
        min_person=args.min_person, min_blur=args.min_blur,
        min_person_score=args.min_person_score, max_overlap=args.max_overlap,
        max_other_area=args.max_other_area,
        crop_margin=args.crop_margin, save=args.save,
        min_yaw=args.min_yaw, min_pose=args.min_pose, dup_sim=args.dup_sim,
        confirm_window=args.confirm_window, anchor_th=args.anchor_th,
        select=args.select, per_bucket=args.per_bucket,
        min_gap=args.min_gap, limit=args.limit, device=args.device,
        min_track=args.min_track, allow_body_only=args.allow_body_only,
        skip_ref=not args.include_ref,
        imgsz=args.imgsz, tiles=args.tiles, conf=args.conf, face_conf=args.face_conf,
        max_frames=args.max_frames, start=args.start,
        end=args.end if args.end > 0 else None, sheet=args.sheet,
        clean=args.clean,
    )
    args.out.mkdir(parents=True, exist_ok=True)

    started = time.time()
    pipe = Pipeline(cfg)
    log(pipe.ref_note)
    if args.check:
        if pipe.ref_info:
            info = pipe.ref_info
            log(f"  mặt ~{info['face_px']}px (tin cậy {info['face_score']}), "
                f"người cao ~{info['person_h']}px, độ nét {info['blur']}")
    for warning in pipe.ref_warnings:
        log(f"cảnh báo: {warning}")
    if args.check:
        return 0

    try:
        pipe.run(args.input, recursive=args.recursive)
    except KeyboardInterrupt:
        log("dừng theo yêu cầu — vẫn xuất các frame đã nhận")
    rows = pipe.export()

    st = pipe.stats
    log(f"xong sau {time.time() - started:.0f}s · {st.frames} frame · "
        f"{st.tracks} track · nhận {st.accepted_tracks} track")
    log(f"đã ghi {len(rows)} ảnh vào {cfg.crops_dir}")
    log(f"xem nhanh: {cfg.out / 'sheet.jpg'} · chi tiết: {cfg.out / 'summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
