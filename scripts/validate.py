# -*- coding: utf-8 -*-
"""web/problems.json 무결성 검사: 필수 필드, 이미지 존재, 학년/단원/난이도 분포 출력."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
ps = json.loads((WEB / "problems.json").read_text(encoding="utf-8"))
req = ["id", "grade", "unit", "difficulty", "image_url"]
bad = [p["id"] for p in ps if any(not p.get(k) for k in req)]
missing = [p["id"] for p in ps if not (WEB / p["image_url"]).exists()]
missing_ans = [p["id"] for p in ps if p.get("explanation_image") and not (WEB / p["explanation_image"]).exists()]
dup = [k for k, v in Counter(p["id"] for p in ps).items() if v > 1]
print(f"문항 {len(ps)}개 | 필드 누락 {len(bad)} | 문제 이미지 없음 {len(missing)} | 해설 이미지 없음 {len(missing_ans)} | 중복 id {len(dup)}")
print("정답 텍스트 있음:", sum(1 for p in ps if p.get("answer")), "| 해설 이미지 있음:", sum(1 for p in ps if p.get("explanation_image")))
for g in sorted({p["grade"] for p in ps}):
    print(f"\n[{g}]")
    for u in sorted({p["unit"] for p in ps if p["grade"] == g}, key=lambda s: int(s.split(".")[0])):
        c = Counter(p["difficulty"] for p in ps if p["grade"] == g and p["unit"] == u)
        st = Counter(p["sheet_type"] for p in ps if p["grade"] == g and p["unit"] == u)
        print(f"  {u:<22} 총 {sum(c.values()):4d}  상{c['상']:4d} 중{c['중']:4d} 하{c['하']:4d}   {dict(st)}")
size = sum(f.stat().st_size for f in (WEB / "images").glob("*.png")) / 1e6
print(f"\n이미지 {len(list((WEB / 'images').glob('*.png')))}개, {size:.1f} MB")
