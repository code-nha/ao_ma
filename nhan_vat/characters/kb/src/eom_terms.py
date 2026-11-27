"""List NIH Elements of Morphology term pages (untrusted HTML, text only): label, region, synonyms, file.
    python -I eom_terms.py <06_nih_elements_morphology dir> > out.jsonl"""
import hashlib
import html
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.stdout.reconfigure(encoding="utf-8")
for d in sorted(p for p in root.iterdir() if p.is_dir()):
    for f in sorted(d.glob("term_*.html")):
        raw = f.read_bytes()
        t = raw.decode("utf-8", "replace")
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
        t = re.sub(r"<[^>]+>", "\n", t)
        t = html.unescape(t)
        lines = [x.strip() for x in t.splitlines() if x.strip()]
        try:
            i = lines.index("Definition:")
        except ValueError:
            continue
        label = lines[i - 1]
        syn = []
        for j, x in enumerate(lines):
            if x.startswith("Synonym"):
                syn = [s.strip() for s in re.split(r";", lines[j + 1]) if s.strip()][:8]
                break
        print(json.dumps({"label": label, "region": d.name, "synonyms": syn, "file": f"{d.name}/{f.name}",
                          "sha256": hashlib.sha256(raw).hexdigest()}, ensure_ascii=False))
