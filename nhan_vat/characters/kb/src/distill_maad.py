"""MAAD-Face attribute marginals and co-occurrence (PROXY only: celebrity faces from VGGFace2, Western-biased labels).
Streams the 481 MB CSV (text only, no pickle), aggregates per identity (an attribute is 'on' for a person when the mean of
their non-zero image labels is > 0), then:
  evidence/num/maad_marginals.csv   share of identities with each attribute by sex x age label x race label
  evidence/num/maad_cooc.csv        pairwise lift P(a&b)/(P(a)P(b)) for physical attributes (all identities and Asian)
  stats.json -> "maad" (Asian + all marginals for mapped attributes; low-lift pairs = exclusion-rule candidates)

    python -I distill_maad.py [data_root]
Never use these numbers as Vietnamese frequencies (basis=proxy)."""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
F = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/khoa/data/nhan_vat_sources") / "10_maad_face" / "MAAD_Face.csv"
PHYS = ["Rosy_Cheeks", "Shiny_Skin", "Bald", "Wavy_Hair", "Receding_Hairline", "Black_Hair", "Blond_Hair", "Brown_Hair",
        "Gray_Hair", "No_Beard", "Mustache", "5_o_Clock_Shadow", "Goatee", "Oval_Face", "Square_Face", "Round_Face", "Double_Chin",
        "High_Cheekbones", "Chubby", "Brown_Eyes", "Bags_Under_Eyes", "Bushy_Eyebrows", "Arched_Eyebrows", "Big_Lips", "Big_Nose",
        "Pointy_Nose", "Sideburns"]
GROUP = ["Male", "Young", "Middle_Aged", "Senior", "Asian", "White", "Black"]


def main():
    h = hashlib.sha256()
    sums = defaultdict(lambda: [0] * 47)
    cnts = defaultdict(lambda: [0] * 47)
    with open(F, "rb") as fb:
        for b in iter(lambda: fb.read(1 << 22), b""):
            h.update(b)
    sha = h.hexdigest()
    with open(F, encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        head = next(r)
        attrs = head[2:]
        n_img = 0
        for row in r:
            n_img += 1
            s, c = sums[row[1]], cnts[row[1]]
            for i, x in enumerate(row[2:]):
                if x != "0":
                    s[i] += 1 if x == "1" else -1
                    c[i] += 1
    idx = {a: i for i, a in enumerate(attrs)}
    people = []
    for pid, s in sums.items():
        c = cnts[pid]
        people.append({a: (None if c[i] == 0 else s[i] > 0) for a, i in idx.items()})

    def grp(p):
        sex = "male" if p["Male"] else "female"
        age = max(("Young", "Middle_Aged", "Senior"), key=lambda a: (p[a] is True, a == "Middle_Aged"))
        race = next((x for x in ("Asian", "Black", "White") if p[x]), "other")
        return sex, {"Young": "young", "Middle_Aged": "middle", "Senior": "senior"}[age], race

    out = KB / "evidence" / "num"
    tab = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for p in people:
        sex, age, race = grp(p)
        for key in (("all", "all", "all"), (sex, "all", "all"), (sex, age, "all"), (sex, "all", race), (sex, age, race)):
            for a in PHYS:
                if p[a] is not None:
                    tab[key][a][1] += 1
                    tab[key][a][0] += p[a]
    with open(out / "maad_marginals.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256", "sex", "age_label", "race_label", "attribute", "n_identities", "share"])
        for key in sorted(tab):
            for a in PHYS:
                on, n = tab[key][a]
                if n >= 20:
                    w.writerow([F.name, sha[:16], *key, a, n, round(on / n, 4)])

    def cooc(sel):
        ps = [p for p in people if sel(p)]
        res = []
        for i, a in enumerate(PHYS):
            for b in PHYS[i + 1:]:
                both = [p for p in ps if p[a] is not None and p[b] is not None]
                if len(both) < 50:
                    continue
                pa = sum(p[a] for p in both) / len(both)
                pb = sum(p[b] for p in both) / len(both)
                pab = sum(p[a] and p[b] for p in both) / len(both)
                if pa > 0 and pb > 0:
                    res.append((a, b, len(both), round(pa, 4), round(pb, 4), round(pab, 4), round(pab / (pa * pb), 3)))
        return res

    rows_all = cooc(lambda p: True)
    rows_asian = cooc(lambda p: p["Asian"])
    with open(out / "maad_cooc.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256", "subset", "a", "b", "n", "p_a", "p_b", "p_ab", "lift"])
        for sub, rows in (("all", rows_all), ("asian", rows_asian)):
            for x in rows:
                w.writerow([F.name, sha[:16], sub, *x])
    low = [x for x in rows_all if x[6] < 0.25 and x[3] >= 0.03 and x[4] >= 0.03]
    sp = KB / "stats.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    st["maad"] = {"basis": "proxy", "note": "VGGFace2 celebrities, identity-level labels; not Vietnamese frequencies",
                  "file": F.name, "sha256": sha, "images": n_img, "identities": len(people),
                  "asian_identities": sum(1 for p in people if p["Asian"]),
                  "share": {f"{'/'.join(k)}": {a: round(v[0] / v[1], 3) for a, v in d.items() if v[1] >= 20}
                            for k, d in tab.items() if k[1] == "all" and k[2] in ("all", "Asian")},
                  "low_lift_pairs": sorted([[a, b, lift] for a, b, n, pa, pb, pab, lift in low], key=lambda x: x[2])}
    sp.write_text(json.dumps(st, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print("images", n_img, "identities", len(people), "asian", st["maad"]["asian_identities"])
    for x in st["maad"]["low_lift_pairs"][:30]:
        print(x)


if __name__ == "__main__":
    main()
