"""Web UI nhỏ để tải video từ URL về máy — phục vụ việc kiếm dữ liệu test cho luyen_co.

Nhận: link YouTube, TikTok, Facebook, Instagram, hoặc trang web có thẻ <video> /
link .mp4 / .m3u8 trực tiếp. Tải bằng yt-dlp (ưu tiên) và tự fallback sang bóc
link media trong HTML khi yt-dlp không hỗ trợ trang đó.

Chạy:
  python download_ui.py                 # mở http://127.0.0.1:8765
  python download_ui.py --port 9000 --out D:\\cctv_test --no-browser

Video tải về nằm trong --out (mặc định ./downloads), sau đó trỏ luyen_co vào đó:
  python luyen_co.py --input downloads --ref anh.jpg
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

try:
    import yt_dlp
except ImportError:  # vẫn dùng được chế độ tải link trực tiếp
    yt_dlp = None

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".ts", ".m4v", ".3gp"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

OUT_DIR = Path("downloads")
MAX_HEIGHT = 1080


@dataclass
class Job:
    id: str
    url: str
    status: str = "queued"          # queued | downloading | merging | done | error
    title: str = ""
    progress: float = 0.0
    speed: float = 0.0
    eta: int | None = None
    file: str = ""
    size: int = 0
    codec: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)


JOBS: dict[str, Job] = {}
ORDER: list[str] = []
LOCK = threading.Lock()
QUEUE: "Queue[tuple[str, str, bool]]" = Queue()


# --------------------------------------------------------------------- tải file


def _sanitize(name: str, limit: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (name or "video")[:limit]


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(2, 1000):
        cand = path.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
    return path.with_name(f"{stem}_{int(time.time())}{suffix}")


def _fetch(url: str, limit: int = 4 << 20) -> tuple[bytes, str, str]:
    """Tải tối đa `limit` byte đầu (đủ để đọc HTML), trả (data, content_type, final_url)."""
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=30) as resp:
        data = resp.read(limit)
        return data, resp.headers.get("Content-Type", ""), resp.geturl()


def _candidate_media_urls(html: str, base: str) -> list[str]:
    patterns = [
        r'<video[^>]+src=["\']([^"\']+)',
        r'<source[^>]+src=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:video(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:video',
        r'"contentUrl"\s*:\s*"([^"]+)"',
        r'"(https?://[^"]+?\.(?:mp4|webm|m3u8|mov)(?:\?[^"]*)?)"',
    ]
    found: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, html, flags=re.I):
            u = urljoin(base, m.group(1).replace("\\/", "/"))
            if u not in found:
                found.append(u)
    return found


def _stream_to_file(url: str, dest: Path, job: Job) -> None:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": url})
    with urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            job.progress = done / total if total else 0.0
            job.size = done


def _download_with_ffmpeg(url: str, dest: Path, job: Job) -> None:
    job.status = "merging"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", url,
           "-c", "copy", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg lỗi: {r.stderr.strip()[:300]}")
    job.size = dest.stat().st_size


def _direct_download(url: str, job: Job) -> Path:
    """Trang web thường: tìm link media trong HTML rồi tải trực tiếp."""
    data, ctype, final_url = _fetch(url)
    if ctype.startswith("video/") or ctype.startswith("application/octet-stream"):
        name = _sanitize(unquote(Path(urlparse(final_url).path).name) or "video.mp4")
        dest = _unique(OUT_DIR / name)
        _stream_to_file(final_url, dest, job)
        return dest

    html = data.decode("utf-8", errors="replace")
    media = _candidate_media_urls(html, final_url)
    if not media:
        raise RuntimeError("không tìm thấy link video trong trang (trang cần đăng nhập?)")

    last_err = None
    for media_url in media[:4]:
        try:
            if media_url.endswith(".m3u8"):
                dest = _unique(OUT_DIR / "hls_video.mp4")
                _download_with_ffmpeg(media_url, dest, job)
                return dest
            name = _sanitize(unquote(Path(urlparse(media_url).path).name) or "video.mp4")
            if Path(name).suffix.lower() not in VIDEO_EXT:
                name += ".mp4"
            dest = _unique(OUT_DIR / name)
            _stream_to_file(media_url, dest, job)
            if dest.stat().st_size > 1024:
                return dest
            dest.unlink(missing_ok=True)
        except Exception as exc:  # thử link kế tiếp
            last_err = exc
    raise RuntimeError(f"tải link media thất bại: {last_err}")


def _find_deno() -> str | None:
    """Tìm deno (JS runtime cho yt-dlp giải challenge của YouTube).

    winget cài vào Packages nhưng không phải lúc nào cũng có shim trên PATH, nên
    dò thêm vài chỗ quen thuộc.
    """
    found = shutil.which("deno")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    home = Path(os.environ.get("USERPROFILE", ""))
    patterns = [
        local / "Microsoft" / "WinGet" / "Packages",
        home / "scoop" / "shims",
        home / ".deno" / "bin",
        Path("C:/Program Files/deno"),
    ]
    for base in patterns:
        if not base.exists():
            continue
        if base.name == "Packages":
            hits = list(base.glob("DenoLand.Deno*/deno.exe"))
        else:
            hits = list(base.glob("deno.exe")) or list(base.glob("deno"))
        if hits:
            return str(hits[0])
    return None


DENO_PATH = _find_deno()


def _ydl_download(url: str, job: Job, cookies: str, overwrite: bool = False) -> Path:
    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            job.status = "downloading"
            job.progress = min(1.0, done / total) if total else 0.0
            job.speed = float(d.get("speed") or 0)
            job.eta = d.get("eta")
            job.size = done
        elif d.get("status") == "finished":
            job.status = "merging"
            job.progress = 1.0

    opts = {
        "outtmpl": {"default": str(OUT_DIR / "%(title).110s [%(id)s].%(ext)s")},
        # Ưu tiên H.264 + AAC: combo AV1/VP9 + Opus trong MP4 làm VLC nháy/khựng
        # vài giây đầu (cảnh báo của ffmpeg: non-standard codec trong mp4).
        "format": (f"bv*[vcodec^=avc1][height<={MAX_HEIGHT}]+ba[acodec^=mp4a]/"
                   f"bv*[vcodec^=avc1][height<={MAX_HEIGHT}]+ba/"
                   f"bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]/b"),
        "format_sort": ["vcodec:h264", "acodec:aac", "res", "fps"],
        "merge_output_format": "mp4",
        # moov lên đầu file: mở/seek mượt hơn trên VLC, TV, điện thoại
        "postprocessor_args": {"merger": ["-movflags", "+faststart"]},
        "noplaylist": True,
        "playlist_items": "1",       # trang có nhiều <video> chỉ lấy cái đầu
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 4,
        "retries": 3,
        "socket_timeout": 30,
    }
    if cookies and cookies != "none":
        opts["cookiesfrombrowser"] = (cookies,)
    if overwrite:
        opts["overwrites"] = True          # tải đè bản cũ (vd. bản AV1/VP9 bị nháy)
    if DENO_PATH:
        # deno + script giải challenge (EJS) giúp YouTube trả đủ format
        opts["js_runtimes"] = {"deno": {"path": DENO_PATH}}
        opts["remote_components"] = ["ejs:github"]

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("_type") == "playlist" and info.get("entries"):
            info = info["entries"][0]
        job.title = info.get("title") or ""
        downloads = info.get("requested_downloads") or []
        path = downloads[0].get("filepath") if downloads else None
        path = path or ydl.prepare_filename(info)
        return Path(path)


def _probe_codec(path: Path) -> str:
    """Chuỗi 'video/audio' để kiểm tra file có dễ phát không."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=codec_type,codec_name", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=20)
        found: dict[str, str] = {}
        for line in r.stdout.splitlines():
            parts = [x.strip() for x in line.split(",") if x.strip()]
            kinds = [p for p in parts if p in ("video", "audio")]
            if not kinds:
                continue
            kind = kinds[0]
            codec = next((p for p in parts if p != kind), "")
            found.setdefault(kind, codec)
        return "/".join(found.get(k, "") for k in ("video", "audio"))
    except Exception:
        return ""


def _newest_video(since: float) -> Path | None:
    """File video mới nhất trong OUT_DIR được tạo sau mốc `since`."""
    if not OUT_DIR.exists():
        return None
    cands = [p for p in OUT_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO_EXT and p.stat().st_mtime >= since - 2]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def _run(job: Job, cookies: str, overwrite: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        path: Path | None = None
        if yt_dlp is not None:
            try:
                path = _ydl_download(job.url, job, cookies, overwrite)
            except Exception as exc:
                job.error = str(exc)[:300]
                path = None
        if path is None or not Path(path).exists():
            # yt-dlp ghép/đổi tên file xong có thể không khớp đường dẫn nó báo
            path = _newest_video(started) or path
        if path is None or not Path(path).exists():
            job.status = "downloading"
            job.error = ""
            path = _direct_download(job.url, job)

        job.file = Path(path).name
        job.size = Path(path).stat().st_size if Path(path).exists() else 0
        job.codec = _probe_codec(Path(path)) if Path(path).exists() else ""
        if job.codec and "/" in job.codec:
            vcodec = job.codec.split("/")[0]
            if vcodec not in ("h264", "hevc"):
                print(f"cảnh báo: {job.file} là {job.codec} — một số player (VLC) có thể "
                      f"nháy vài giây đầu; nên tải lại hoặc remux sang h264.")
        job.progress = 1.0
        job.status = "done"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)[:300] or type(exc).__name__


def _worker() -> None:
    while True:
        job_id, cookies, overwrite = QUEUE.get()
        with LOCK:
            job = JOBS.get(job_id)
        if job is None:
            continue
        try:
            _run(job, cookies, overwrite)
        finally:
            QUEUE.task_done()


# ------------------------------------------------------------------------ HTTP


def _video_files() -> list[dict]:
    if not OUT_DIR.exists():
        return []
    items = [p for p in OUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
            for p in items[:200]]


def _state() -> dict:
    with LOCK:
        jobs = [asdict(JOBS[i]) for i in ORDER if i in JOBS]
    return {"out": str(OUT_DIR.resolve()), "has_ytdlp": yt_dlp is not None,
            "has_deno": DENO_PATH is not None, "deno": DENO_PATH or "",
            "jobs": jobs, "files": _video_files()}


class Handler(BaseHTTPRequestHandler):
    server_version = "luyenCoDownloader/1.0"

    def log_message(self, fmt: str, *args) -> None:  # im lặng khi chạy
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(_state())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json({"error": "JSON không hợp lệ"}, 400)

        if self.path == "/api/download":
            urls = [u.strip() for u in re.split(r"[\r\n]+", str(payload.get("urls", ""))) if u.strip()]
            cookies = str(payload.get("cookies", "none"))
            overwrite = bool(payload.get("overwrite", False))
            if not urls:
                return self._json({"error": "chưa nhập URL"}, 400)
            if len(urls) > 10:
                return self._json({"error": "tối đa 10 URL mỗi lần"}, 400)
            created = []
            for url in urls:
                if urlparse(url).scheme not in ("http", "https"):
                    return self._json({"error": f"URL không hợp lệ: {url}"}, 400)
                job = Job(id=uuid.uuid4().hex[:8], url=url)
                with LOCK:
                    JOBS[job.id] = job
                    ORDER.append(job.id)
                QUEUE.put((job.id, cookies, overwrite))
                created.append(job.id)
            return self._json({"ids": created})

        if self.path == "/api/clear":
            with LOCK:
                for job_id in [i for i in ORDER if JOBS[i].status in ("done", "error")]:
                    JOBS.pop(job_id, None)
                ORDER[:] = [i for i in ORDER if i in JOBS]
            return self._json({"ok": True})

        if self.path == "/api/open":
            try:
                os.startfile(OUT_DIR.resolve())  # noqa: S606 (chỉ Windows, tool local)
            except Exception as exc:
                return self._json({"error": str(exc)}, 500)
            return self._json({"ok": True})

        self._json({"error": "not found"}, 404)


PAGE = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>luyen_co · tải video test</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font: 15px/1.5 "Segoe UI", system-ui, sans-serif;
         background: #14161a; color: #e6e8ec; }
  .wrap { max-width: 900px; margin: 40px auto; padding: 0 18px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: #9aa3af; margin-bottom: 22px; font-size: 13px; }
  .card { background: #1c1f26; border: 1px solid #2a2f3a; border-radius: 10px;
          padding: 16px; margin-bottom: 18px; }
  textarea { width: 100%; box-sizing: border-box; background: #12141a; color: #e6e8ec;
             border: 1px solid #333a47; border-radius: 8px; padding: 10px; min-height: 92px;
             font: 13px/1.5 ui-monospace, Consolas, monospace; resize: vertical; }
  .row { display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
  select, button { background: #232833; color: #e6e8ec; border: 1px solid #333a47;
                   border-radius: 8px; padding: 8px 12px; font-size: 14px; }
  button.primary { background: #2f6feb; border-color: #2f6feb; font-weight: 600; cursor: pointer; }
  button.primary:disabled { opacity: .55; cursor: default; }
  button.ghost { cursor: pointer; }
  .job { border-top: 1px solid #262b35; padding: 12px 0; }
  .job:first-child { border-top: 0; }
  .job .t { display: flex; justify-content: space-between; gap: 12px; }
  .job .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .job .meta { color: #9aa3af; font-size: 12px; white-space: nowrap; }
  .bar { height: 6px; background: #262b35; border-radius: 4px; overflow: hidden; margin-top: 8px; }
  .bar > i { display: block; height: 100%; background: #2f6feb; width: 0; transition: width .3s; }
  .err { color: #ff7b72; font-size: 12px; margin-top: 6px; word-break: break-word; }
  .files { list-style: none; margin: 0; padding: 0; }
  .files li { display: flex; justify-content: space-between; padding: 7px 0;
              border-top: 1px solid #262b35; font-size: 13px; }
  .files li:first-child { border-top: 0; }
  .files .n { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  code { background: #12141a; border: 1px solid #333a47; border-radius: 6px;
         padding: 2px 6px; font-size: 12px; }
  .hint { color: #9aa3af; font-size: 12px; margin-top: 12px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Tải video từ web</h1>
  <div class="sub">Dán link YouTube / TikTok / Facebook / Instagram / trang có video — mỗi dòng một link.
    Tải xong, trỏ <code>luyen_co.py --input downloads</code> vào là quét được.</div>

  <div class="card">
    <textarea id="urls" placeholder="https://www.youtube.com/watch?v=...
https://www.tiktok.com/@user/video/...
https://example.com/trang-co-video"></textarea>
    <div class="row">
      <select id="cookies" title="Dùng cookie trình duyệt cho video cần đăng nhập">
        <option value="none">Không dùng cookie</option>
        <option value="chrome">Cookie Chrome</option>
        <option value="edge">Cookie Edge</option>
        <option value="firefox">Cookie Firefox</option>
      </select>
      <label class="hint" title="Tải đè bản cũ (vd. bản AV1/VP9 bị VLC nháy)"><input type="checkbox"
        id="overwrite"> tải lại/ghi đè</label>
      <button class="primary" id="go">Tải về</button>
      <button class="ghost" id="clear">Xoá danh sách đã xong</button>
      <span id="out" class="hint"></span>
    </div>
  </div>

  <div class="card">
    <div class="sub" style="margin:0 0 8px">Đang tải</div>
    <div id="jobs"></div>
  </div>

  <div class="card">
    <div class="sub" style="margin:0 0 8px">Video đã tải</div>
    <ul class="files" id="files"></ul>
    <div class="hint" id="hint"></div>
  </div>
</div>
<script>
const $ = (id) => document.getElementById(id);
const fmtSize = (b) => b > 1e9 ? (b/1e9).toFixed(2)+' GB'
  : b > 1e6 ? (b/1e6).toFixed(1)+' MB' : Math.round(b/1024)+' KB';
const fmtSpeed = (s) => s > 0 ? (s/1e6).toFixed(1)+' MB/s' : '';
const fmtEta = (s) => s == null ? '' : (s > 60 ? Math.round(s/60)+' phút' : s+' giây');

async function submit() {
  const urls = $('urls').value.trim();
  if (!urls) return;
  $('go').disabled = true;
  try {
    const r = await fetch('/api/download', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({urls, cookies: $('cookies').value, overwrite: $('overwrite').checked})});
    const j = await r.json();
    if (j.error) alert(j.error);
    else $('urls').value = '';
  } finally { $('go').disabled = false; tick(); }
}

async function tick() {
  const s = await (await fetch('/api/state')).json();
  $('out').textContent = 'lưu vào: ' + s.out;
  $('hint').innerHTML = 'Quét bằng: <code>python luyen_co.py --input "' + s.out + '" --ref anh.jpg</code>'
    + (s.has_ytdlp ? '' : '<br>Chưa cài yt-dlp → chỉ tải được link .mp4 trực tiếp.')
    + (s.has_deno ? '<br>deno: đã thấy (' + esc(s.deno) + ')'
                  : '<br>Chưa thấy deno → YouTube có thể thiếu format; cài bằng <code>winget install DenoLand.Deno</code>');

  const jobs = s.jobs.map((j) => {
    const pct = Math.round((j.progress || 0) * 100);
    const label = j.status === 'done' ? 'xong' : j.status === 'error' ? 'lỗi'
      : j.status === 'merging' ? 'đang ghép' : j.status === 'queued' ? 'chờ' : pct + '%';
    const meta = [label, fmtSpeed(j.speed), j.eta ? 'còn ' + fmtEta(j.eta) : '',
                  j.codec].filter(Boolean).join(' · ');
    return `<div class="job">
      <div class="t"><span class="name">${esc(j.title || j.url)}</span>
      <span class="meta">${esc(meta)}</span></div>
      <div class="bar"><i style="width:${j.status === 'error' ? 100 : pct}%;
        background:${j.status === 'error' ? '#ff7b72' : '#2f6feb'}"></i></div>
      ${j.error ? `<div class="err">${esc(j.error)}</div>` : ''}
    </div>`;
  }).join('');
  $('jobs').innerHTML = jobs || '<div class="hint">chưa có gì</div>';

  $('files').innerHTML = s.files.map((f) =>
    `<li><span class="n">${esc(f.name)}</span><span class="meta">${fmtSize(f.size)}</span></li>`
  ).join('') || '<li class="hint">chưa có video nào</li>';
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

$('go').onclick = submit;
$('clear').onclick = async () => { await fetch('/api/clear', {method:'POST'}); tick(); };
$('urls').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit();
});
tick();
setInterval(tick, 1000);
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    global OUT_DIR, MAX_HEIGHT
    p = argparse.ArgumentParser(description="Web UI tải video từ URL về máy (cho luyen_co).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--out", type=Path, default=Path("downloads"), help="thư mục lưu video")
    p.add_argument("--max-height", type=int, default=1080, help="giới hạn độ phân giải tải về")
    p.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    args = p.parse_args(argv)

    OUT_DIR = args.out
    MAX_HEIGHT = args.max_height
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    threading.Thread(target=_worker, daemon=True).start()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"luyen_co download UI: {url}  ·  lưu vào {OUT_DIR.resolve()}")
    print("deno: " + (DENO_PATH or "CHƯA THẤY — YouTube sẽ thiếu format (winget install DenoLand.Deno)"))
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndừng.")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
