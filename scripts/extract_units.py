# -*- coding: utf-8 -*-
"""
연산학습지 해설 PDF 첫 쪽의 대단원 제목("1 소인수분해" 처럼 빨간 굵은 글씨)을 읽어
config/units.json 의 단원명을 실제 교과서 목차로 갱신한다.

  python scripts/extract_units.py           # work/pdf/*해설.pdf 스캔 → config/units.json 갱신
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_filename, CONFIG  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "work" / "pdf"
TITLE_COLOR = 0xD11D24


def unit_title(pdf):
    page = pymupdf.open(pdf)[0]
    spans = [s for b in page.get_text("dict")["blocks"] if b["type"] == 0
             for l in b["lines"] for s in l["spans"] if s["text"].strip()]
    # 대단원 번호: 빨간 굵은 숫자. 같은 줄(y 차이 3pt 이내)에 있는 글자가 제목.
    nums = [s for s in spans if s["color"] == TITLE_COLOR and re.match(r"^\d+$", s["text"].strip())]
    if not nums:
        return None
    n = min(nums, key=lambda s: s["bbox"][1])
    line = sorted([s for s in spans if abs(s["bbox"][1] - n["bbox"][1]) < 3 and s is not n and s["size"] >= 10],
                  key=lambda s: s["bbox"][0])
    half = page.rect.width / 2
    text = " ".join(s["text"].strip() for s in line if n["bbox"][0] < s["bbox"][0] < half)
    return text.strip() or None


def main():
    units = json.loads(CONFIG.read_text(encoding="utf-8"))
    found = {}
    for pdf in sorted(PDF_DIR.glob("*해설.pdf")):
        info = parse_filename(pdf)
        if not info["grade"] or info["unit_no"] is None:
            continue
        t = unit_title(pdf)
        if not t:
            continue
        # 연산학습지 제목을 우선, 없으면 준비학습지 제목
        key = (info["grade"], info["unit_no"])
        if key not in found or info["sheet_type"] == "연산학습지":
            found[key] = (t, info["sheet_type"])
    for (grade, no), (t, st) in sorted(found.items()):
        name = f"{no}. {t}"
        old = units.setdefault(grade, {}).get(str(no))
        units[grade][str(no)] = name
        print(f"{grade} {name}" + (f"   (이전: {old})" if old != name else "") + f"   [{st}]")
    CONFIG.write_text(json.dumps(units, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n갱신: {CONFIG}")


if __name__ == "__main__":
    main()
