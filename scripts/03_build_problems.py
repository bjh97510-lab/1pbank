# -*- coding: utf-8 -*-
"""
3단계: work/crops.json 의 영역을 실제로 잘라 web/images/*.png 로 저장하고 web/problems.json 생성

- 문제 문서와 해설 문서는 파일명(학년/단원/학습지 종류)으로 짝지어지며,
  n번째 문항 <-> n번째 해설 블록 으로 1:1 매칭됩니다.
  (해설 문서의 블록 수가 다르면 경고를 출력하니 crop_editor 로 맞춰 주세요.)
- 이미 problems.json 에 있는 항목의 answer(정답 텍스트) 는 보존됩니다.

사용법:
  python scripts/03_build_problems.py
  python scripts/03_build_problems.py --answers answers.csv   # id,answer 형식 CSV 로 정답 일괄 입력
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import make_id, doc_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CROPS = ROOT / "work" / "crops.json"
WEB = ROOT / "web"
IMG_DIR = WEB / "images"
OUT_JSON = WEB / "problems.json"


def crop_blocks(doc, out_prefix):
    """문서의 모든 페이지 박스를 순서대로 잘라 저장. 저장된 상대경로 리스트 반환."""
    files = []
    n = 0
    for page in doc["pages"]:
        img = Image.open(ROOT / page["image"]).convert("RGB")
        for b in page["boxes"]:
            n += 1
            box = (int(b["x"]), int(b["y"]), int(b["x"] + b["w"]), int(b["y"] + b["h"]))
            out = IMG_DIR / f"{out_prefix}_{n:03d}.png"
            img.crop(box).save(out, optimize=True)
            files.append(out)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", default="", help="id,answer CSV")
    a = ap.parse_args()

    if not CROPS.exists():
        print("work/crops.json 이 없습니다. 2단계를 먼저 실행하세요.")
        return
    data = json.loads(CROPS.read_text(encoding="utf-8"))
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    old_answers = {}
    if OUT_JSON.exists():
        for p in json.loads(OUT_JSON.read_text(encoding="utf-8")):
            if p.get("answer"):
                old_answers[p["id"]] = p["answer"]
    if a.answers:
        with open(a.answers, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0] and row[0] != "id":
                    old_answers[row[0].strip()] = row[1].strip()

    problem_docs, answer_docs = {}, {}
    for stem, doc in data["docs"].items():
        key = doc_key(doc["meta"])
        (answer_docs if doc["meta"]["is_answer"] else problem_docs)[key] = (stem, doc)

    problems = []
    for key, (stem, doc) in sorted(problem_docs.items(), key=lambda kv: str(kv[0])):
        meta = doc["meta"]
        grade, unit_no, sheet, seq = key
        base = f"MATH_{grade.replace('중','')}_{unit_no:02d}" + (f"_{sheet}" if sheet else "")
        q_files = crop_blocks(doc, base)

        ans_files = []
        if key in answer_docs:
            ans_files = crop_blocks(answer_docs[key][1], base + "_ans")
            if len(ans_files) != len(q_files):
                print(f"!! 문항 {len(q_files)}개 vs 해설 {len(ans_files)}개 불일치: {stem}")
        else:
            print(f"   (해설 문서 없음) {stem}")

        for i, qf in enumerate(q_files, 1):
            pid = make_id(grade, unit_no, i, sheet) if seq is None else make_id(grade, unit_no, seq, sheet)
            if seq is not None and len(q_files) > 1:
                pid = f"{pid}_{i:02d}"
            problems.append({
                "id": pid,
                "grade": grade,
                "unit": meta["unit"],
                "unit_no": unit_no,
                "sheet_type": sheet,
                "difficulty": meta["difficulty"],
                "image_url": qf.relative_to(WEB).as_posix(),
                "answer": old_answers.get(pid, ""),
                "explanation_image": ans_files[i - 1].relative_to(WEB).as_posix() if i - 1 < len(ans_files) else "",
                "source": stem,
            })
        print(f"[ok] {stem}: 문항 {len(q_files)}개")

    OUT_JSON.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(problems)}문항 -> {OUT_JSON}")
    print("다음: web/ 폴더를 정적 서버로 열어 index.html 확인  (예: python -m http.server 8000 --directory web)")


if __name__ == "__main__":
    main()
