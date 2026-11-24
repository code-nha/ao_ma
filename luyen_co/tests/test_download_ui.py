"""Test các hàm thuần của download_ui (không cần mạng)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import download_ui as du


def test_sanitize_strips_bad_chars():
    assert du._sanitize('a<b>c:d/e\\f|g?h*i.mp4') == "a_b_c_d_e_f_g_h_i.mp4"
    assert du._sanitize("   ") == "video"
    assert len(du._sanitize("x" * 300)) == 120


def test_unique_appends_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(du, "OUT_DIR", tmp_path)
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"x")
    assert du._unique(p).name == "clip_2.mp4"


def test_candidate_media_urls():
    html = """
    <html><head><meta property="og:video" content="/media/og.mp4"></head>
    <body>
      <video src="https://cdn.example.com/a.mp4"></video>
      <video><source src="/files/b.webm"></video>
      <script>var x = {"contentUrl": "https://cdn.example.com/c.mp4"};</script>
      <a href="https://cdn.example.com/d.m3u8">hls</a>
    </body></html>
    """
    urls = du._candidate_media_urls(html, "https://example.com/page")
    assert "https://cdn.example.com/a.mp4" in urls
    assert "https://example.com/files/b.webm" in urls
    assert "https://example.com/media/og.mp4" in urls
    assert "https://cdn.example.com/c.mp4" in urls
    assert "https://cdn.example.com/d.m3u8" in urls
    assert len(urls) == len(set(urls))


def test_candidate_media_urls_empty():
    assert du._candidate_media_urls("<html>không có gì</html>", "https://x.test/") == []


def test_looks_like_media():
    assert du._looks_like_media("https://cdn.test/v.mp4?x=1") is True
    assert du._looks_like_media("https://cdn.test/v.MOV") is True
    assert du._looks_like_media("https://www.facebook.com/stories/123/") is False
    assert du._looks_like_media("https://youtu.be/abc") is False


def test_strip_byte_range():
    raw = "https://cdn.test/o1/v.mp4?_nc_cat=102&bytestart=0&byteend=1067&x=1"
    assert du._strip_byte_range(raw) == "https://cdn.test/o1/v.mp4?_nc_cat=102&x=1"
    same = "https://cdn.test/o1/v.mp4?_nc_cat=102&x=1"
    assert du._strip_byte_range(same) == same
    assert du._strip_byte_range("https://cdn.test/v.mp4") == "https://cdn.test/v.mp4"
