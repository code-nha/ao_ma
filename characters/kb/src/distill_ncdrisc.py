"""Distill NCD-RisC height (adult by birth year; age 19 by year) and BMI (age-specific, 2024) for Viet Nam and
neighbours into numeric evidence + kb/stats.json. Reads CSV text only (downloaded files are untrusted data).

    python -I distill_ncdrisc.py [data_root]      (default C:/Users/khoa/data/nhan_vat_sources)

Writes (relative to kb/):
  evidence/num/ncdrisc_height_adult.csv   rows copied for the ISO codes below (birth years 1896-1996)
  evidence/num/ncdrisc_height_age19.csv   age-19 rows, years 1985-2019 (birth cohorts 1966-2000)
  evidence/num/ncdrisc_bmi_vn.csv         Viet Nam BMI category prevalence by sex x 5-year age group, 2000 and 2024
  evidence/num/height_bands.csv           derived: mean + z-band cut-offs (cm) per eth x sex x birth decade
  stats.json -> "height", "bmi" sections (merged; other sections kept)
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/khoa/data/nhan_vat_sources") / "01_ncdrisc"
F_ADULT = ROOT / "NCD_RisC_eLife_2016_height_age18_countries.csv"
F_19 = ROOT / "NCD_RisC_Lancet_2020_height_child_adolescent_country" / "NCD_RisC_Lancet_2020_height_child_adolescent_country.csv"
F_BMI = {s: ROOT / f"NCD_RisC_Nature_2026_BMI_{s}_age_specific_country" / f"NCD_RisC_Nature_2026_BMI_{s}_age_specific_country.csv"
         for s in ("male", "female")}
GROUPS = {"kinh": ["VNM"], "sea-asian": ["THA", "LAO", "KHM", "MMR", "MYS", "PHL", "IDN", "TLS"], "east-asian": ["CHN", "JPN", "KOR"]}
NAME19 = {"Viet Nam": "VNM", "Thailand": "THA", "Lao PDR": "LAO", "Cambodia": "KHM", "Myanmar": "MMR", "Malaysia": "MYS",
          "Philippines": "PHL", "Indonesia": "IDN", "Timor-Leste": "TLS", "China": "CHN", "Japan": "JPN", "South Korea": "KOR"}
ISOS = {i for v in GROUPS.values() for i in v}
# within-population SD of adult height (cm): proxy, see README of stats / report.md
SD = {"male": 6.5, "female": 6.0}
SD_NOTE = ("proxy: ANSUR II all-subject stature SD 6.86 (men) / 6.42 (women), rounded down for an unselected population; "
           "STEPS VN 2015/2021 height CIs bound SD at <=6.8-8.4 before design effect")
# z bands for height values (same sex x birth cohort x population)
ZB = {"very-short": [-9, -2.0], "short": [-2.0, -1.0], "normal": [-1.0, 1.0], "tall": [1.0, 2.0], "very-tall": [2.0, 9]}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def wcsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    out = KB / "evidence" / "num"
    sh_a, sh_19 = sha(F_ADULT), sha(F_19)
    # ---- adult height by birth year
    adult = {}
    rows = []
    with open(F_ADULT, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["ISO"] in ISOS:
                sex = "male" if r["Sex"] == "Men" else "female"
                y = int(r["Year of birth"])
                m = float(r["Mean height (cm)"])
                adult[(r["ISO"], sex, y)] = m
                rows.append([F_ADULT.name, sh_a, r["Country"], r["ISO"], sex, y, round(m, 2),
                             round(float(r["Mean height lower 95% uncertainty interval (cm)"]), 2),
                             round(float(r["Mean height upper 95% uncertainty interval (cm)"]), 2)])
    wcsv(out / "ncdrisc_height_adult.csv", ["file", "sha256", "country", "iso", "sex", "birth_year", "mean_cm", "lo95", "hi95"], rows)
    # ---- age 19 by year -> birth cohort year-19
    a19 = {}
    rows = []
    with open(F_19, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            iso = NAME19.get(r["Country"])
            if iso and r["Age group"] == "19":
                sex = "male" if r["Sex"] == "Boys" else "female"
                y = int(r["Year"])
                m = float(r["Mean height"])
                a19[(iso, sex, y - 19)] = m
                rows.append([F_19.name, sh_19, r["Country"], iso, sex, y, 19, y - 19, round(m, 2),
                             round(float(r["Mean height lower 95% uncertainty interval"]), 2),
                             round(float(r["Mean height upper 95% uncertainty interval"]), 2)])
    wcsv(out / "ncdrisc_height_age19.csv", ["file", "sha256", "country", "iso", "sex", "year", "age", "birth_year", "mean_cm",
                                            "lo95", "hi95"], rows)
    # ---- combined cohort series: adult (<=1996), age-19 + overlap offset (1997-2000)
    series = {}
    offsets = {}
    for iso in ISOS:
        for sex in ("male", "female"):
            ov = [adult[(iso, sex, y)] - a19[(iso, sex, y)] for y in range(1987, 1997) if (iso, sex, y) in adult and (iso, sex, y) in a19]
            off = sum(ov) / len(ov) if ov else 0.0
            offsets[(iso, sex)] = off
            for y in range(1896, 2001):
                if (iso, sex, y) in adult:
                    series[(iso, sex, y)] = adult[(iso, sex, y)]
                elif (iso, sex, y) in a19:
                    series[(iso, sex, y)] = a19[(iso, sex, y)] + off
    # ---- bands per eth x sex x birth decade (decade mean of yearly means, group = unweighted country mean)
    stats_h = {"sd": SD, "sd_note": SD_NOTE, "z_bands": ZB, "by": {}, "basis": "stat (means) + proxy (SD)",
               "src": {"adult": f"{F_ADULT.name} sha256 {sh_a[:12]}", "age19": f"{F_19.name} sha256 {sh_19[:12]}",
                       "offset_1997_2000": {f"{i}/{s}": round(o, 2) for (i, s), o in sorted(offsets.items()) if i == "VNM"}}}
    brows = []
    for eth, isos in GROUPS.items():
        for sex in ("male", "female"):
            for dec in range(1900, 2001, 10):
                ys = range(dec, min(dec + 10, 2001))
                per = [sum(series[(i, sex, y)] for y in ys if (i, sex, y) in series) / max(1, sum((i, sex, y) in series for y in ys))
                       for i in isos]
                mean = sum(per) / len(per)
                sd = SD[sex]
                cuts = {b: [round(mean + lo * sd, 1) if lo > -9 else None, round(mean + hi * sd, 1) if hi < 9 else None]
                        for b, (lo, hi) in ZB.items()}
                stats_h["by"][f"{eth}/{sex}/{dec}"] = {"mean": round(mean, 1), "sd": sd, "bands": cuts}
                brows.append([eth, sex, f"{dec}s", round(mean, 1), sd] + [cuts[b][0] if cuts[b][0] else "" for b in
                                                                         ("short", "normal", "tall", "very-tall")])
    wcsv(out / "height_bands.csv", ["eth", "sex", "birth_decade", "mean_cm", "sd_cm", "short_from", "normal_from", "tall_from",
                                    "very_tall_from"], brows)
    # ---- BMI Viet Nam (and SEA mean) by sex x age group, 2000 and 2024
    cats = [("lt18.5", "Prevalence of BMI<18.5 kg/m² (underweight)"), ("18.5-20", "Prevalence of BMI 18.5 kg/m² to <20 kg/m²"),
            ("20-25", "Prevalence of BMI 20 kg/m² to <25 kg/m²"), ("25-30", "Prevalence of BMI 25 kg/m² to <30 kg/m²"),
            ("30-35", "Prevalence of BMI 30 kg/m² to <35 kg/m²"), ("35-40", "Prevalence of BMI 35 kg/m² to <40 kg/m²"),
            ("ge40", "Prevalence of BMI >=40 kg/m² (morbid obesity)")]
    rows = []
    bmi = {}
    for sex, p in F_BMI.items():
        sh = sha(p)
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["ISO"] in ISOS and r["Year"] in ("2000", "2024"):
                    vals = {k: float(r[c]) for k, c in cats}
                    bmi[(r["ISO"], sex, r["Year"], r["Age group"])] = vals
                    if r["ISO"] == "VNM":
                        rows.append([p.name, sh, r["ISO"], sex, r["Year"], r["Age group"]] + [round(vals[k], 4) for k, _ in cats])
    wcsv(out / "ncdrisc_bmi_vn.csv", ["file", "sha256", "iso", "sex", "year", "age_group"] + [k for k, _ in cats], rows)
    bands = {"young": ["18-19", "20-24", "25-29"], "adult": ["30-34", "35-39", "40-44"],
             "middle": ["45-49", "50-54", "55-59", "60-64"], "elderly": ["65-69", "70-74", "75-79", "80-84", "85plus"]}
    stats_b = {"note": "share of people by BMI class, unweighted mean of 5-year age groups in the band; NCD-RisC Nature 2026",
               "by": {}}
    for eth, isos in (("kinh", ["VNM"]), ("sea-asian", GROUPS["sea-asian"])):
        for sex in ("male", "female"):
            for year in ("2000", "2024"):
                for band, ags in bands.items():
                    acc = {k: 0.0 for k, _ in cats}
                    n = 0
                    for i in isos:
                        for ag in ags:
                            v = bmi.get((i, sex, year, ag))
                            if v:
                                n += 1
                                for k in acc:
                                    acc[k] += v[k]
                    stats_b["by"][f"{eth}/{sex}/{year}/{band}"] = {k: round(x / n, 4) for k, x in acc.items()}
    sp = KB / "stats.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    st["height"] = stats_h
    st["bmi"] = stats_b
    sp.write_text(json.dumps(st, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    for k in ("kinh/male/1950", "kinh/male/2000", "kinh/female/1950", "kinh/female/2000", "sea-asian/male/2000"):
        print(k, stats_h["by"][k]["mean"], stats_h["by"][k]["bands"]["tall"])
    for k in ("kinh/male/2024/young", "kinh/male/2024/elderly", "kinh/female/2024/middle"):
        print(k, stats_b["by"][k])


if __name__ == "__main__":
    main()
