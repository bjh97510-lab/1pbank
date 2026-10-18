# -*- coding: utf-8 -*-
"""
공통 유틸: 파일명 파싱, 설정 로드, ID 생성.

지원하는 파일명 패턴 (둘 중 하나면 인식):
  A) 규칙형  : [중2]_[1단원]_[상]_001.hwp   /  [중2]_[1단원]_[상]_001_ans.hwp
  B) 출판사형: (동아출판) 22개정_중학_수학2_연산학습지_3단원.hwp  /  ..._3단원_해설.hwp
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "units.json"


def load_units():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


_RE_GRADE_A = re.compile(r"\[\s*중\s*([123])\s*\]")
_RE_GRADE_B = re.compile(r"수학\s*([123])")
_RE_UNIT = re.compile(r"(\d{1,2})\s*단원")
_RE_DIFF = re.compile(r"\[\s*([상중하])\s*\]")
_RE_SEQ = re.compile(r"_(\d{3})(?:_ans)?$")
_RE_SHEET = re.compile(r"(준비학습지|연산학습지|단원평가|기본학습지|심화학습지)")


def parse_filename(path):
    """파일명에서 grade / unit_no / difficulty / is_answer / sheet_type / seq 를 추출."""
    stem = Path(path).stem
    units = load_units()

    m = _RE_GRADE_A.search(stem) or _RE_GRADE_B.search(stem)
    grade = f"중{m.group(1)}" if m else None

    m = _RE_UNIT.search(stem)
    unit_no = int(m.group(1)) if m else None

    m = _RE_SHEET.search(stem)
    sheet_type = m.group(1) if m else None

    m = _RE_DIFF.search(stem)
    if m:
        difficulty = m.group(1)
    else:
        table = units.get("_difficulty_by_sheet_type", {})
        difficulty = table.get(sheet_type, table.get("default", "중"))

    is_answer = bool(re.search(r"(_ans|해설|정답)", stem))

    m = _RE_SEQ.search(stem)
    seq = int(m.group(1)) if m else None

    unit_name = None
    if grade and unit_no is not None:
        unit_name = units.get(grade, {}).get(str(unit_no), f"{unit_no}. 단원")

    return {
        "grade": grade,
        "unit_no": unit_no,
        "unit": unit_name,
        "difficulty": difficulty,
        "sheet_type": sheet_type,
        "is_answer": is_answer,
        "seq": seq,
        "stem": stem,
    }


def make_id(grade, unit_no, seq, sheet_type=None):
    """MATH_2_01_001 형식의 ID. 학습지 종류가 있으면 MATH_2_01_Y_001 처럼 1글자 태그 삽입."""
    g = grade.replace("중", "") if grade else "X"
    tag = ""
    if sheet_type:
        tag = {"준비학습지": "P", "연산학습지": "C", "단원평가": "T"}.get(sheet_type, "S") + "_"
    return f"MATH_{g}_{int(unit_no or 0):02d}_{tag}{int(seq):03d}"


def doc_key(info):
    """문제 문서와 해설 문서를 짝지을 때 쓰는 키 (해설 여부만 제외)."""
    return (info["grade"], info["unit_no"], info["sheet_type"], info["seq"])


if __name__ == "__main__":
    for s in [
        "[중2]_[1단원]_[상]_001.hwp",
        "[중2]_[1단원]_[상]_001_ans.hwp",
        "(동아출판) 22개정_중학_수학1_연산학습지_3단원.hwp",
        "(동아출판) 중학_수학2_준비학습지_8단원_해설.hwp",
    ]:
        print(s, "->", parse_filename(s))
