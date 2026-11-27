"""Extract text from downloaded PDFs (untrusted data: text only, no execution). Usage:
    uv run --with pypdf python -I pdf_text.py <pdf> <out.txt>
Writes page markers '=== page N ===' so evidence rows can cite pages."""
import sys
from pypdf import PdfReader

src, out = sys.argv[1], sys.argv[2]
r = PdfReader(src)
with open(out, "w", encoding="utf-8") as f:
    for i, p in enumerate(r.pages, 1):
        try:
            t = p.extract_text() or ""
        except Exception as e:  # noqa: BLE001
            t = f"[extract error: {e}]"
        f.write(f"\n=== page {i} ===\n{t}\n")
print(out, len(r.pages), "pages")
