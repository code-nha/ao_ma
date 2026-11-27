"""Cho Gemma đóng nhân vật tự viết STYLE rồi LOOK, theo characters/SPEC.md.

    python -I char_style_look.py lao_bay [--api http://wee:11435] [--model gemma4:26b]

Đọc characters/<id>/{IDENTITY,SOUL,LIFE}.md. Gọi 1: viết STYLE. Gọi 2: viết LOOK (đọc thêm STYLE vừa viết).
Ghi <id>/STYLE.gemma.md, <id>/LOOK.gemma.md (không đè bản nháp) và logs/style_look.jsonl.
Máy wee dùng chung: tuần tự, không gửi num_ctx / keep_alive.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARS = ROOT / "characters"


def opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


API = opt("--api", "http://wee:11435") + "/api/chat"
MODEL = opt("--model", "gemma4:26b")
CID = sys.argv[1] if len(sys.argv) > 1 else "lao_bay"

# Model input is English (small models are weak in Vietnamese); the Vietnamese .md files are for the user.
SPEC = (CHARS / "SPEC.en.md").read_text(encoding="utf-8")
STYLE_SPEC = SPEC.split("## STYLE")[1].split("## LOOK")[0].strip()
LOOK_SPEC = SPEC.split("## LOOK")[1].strip()

SYS_STYLE = f"""You play the character below and decide your own STYLE. You may read your own IDENTITY, SOUL and LIFE.
Write STYLE in the first person, following this spec:

## STYLE {STYLE_SPEC}

Format as Markdown: heading "# STYLE", then the groups Speech, Appearance habits, Body language, Habits, Other; one bullet per line in
the form "when ... -> ...". Write in English, except sample spoken lines, which are in your own language and in double quotes.
Use exactly the forms of address you choose for yourself, consistently."""

SYS_LOOK = f"""You play the character below and build your own LOOK. You may read your own IDENTITY, SOUL, LIFE and STYLE.
Think privately about how your life has shaped your body, but write ONLY the visible appearance, following this spec:

## LOOK {LOOK_SPEC}

Format as Markdown: heading "# LOOK", then the sections Stature, Face, Hair, Torso, Arms and hands, Legs and feet, Posture, Marks;
a few short English phrases per section, third person, objective."""


def read(name):
    return (CHARS / CID / f"{name}.en.md").read_text(encoding="utf-8").strip()


def call(system, user):
    body = {"model": MODEL, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.7, "num_predict": 2500}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.loads(r.read())
    return out["message"]["content"].strip(), {"secs": round(time.time() - t, 1),
                                               "prompt_tokens": out.get("prompt_eval_count"), "eval_tokens": out.get("eval_count")}


def main():
    base = "\n\n".join(read(n) for n in ("IDENTITY", "SOUL", "LIFE"))
    style, s1 = call(SYS_STYLE, base)
    (CHARS / CID / "STYLE.gemma3.md").write_text(style + "\n", encoding="utf-8")
    print("STYLE", s1, flush=True)
    look, s2 = call(SYS_LOOK, base + "\n\n" + style)
    (CHARS / CID / "LOOK.gemma3.md").write_text(look + "\n", encoding="utf-8")
    print("LOOK", s2, flush=True)
    (ROOT / "experiments" / "logs").mkdir(exist_ok=True)
    with (ROOT / "experiments" / "logs" / "style_look.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "char": CID, "model": MODEL,
                             "style": style, "look": look, "stats": [s1, s2]}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
