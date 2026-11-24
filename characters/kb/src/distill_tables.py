"""Numbers transcribed from PDF text (pdf_text.py output) of WHO STEPS Viet Nam 2015/2021 and the two Kinh face papers.
Each row carries file, sha256, table and PDF page so a reviewer can re-check it. Writes:
  evidence/num/steps_vn.csv, evidence/num/kinh_face.csv, stats.json -> "steps", "kinh_face"

    python -I distill_tables.py [data_root]"""
import csv
import hashlib
import json
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
D = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/khoa/data/nhan_vat_sources")
S21 = D / "02_who_steps_vn" / "WHO_STEPS_VietNam_2021_report_9789290620266.pdf"
S15 = D / "02_who_steps_vn" / "WHO_STEPS_VietNam_2015_report.pdf"
K23 = D / "03_kinh_face_papers" / "TCNCYH_2023_nhan_trac_dau_mat_nguoi_Kinh_18-25_art1358.pdf"
V21 = D / "03_kinh_face_papers" / "VMJ_kich_thuoc_khuon_mat_theo_dang_mat_Kinh_18-25_BinhDuong_vnras-34482.pdf"
AG = ["18-29", "30-49", "50-69", "18-69"]

# (file, table, pdf page, measure, sex, group, value) ; BMI class shares in %
STEPS = []


def add(f, table, page, measure, sex, groups, vals):
    for g, v in zip(groups, vals):
        STEPS.append((f, table, page, measure, sex, g, v))


for sex, rows in (("male", [(206, 11.6, 73.1, 11.6, 3.7), (779, 6.9, 72.1, 19.2, 1.8), (850, 10.3, 69.0, 19.8, 1.0), (1835, 9.1, 71.5, 17.2, 2.1)]),
                  ("female", [(199, 20.8, 62.3, 14.3, 2.6), (805, 5.3, 76.6, 16.2, 1.9), (878, 6.3, 68.9, 22.7, 2.2), (1882, 9.7, 70.6, 17.5, 2.2)])):
    for g, (n, u, nw, ow, ob) in zip(AG, rows):
        for m, v in (("n", n), ("bmi_lt18.5_pct", u), ("bmi_18.5-25_pct", nw), ("bmi_25-30_pct", ow), ("bmi_ge30_pct", ob)):
            STEPS.append((S21, "Table 32", 46, m, sex, g, v))
for sex, rows in (("male", [(220, 16.2, 72.9, 9.4, 1.5), (610, 5.9, 76.8, 15.4, 1.9), (486, 11.9, 72.0, 14.3, 1.8), (1316, 10.7, 74.4, 13.2, 1.7)]),
                  ("female", [(251, 20.9, 70.5, 7.8, 0.8), (868, 8.1, 73.9, 17.0, 1.0), (602, 10.4, 66.8, 18.9, 3.9), (1721, 12.6, 71.0, 14.7, 1.7)])):
    for g, (n, u, nw, ow, ob) in zip(AG, rows):
        for m, v in (("n", n), ("bmi_lt18.5_pct", u), ("bmi_18.5-25_pct", nw), ("bmi_25-30_pct", ow), ("bmi_ge30_pct", ob)):
            STEPS.append((S15, "Table 39", 59, m, sex, g, v))
add(S21, "Table A25", 85, "height_cm", "male", AG, [165.8, 164.1, 161.9, 164.0])
add(S21, "Table A25", 85, "height_cm", "female", AG, [155.0, 153.2, 152.0, 153.4])
add(S21, "Table A25", 85, "weight_kg", "male", AG, [60.6, 61.1, 58.4, 60.2])
add(S21, "Table A25", 85, "weight_kg", "female", AG, [51.8, 53.4, 53.3, 53.0])
add(S21, "Table A26", 85, "bmi_mean", "male", AG, [22.0, 22.7, 22.3, 22.4])
add(S21, "Table A26", 85, "bmi_mean", "female", AG, [21.6, 22.7, 23.0, 22.5])
add(S21, "Table A27", 86, "waist_cm", "male", AG, [77.8, 81.2, 81.7, 80.4])
add(S21, "Table A27", 86, "waist_cm", "female", AG, [72.8, 76.2, 81.0, 76.6])
add(S21, "Table A27", 86, "waist_over_cutoff_pct", "male", AG, [8.6, 16.6, 18.6, 14.9])
add(S21, "Table A27", 86, "waist_over_cutoff_pct", "female", AG, [11.4, 15.1, 33.3, 19.8])
add(S21, "Table A28", 86, "hip_cm", "male", AG, [91.7, 92.5, 91.5, 92.0])
add(S21, "Table A28", 86, "hip_cm", "female", AG, [89.5, 91.0, 91.7, 90.8])
add(S21, "Table 55", 61, "bmi_ge25_pct_2021", "both", ["rural", "urban", "18-69"], [16.7, 24.2, 19.5])
add(S21, "Table 55", 61, "bmi_ge25_pct_2015", "both", ["rural", "urban", "18-69"], [12.6, 21.4, 15.6])
add(S15, "Table 83 (annex 8)", 105, "height_cm", "male", AG, [163.7, 162.0, 161.4, 162.4])
add(S15, "Table 83 (annex 8)", 105, "height_cm", "female", AG, [154.2, 152.5, 150.9, 152.6])
add(S15, "Table 84", 106, "waist_cm", "male", AG, [74.5, 78.8, 80.6, 77.8])
add(S15, "Table 84", 106, "waist_cm", "female", AG, [71.4, 76.1, 79.2, 75.5])
add(S15, "Table 41", 60, "bmi_ge25_pct", "male", ["urban", "rural"], [22.1, 11.2])
add(S15, "Table 41", 60, "bmi_ge25_pct", "female", ["urban", "rural"], [20.6, 14.0])
add(S15, "Table 87", 107, "height_cm", "male", ["urban", "rural"], [163.0, 162.1])
add(S15, "Table 87", 107, "height_cm", "female", ["urban", "rural"], [153.1, 152.3])
add(S15, "Table 89", 107, "waist_cm", "male", ["urban", "rural"], [80.4, 76.5])
add(S15, "Table 89", 107, "waist_cm", "female", ["urban", "rural"], [76.8, 74.7])
add(S15, "Table 90", 108, "bmi_mean", "male", ["urban", "rural"], [22.7, 21.7])
add(S15, "Table 90", 108, "bmi_mean", "female", ["urban", "rural"], [22.4, 21.7])
for sex, u, r in (("male", (9.3, 68.6, 20.1, 2.0), (11.4, 77.4, 9.6, 1.6)), ("female", (9.6, 69.7, 18.2, 2.5), (14.2, 71.8, 12.7, 1.3))):
    for g, vals in (("urban", u), ("rural", r)):
        for m, v in zip(("bmi_lt18.5_pct", "bmi_18.5-25_pct", "bmi_25-30_pct", "bmi_ge30_pct"), vals):
            STEPS.append((S15, "Table 91", 109, m, sex, g, v))

# Kinh face (TCNCYH 162(1) 2023, n = 3068 men, 4308 women, age 18-25, Ha Noi + Binh Duong); class shares in %
FACE = []
for idx, table, page, classes, m, f in (
        ("cephalic", "Bang 2", 5, ["very_long<71", "long71-76", "medium76-81", "short81-86", "very_short>86"],
         [0.65, 3.52, 21.58, 33.93, 40.32], [0.56, 3.02, 14.86, 36.84, 44.73]),
        ("facial_total", "Bang 3", 5, ["very_wide<80", "wide80-85", "medium85-90", "long90-95", "very_long>95"],
         [44.88, 36.05, 13.1, 3.88, 2.09], [26.49, 30.01, 32.71, 8.1, 2.69]),
        ("nasal", "Bang 4", 5, ["hyper_narrow<40", "very_narrow40-55", "narrow55-70", "medium70-85", "wide85-100", "very_wide100-115",
                                "hyper_wide>115"], [0, 0.03, 9, 43, 35.56, 9.49, 2.87], [0, 0.95, 26, 46, 21, 4.57, 1.32]),
        ("prognathism", "Bang 5", 6, ["none<109", "prognathic109-113", "very>113"], [91.13, 6.19, 2.67], [87.16, 6.43, 6.41]),
        ("mandibular", "Bang 6", 6, ["narrow<76", "medium76-78", "wide>78"], [4.37, 2.71, 92.93], [0.49, 1.07, 98.44])):
    for c, a, b in zip(classes, m, f):
        FACE.append((K23, table, page, idx, c, "male", a))
        FACE.append((K23, table, page, idx, c, "female", b))
MEAS = [("head_circumference_mm", 554.77, 541.70), ("head_breadth_mm", 152.25, 148.93), ("head_length_mm", 180.84, 174.59),
        ("face_breadth_zy_mm", 138.59, 131.24), ("mandible_breadth_go_mm", 119.61, 117.88), ("eye_width_mm", 31.55, 30.80),
        ("intercanthal_mm", 35.19, 34.23), ("nose_breadth_mm", 40.76, 37.51), ("mouth_width_mm", 50.44, 48.28),
        ("forehead_height_mm", 72.23, 68.05), ("morph_face_height_mm", 108.29, 106.1), ("upper_lip_mm", 21.26, 24.14),
        ("nose_length_mm", 50.31, 48.12), ("ear_length_mm", 59.15, 55.70), ("cephalic_index", 84.33, 85.44),
        ("facial_index", 80.55, 83.67), ("nasal_index", 85.61, 78.51)]
for name, a, b in MEAS:
    FACE.append((K23, "Bang 1", 3 if "index" not in name and name not in ("eye_width_mm",) else 4, "mean", name, "male", a))
    FACE.append((K23, "Bang 1", 3 if "index" not in name and name not in ("eye_width_mm",) else 4, "mean", name, "female", b))
for c, n, pct in (("oval", 1633, 66.3), ("square", 654, 26.6), ("triangle", 175, 7.1)):
    FACE.append((V21, "Bieu do 3.2 + Bang 3.1", 2, "celebie_jerolimov_shape", c, "both", pct))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    out = KB / "evidence" / "num"
    hs = {p: sha(p) for p in (S21, S15, K23, V21)}
    with open(out / "steps_vn.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256", "table", "pdf_page", "measure", "sex", "group", "value"])
        for p, t, pg, m, s, g, v in STEPS:
            w.writerow([p.name, hs[p], t, pg, m, s, g, v])
    with open(out / "kinh_face.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256", "table", "pdf_page", "index", "class", "sex", "value_pct_or_mean"])
        for p, t, pg, idx, c, s, v in FACE:
            w.writerow([p.name, hs[p], t, pg, idx, c, s, v])
    sp = KB / "stats.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    st["steps"] = {f"{p.name.split('_')[3]}|{t}|{m}|{s}|{g}": v for p, t, pg, m, s, g, v in STEPS}
    st["kinh_face"] = {f"{idx}|{c}|{s}": v for p, t, pg, idx, c, s, v in FACE}
    sp.write_text(json.dumps(st, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print(len(STEPS), "STEPS rows,", len(FACE), "face rows")


if __name__ == "__main__":
    main()
