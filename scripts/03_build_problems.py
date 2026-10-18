# -*- coding: utf-8 -*-
"""
3단계: work/crops.json 의 영역을 실제로 잘라 web/images/*.png 로 저장하고 web/problems.json 생성

- 각 문항 이미지 = [묶음 지시문 (있으면)] + [문항 본문], 번호/라벨은 흰색으로 지운 뒤 여백을 자동 트림
- 문제 문서와 해설 문서는 파일명(학년/단원/학습지 종류)으로 짝지어지고,
  읽기 순서 n번째 문항 <-> n번째 정답 으로 매칭. 인쇄된 번호 순서가 다르면 경고.
- 해설 문서에서 추출한 정답 텍스트(수식 없는 경우) 는 answer 필드에 들어간다.
- 기존 problems.json 에 수동으로 넣은 answer 는 보존 (추출 텍스트보다 우선)

사용법:
  python scripts/03_build_problems.py
  python scripts/03_build_problems.py --answers answers.csv   # id,answer CSV 로 정답 덮어쓰기
  python scripts/03_build_problems.py --only 수학2_연산학습지_1단원
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import doc_key, load_units  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CROPS = ROOT / "work" / "crops.json"
WEB = ROOT / "web"
IMG_DIR = WEB / "images"
OUT_JSON = WEB / "problems.json"

PAD = 8          # 트림 후 바깥 여백(px)
GAP = 10         # 지시문과 본문 사이 간격(px)
INK = 235        # 이 값보다 어두우면 잉크로 간주


class PageCache:
    def __init__(self):
        self.cache = {}

    def get(self, rel):
        if rel not in self.cache:
            self.cache[rel] = Image.open(ROOT / rel).convert("RGB")
        return self.cache[rel]


def crop_with_erase(page_img, box, erases, page_no):
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    if w <= 0 or h <= 0:
        return None
    img = page_img.crop((x, y, x + w, y + h))
    for e in erases:
        if e.get("page", page_no) != page_no:
            continue
        ex0, ey0 = e["x"] - x, e["y"] - y
        ex1, ey1 = ex0 + e["w"], ey0 + e["h"]
        if ex1 <= 0 or ey1 <= 0 or ex0 >= w or ey0 >= h:
            continue
        img.paste((255, 255, 255), (max(0, ex0), max(0, ey0), min(w, ex1), min(h, ey1)))
    return img


def trim(img):
    g = ImageOps.invert(img.convert("L")).point(lambda v: 255 if v > 255 - INK else 0)
    bbox = g.getbbox()
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    return img.crop((max(0, x0 - PAD), max(0, y0 - PAD), min(img.width, x1 + PAD), min(img.height, y1 + PAD)))


def build_item_image(doc, item, pages):
    page = doc["pages"][item["page"]]
    body = crop_with_erase(pages.get(page["image"]), item["box"], item["erase"], item["page"])
    if body is None:
        return None
    parts = [body]
    if item.get("header"):
        h = item["header"]
        hp = doc["pages"][h["page"]]
        head = crop_with_erase(pages.get(hp["image"]), h, h.get("erase", []), h["page"])
        head = trim(head) if head is not None else None
        if head is not None:
            parts.insert(0, head)
    if len(parts) == 1:
        return trim(body)
    head, body = parts
    body_t = trim(body)
    if body_t is None:
        return None
    # 왼쪽 정렬로 세로 합치기 (둘 다 단 왼쪽 가장자리 기준으로 잘라 정렬이 유지됨)
    # 본문은 트림 전 원래 x 위치를 지켜야 하므로, 헤더와 같은 원점에서 자른다
    head_full = parts[0]
    W = max(head_full.width, body.width)
    canvas = Image.new("RGB", (W, head_full.height + GAP + body.height), (255, 255, 255))
    canvas.paste(head_full, (0, 0))
    canvas.paste(body, (0, head_full.height + GAP))
    return trim(canvas)


def save_png(img, path):
    # 팔레트 양자화로 용량 1/3 수준으로 축소 (문항 이미지는 색이 거의 없음)
    img.quantize(colors=32, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", default="", help="id,answer CSV")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true", help="이미 있는 이미지도 다시 생성 (기본: 메타데이터만 갱신)")
    a = ap.parse_args()

    if not CROPS.exists():
        print("work/crops.json 이 없습니다. 2단계를 먼저 실행하세요.")
        return
    data = json.loads(CROPS.read_text(encoding="utf-8"))
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    manual = {}
    if OUT_JSON.exists():
        for p in json.loads(OUT_JSON.read_text(encoding="utf-8")):
            if p.get("answer_manual"):
                manual[p["id"]] = p["answer_manual"]
    if a.answers:
        with open(a.answers, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0] and row[0] != "id":
                    manual[row[0].strip()] = row[1].strip()

    problem_docs, answer_docs = {}, {}
    for stem, doc in data["docs"].items():
        if a.only and a.only not in stem:
            continue
        key = doc_key(doc["meta"])
        (answer_docs if doc["meta"]["is_answer"] else problem_docs)[key] = (stem, doc)

    pages = PageCache()
    units = load_units()
    problems = []
    for key, (stem, doc) in sorted(problem_docs.items(), key=lambda kv: str(kv[0])):
        meta = doc["meta"]
        grade, unit_no, sheet, _ = key
        unit_name = units.get(grade, {}).get(str(unit_no), meta["unit"])   # config 가 최신이면 그 이름 사용
        # 난이도: 파일명에 [상/중/하] 가 없으면 연산학습지는 소단원 안에서의 위치(앞 1/3 하, 중간 중, 뒤 1/3 상)로 추정
        explicit = "[" in meta["stem"] and any(f"[{d}]" in meta["stem"] for d in "상중하")
        sec_sizes = {}
        for it in doc["items"]:
            sec_sizes[it["section"]] = sec_sizes.get(it["section"], 0) + 1
        sec_pos = {}

        def guess_difficulty(it):
            if explicit or sheet != "연산학습지":
                return meta["difficulty"]
            sec_pos[it["section"]] = sec_pos.get(it["section"], 0) + 1
            frac = sec_pos[it["section"]] / sec_sizes[it["section"]]
            return "하" if frac <= 1 / 3 else ("중" if frac <= 2 / 3 else "상")
        tag = {"준비학습지": "P", "연산학습지": "C", "단원평가": "T"}.get(sheet, "S") if sheet else ""
        base = f"MATH_{grade.replace('중', '')}_{unit_no:02d}" + (f"_{tag}" if tag else "")

        ans_items, by_index = [], False
        if key in answer_docs:
            ans_stem, ans_doc = answer_docs[key]
            ans_items = ans_doc["items"]
            q_labels = [f"{it['section']}-{it['num']}" for it in doc["items"]]
            a_labels = [f"{it['section']}-{it['num']}" for it in ans_items]
            by_index = len(q_labels) == len(a_labels)   # 개수가 같으면 읽기 순서로 1:1 (출판사 번호 오타에 안전)
            if q_labels != a_labels:
                print(f"!! 문항 {len(q_labels)}개 vs 정답 {len(a_labels)}개 번호 순서 불일치: {stem}")
                mism = next((i for i, (x, y) in enumerate(zip(q_labels, a_labels)) if x != y), min(len(q_labels), len(a_labels)))
                print(f"   첫 불일치 위치 {mism + 1}: 문항 {q_labels[mism:mism + 3]} / 정답 {a_labels[mism:mism + 3]}"
                      + ("  → 개수가 같아 순서대로 매칭" if by_index else "  → 번호로 매칭"))
        else:
            print(f"   (해설 문서 없음) {stem}")

        n_ok = 0
        for it in doc["items"]:
            pid = f"{base}_{it['seq']:03d}"
            q_path = IMG_DIR / f"{pid}.png"
            if a.force or not q_path.exists():
                img = build_item_image(doc, it, pages)
                if img is None:
                    print(f"   !! 빈 이미지, 건너뜀: {pid}")
                    continue
                save_png(img, q_path)

            ans_text, ans_path = "", ""
            if by_index:
                ai = ans_items[it["seq"] - 1] if it["seq"] - 1 < len(ans_items) else None
            else:
                ai = next((x for x in ans_items if x["section"] == it["section"] and x["num"] == it["num"]), None)
            if ai is not None:
                ans_path = IMG_DIR / f"{pid}_ans.png"
                if a.force or not ans_path.exists():
                    aimg = build_item_image(ans_doc, ai, pages)
                    if aimg is not None:
                        save_png(aimg, ans_path)
                ans_path = ans_path.relative_to(WEB).as_posix() if ans_path.exists() else ""
                ans_text = ai.get("text", "")

            entry = {
                "id": pid,
                "grade": grade,
                "unit": unit_name,
                "unit_no": unit_no,
                "sheet_type": sheet,
                "section": it["section"],
                "num": it["num"],
                "difficulty": guess_difficulty(it),
                "image_url": q_path.relative_to(WEB).as_posix(),
                "answer": manual.get(pid, ans_text),
                "explanation_image": ans_path,
                "source": stem,
            }
            if pid in manual:
                entry["answer_manual"] = manual[pid]
            problems.append(entry)
            n_ok += 1
        print(f"[ok] {stem}: 문항 {n_ok}개" + (f" (정답 매칭 {sum(1 for p in problems if p['source'] == stem and p['explanation_image'])}개)" if ans_items else ""))

    if a.only and OUT_JSON.exists():
        keep = [p for p in json.loads(OUT_JSON.read_text(encoding="utf-8")) if a.only not in p["source"]]
        problems = keep + problems
    OUT_JSON.write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in IMG_DIR.glob("*.png"))
    print(f"\n총 {len(problems)}문항 -> {OUT_JSON}   (이미지 {total / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
