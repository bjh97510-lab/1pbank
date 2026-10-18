# -*- coding: utf-8 -*-
"""
work/crops.json 의 탐지 결과를 페이지 이미지 위에 그려서 확인하는 디버그 도구.

  python scripts/debug_overlay.py --doc 수학1_연산학습지_5단원 --seq 9          # seq 9 가 있는 페이지
  python scripts/debug_overlay.py --doc 수학1_연산학습지_5단원 --page 8         # 8쪽
  python scripts/debug_overlay.py --doc 6단원_해설 --num 97 --section 2        # 해당 번호가 있는 페이지

결과: work/debug/<stem>_pNN.png  (파란 실선 = 문항 영역, 초록 점선 = 지시문, 빨강 = 지워지는 번호)
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
CROPS = ROOT / "work" / "crops.json"
OUT = ROOT / "work" / "debug"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True, help="문서 stem 에 포함된 문자열")
    ap.add_argument("--seq", type=int)
    ap.add_argument("--page", type=int, help="1부터")
    ap.add_argument("--num")
    ap.add_argument("--section", type=int, default=1)
    ap.add_argument("--scale", type=float, default=0.5)
    a = ap.parse_args()

    data = json.loads(CROPS.read_text(encoding="utf-8"))
    stems = [s for s in data["docs"] if a.doc in s]
    if len(stems) > 1 and "해설" not in a.doc:
        stems = [s for s in stems if "해설" not in s]
    if len(stems) != 1:
        print("문서가 유일하지 않음:", stems)
        return
    stem = stems[0]
    doc = data["docs"][stem]
    items = doc["items"]
    if a.page:
        pno = a.page - 1
    else:
        if a.seq:
            hit = next((it for it in items if it["seq"] == a.seq), None)
        else:
            hit = next((it for it in items if it["num"] == a.num and it["section"] == a.section), None)
        if hit is None:
            print("해당 문항 없음")
            return
        pno = hit["page"]
        print(f"seq {hit['seq']} num {hit['num']} section {hit['section']} page {pno + 1} box {hit['box']} check={hit.get('check')}")

    page = doc["pages"][pno]
    img = Image.open(ROOT / page["image"]).convert("RGB")
    d = ImageDraw.Draw(img)
    for it in items:
        for e in it.get("erase", []):
            if e["page"] == pno:
                d.rectangle((e["x"], e["y"], e["x"] + e["w"], e["y"] + e["h"]), outline=(220, 0, 0), width=3)
        if it.get("header") and it["header"]["page"] == pno and it["page"] == pno:
            h = it["header"]
            d.rectangle((h["x"] + 2, h["y"] + 2, h["x"] + h["w"] - 2, h["y"] + h["h"] - 2), outline=(0, 160, 0), width=3)
        if it["page"] != pno:
            continue
        b = it["box"]
        d.rectangle((b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]), outline=(0, 90, 220), width=4)
        d.text((b["x"] + 6, b["y"] + 4), f"#{it['seq']} ({it['section']}-{it['num']})" + (" CHECK" if it.get("check") else ""),
               fill=(0, 90, 220))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{stem}_p{pno + 1:02d}.png"
    img.resize((int(img.width * a.scale), int(img.height * a.scale))).save(out)
    print("saved:", out)


if __name__ == "__main__":
    main()
