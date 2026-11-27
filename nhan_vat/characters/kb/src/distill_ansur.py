"""ANSUR II (US Army 2012, PROXY): correlations between body measures as weak compatibility hints.
Reads the two public CSVs as text. Writes evidence/num/ansur_corr.csv and stats.json -> "ansur".

    python -I distill_ansur.py [data_root]"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
D = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/khoa/data/nhan_vat_sources") / "08_ansur2"
FILES = {"male": D / "ANSUR_II_MALE_Public.csv", "female": D / "ANSUR_II_FEMALE_Public.csv"}
MEAS = ["biacromialbreadth", "bideltoidbreadth", "hipbreadth", "chestcircumference", "waistcircumference", "wristcircumference",
        "neckcircumference", "span", "handlength", "footlength", "sittingheight", "thighcircumference", "calfcircumference",
        "buttockcircumference"]


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x) / (n - 1))
    sy = math.sqrt(sum((b - my) ** 2 for b in y) / (n - 1))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / ((n - 1) * sx * sy)


def z(xs):
    m = sum(xs) / len(xs)
    s = math.sqrt(sum((a - m) ** 2 for a in xs) / (len(xs) - 1))
    return [(a - m) / s for a in xs]


def main():
    rows_out, st = [], {"basis": "proxy", "note": "US Army personnel 2012 (selected, fit adults); compatibility hints only", "by": {}}
    for sex, p in FILES.items():
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        rows = list(csv.DictReader(raw.decode("latin-1").splitlines()))
        stat = [float(r["stature"]) for r in rows]
        bmi = [float(r["weightkg"]) / 10 / (float(r["stature"]) / 1000) ** 2 for r in rows]
        res = {}
        for m in MEAS:
            v = [float(r[m]) for r in rows]
            res[f"stature~{m}"] = pearson(stat, v)
            res[f"bmi~{m}"] = pearson(bmi, v)
        rel_sit = [float(r["sittingheight"]) / float(r["stature"]) for r in rows]
        res["stature~sitting_ratio"] = pearson(stat, rel_sit)
        res["bmi~waist_to_height"] = pearson(bmi, [float(r["waistcircumference"]) / float(r["stature"]) for r in rows])
        res["stature~bmi"] = pearson(stat, bmi)
        # conditional shares (within-sex z): broad shoulders among the shortest tenth, etc.
        zs, zb, zw, zh = z(stat), z([float(r["biacromialbreadth"]) for r in rows]), z([float(r["wristcircumference"]) for r in rows]), \
            z([float(r["hipbreadth"]) for r in rows])
        zbmi, zwaist = z(bmi), z([float(r["waistcircumference"]) for r in rows])

        def cond(a, alo, ahi, b, blo, bhi):
            sel = [j for j in range(len(rows)) if alo <= a[j] < ahi]
            return round(sum(blo <= b[j] < bhi for j in sel) / max(1, len(sel)), 3), len(sel)
        res_c = {
            "P(shoulders z>=1.28 | stature z<-1.28)": cond(zs, -9, -1.28, zb, 1.28, 9),
            "P(shoulders z>=1.28 | all)": cond(zs, -9, 9, zb, 1.28, 9),
            "P(shoulders z<-1.28 | stature z>=1.28)": cond(zs, 1.28, 9, zb, -9, -1.28),
            "P(wrist z>=1.28 | stature z<-1.28)": cond(zs, -9, -1.28, zw, 1.28, 9),
            "P(hips z>=1.28 | stature z<-1.28)": cond(zs, -9, -1.28, zh, 1.28, 9),
            "P(waist z>=1.28 | bmi z<-1)": cond(zbmi, -9, -1, zwaist, 1.28, 9),
            "P(waist z<-1.28 | bmi z>=1)": cond(zbmi, 1, 9, zwaist, -9, -1.28),
        }
        st["by"][sex] = {"n": len(rows), "sha256": sha, "r": {k: round(v, 3) for k, v in res.items()},
                         "conditional": {k: v[0] for k, v in res_c.items()}}
        for k, v in res.items():
            rows_out.append([p.name, sha[:16], sex, len(rows), "pearson_r", k, round(v, 3)])
        for k, (v, n) in res_c.items():
            rows_out.append([p.name, sha[:16], sex, n, "share", k, v])
    with open(KB / "evidence" / "num" / "ansur_corr.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256", "sex", "n", "stat", "pair", "value"])
        w.writerows(rows_out)
    sp = KB / "stats.json"
    s = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    s["ansur"] = st
    sp.write_text(json.dumps(s, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    for sex in st["by"]:
        print(sex, json.dumps(st["by"][sex]["r"]), json.dumps(st["by"][sex]["conditional"]))


if __name__ == "__main__":
    main()
