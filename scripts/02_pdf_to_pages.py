# -*- coding: utf-8 -*-
"""
2단계: PDF -> 페이지 PNG 렌더링 + 문항 영역 탐지 -> work/crops.json

탐지 방식 (PDF 텍스트 레이어 기반, OCR 불필요):
  - 한글(HWP) 에서 저장한 PDF 는 글자 정보가 살아 있다.
  - 문항 번호는 전용 글꼴(HanSantteutDotumBold) + 강조색(주황 0xf25d18 / 분홍 0xf03ca7) 으로 찍혀 있어
    "01", "02", ... 처럼 숫자만 있는 span 을 "앵커" 로 잡으면 문항 시작 위치를 정확히 알 수 있다.
  - "[06~10]" 형태의 묶음 지시문은 같은 글꼴의 라벨로 찾아, 해당 번호 범위의 문항 위에 붙여 준다.
  - 나머지 글자/도형(선, 네모 칸, 그림)은 "자기 위쪽에서 가장 가까운 앵커 줄" 에 소속시키고,
    각 앵커의 영역 = 앵커 + 소속 요소들의 합집합 → 번호보다 위아래로 긴 분수/그림도 잘리지 않는다.
  - 해설(정답) 문서는 한 줄에 여러 번호가 오므로, 같은 줄에서는 x 위치로 소속을 나눈다.
    정답 텍스트도 함께 추출한다 (수식 글꼴 중 숫자는 복원, 그 외 기호가 섞이면 이미지로만 제공).
  - 번호 글자와 "[a~b]" 라벨은 흰색으로 지워서(erase) 학습지에서 새로 매기는 번호와 충돌하지 않게 한다.

출력 (work/crops.json):
  {
    "dpi": 200,
    "docs": {
      "<파일 stem>": {
        "meta": {...parse_filename...},
        "pages": [{"image": "work/pages/xxx_p01.png", "width": W, "height": H}],
        "items": [
          {"seq": 1, "num": "01", "section": 1, "page": 0,
           "box": {"x","y","w","h"},           # 픽셀 좌표
           "header": {"page","x","y","w","h","erase":[...]} | null,   # 지시문 crop 과 그 안에서 지울 영역
           "erase": [{"page","x","y","w","h"}],                       # 본문 crop 에서 지울 영역(번호)
           "text": "1, 5"}                     # 해설 문서만 의미 있음
        ]
      }
    }
  }

사용법:
  python scripts/02_pdf_to_pages.py                   # work/pdf/*.pdf 전체 (이미 처리된 문서는 건너뜀)
  python scripts/02_pdf_to_pages.py --only 수학2_연산학습지_1단원 --reset
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_filename  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "work" / "pdf"
PAGE_DIR = ROOT / "work" / "pages"
CROPS = ROOT / "work" / "crops.json"

MARK_RE = re.compile(r"^\d{1,3}$")
HDR_RE = re.compile(r"^\[(\d+)(?:~(\d+))?\]$")
MARK_COLORS = {0xF25D18, 0xF03CA7}      # 연산학습지(주황) / 준비학습지(분홍)
MARK_FONT = "HanSantteutDotum"
SIDE = 40                               # 페이지 좌우 본문 여백(pt)
BOTTOM = 40
PAD = 4                                 # 영역 바깥 여유(pt)
ROW_SLACK = 12                          # 앵커 줄보다 이만큼 위까지는 같은 줄로 간주 (분수 분자 등)
SHAPE_SLACK = 20                        # 그림 덩어리의 윗변이 앵커 줄보다 이만큼 위까지면 같은 줄

PUA = re.compile(r"[-]")    # 한글 수식 글꼴(HyhwpEQ) 의 사용자 영역 글자
# HyhwpEQ 글꼴의 숫자 글리프 → 실제 숫자 (관찰값: =1 … =9, =0)
EQ_DIGITS = {chr(0xE034 + i): str(i + 1) for i in range(9)}
EQ_DIGITS[chr(0xE03D)] = "0"
EQ_SYMBOLS = {"": ",", "": ".", "": "-", "": "=", "": "<", "": ">",
              "": ":", "": "°", "": "π"}
EQ_LOWER = {chr(0xE0E5 + i): chr(ord("a") + i) for i in range(26)}   # a= … z=
EQ_UPPER = {chr(0xE000 + i): chr(ord("A") + i) for i in range(26)}   # A= … Z=
EQ_MAP = str.maketrans({**EQ_DIGITS, **EQ_SYMBOLS, **EQ_LOWER, **EQ_UPPER})


def eq_text(t):
    """수식 글꼴 텍스트를 가능한 범위에서 일반 문자로 바꾼다. 못 바꾼 글자가 남으면 '' 반환."""
    t = t.translate(EQ_MAP)
    if PUA.search(t):
        return ""
    t = re.sub(r",(?=\S)", ", ", t)           # "1,5" → "1, 5"
    return t if len(t) <= 80 else ""          # 표/긴 풀이는 이미지로만


class Span:
    __slots__ = ("text", "x0", "y0", "x1", "y1", "font", "color", "size")

    def __init__(self, s):
        self.text = s["text"].strip()
        self.x0, self.y0, self.x1, self.y1 = s["bbox"]
        self.font, self.color, self.size = s["font"], s["color"], s["size"]

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    @property
    def rect(self):
        return (self.x0, self.y0, self.x1, self.y1)


def page_spans(page):
    spans, images = [], []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            images.append(tuple(b["bbox"]))
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                if s["text"].strip():
                    spans.append(Span(s))
    return spans, images


def is_marker(s):
    return s.font.startswith(MARK_FONT) and s.color in MARK_COLORS and s.size >= 9 and MARK_RE.match(s.text)


def is_header(s):
    return s.font.startswith(MARK_FONT) and s.color in MARK_COLORS and HDR_RE.match(s.text)


def is_banner(im):
    """소단원 제목 띠(가로로 길고 납작한 그림) 인지. 문항 안의 그림(도형 등)과 구분."""
    w, h = im[2] - im[0], im[3] - im[1]
    return w >= 200 and h <= 40


def find_divider(page, W):
    """페이지 중앙 부근의 긴 세로선(단 구분선) x 좌표, 없으면 None."""
    for d in page.get_drawings():
        r = d.get("rect")
        if r is not None and r.width < 3 and r.height > 200 and abs(r.x0 - W / 2) < 25:
            return r.x0
    return None


def group_rows(anchors, tol=7):
    """같은 줄(y 가 비슷한) 앵커끼리 묶기. 위→아래, 각 줄은 좌→우."""
    rows = []
    for a in sorted(anchors, key=lambda s: (s.y0, s.x0)):
        if rows and abs(rows[-1][0].y0 - a.y0) <= tol:
            rows[-1].append(a)
        else:
            rows.append([a])
    for r in rows:
        r.sort(key=lambda s: s.x0)
    return rows


def cluster_rects(rects, gap=4):
    """서로 닿거나 가까운(gap pt 이내) 사각형들을 하나의 그림 덩어리로 합친다."""
    rs = [list(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        while rs:
            r = rs.pop()
            i = 0
            while i < len(out):
                o = out[i]
                if r[0] - gap <= o[2] and o[0] - gap <= r[2] and r[1] - gap <= o[3] and o[1] - gap <= r[3]:
                    r = [min(r[0], o[0]), min(r[1], o[1]), max(r[2], o[2]), max(r[3], o[3])]
                    out.pop(i)
                    changed = True
                else:
                    i += 1
            out.append(r)
        rs = out
    return [tuple(r) for r in rs]


def union(rects):
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))


def grow(r, d=1):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def analyze_column(spans, drawings, images, left, right, anchors, H, col_index):
    """한 단(column) 안에서 앵커별 영역을 계산. (items, headers) 를 pt 좌표로 반환."""
    rows = group_rows(anchors)
    row_tops = [min(a.y0 for a in r) for r in rows]

    def in_col(x):
        return left <= x <= right

    content = [s for s in spans if not is_marker(s) and not is_header(s) and in_col(s.cx)]
    shapes = [r for r in drawings if r[3] - r[1] < 200 and r[2] - r[0] < 400 and in_col((r[0] + r[2]) / 2)]
    figs = [im for im in images if not is_banner(im) and in_col((im[0] + im[2]) / 2)]
    banners = [im for im in images if is_banner(im) and im[0] < right and im[2] > left]

    owned_spans = {id(a): [] for a in anchors}     # 글자 (줄 중심 y 로 소속 결정)
    owned_shapes = {id(a): [] for a in anchors}    # 그림 덩어리 (덩어리의 윗변 y 로 소속 결정)

    def owner(x0, y, slack):
        ri = None
        for i, top in enumerate(row_tops):
            if top - slack <= y:
                ri = i
            else:
                break
        if ri is None:
            return None
        row = rows[ri]
        if len(row) == 1:
            return row[0]
        cand = [a for a in row if a.x0 <= x0 + 3]
        return cand[-1] if cand else row[0]

    for s in content:
        a = owner(s.x0, s.cy, ROW_SLACK)
        if a is not None:
            owned_spans[id(a)].append(s)
    for c in cluster_rects(shapes + figs):
        a = owner(c[0], c[1], SHAPE_SLACK)
        if a is not None:
            owned_shapes[id(a)].append(c)

    # --- 지시문 옆에 놓인 그림이 아래 문항들 옆까지 길게 이어지는 경우 ---
    #   그림(과 그 안의 라벨 글자)은 지시문 소유로, 그림과 나란한 문항들은 폭을 그림 왼쪽까지로 제한하고
    #   지시문 crop 에서는 그 문항들의 글자를 흰색으로 지운다.
    extra_erase = {id(a): [] for a in anchors}
    x_limit = {}
    header_fig = {}
    for ri, row in enumerate(rows):
        for a in row:
            if not is_header(a) or not owned_shapes[id(a)]:
                continue
            fig = grow(union(owned_shapes[id(a)]), 3)
            header_fig[id(a)] = fig
            for rj in range(ri + 1, len(rows)):
                for b in rows[rj]:
                    keep = []
                    for s in owned_spans[id(b)]:
                        if fig[0] <= s.cx <= fig[2] and fig[1] <= s.cy <= fig[3]:
                            owned_spans[id(a)].append(s)      # 그림 안 라벨
                        else:
                            keep.append(s)
                    owned_spans[id(b)] = keep
            for rj in range(ri + 1, len(rows)):
                for b in rows[rj]:
                    sp = owned_spans[id(b)]
                    ty0 = min([b.y0] + [s.y0 for s in sp])
                    ty1 = max([b.y1] + [s.y1 for s in sp])
                    if ty0 < fig[3] and ty1 > fig[1]:                     # 그림과 세로로 겹침
                        tx1 = max([b.x1] + [s.x1 for s in sp] + [c[2] for c in owned_shapes[id(b)]])
                        if tx1 < fig[0]:
                            x_limit[id(b)] = fig[0] - 2
                            extra_erase[id(a)] += [grow(b.rect)] + [grow(s.rect) for s in sp] \
                                                  + [grow(c) for c in owned_shapes[id(b)]]

    def extent(a, with_shapes=True):
        rects = [a.rect] + [s.rect for s in owned_spans[id(a)]]
        if with_shapes:
            rects += owned_shapes[id(a)]
        return union(rects)

    # 줄 단위 실제 범위 (이웃 줄과 겹치지 않게 자르는 기준). 지시문 줄은 글자 범위만 사용.
    raw = []
    for row in rows:
        ex = [extent(a, with_shapes=not is_header(a)) for a in row]
        raw.append((min(e[1] for e in ex), max(e[3] for e in ex)))

    items, headers = [], []
    for ri, row in enumerate(rows):
        for k, a in enumerate(row):
            ex = extent(a)
            y0, y1 = ex[1] - PAD, ex[3] + PAD
            if ri > 0:
                y0 = max(y0, raw[ri - 1][1] + 1)
            if ri + 1 < len(rows) and id(a) not in header_fig:
                y1 = min(y1, raw[ri + 1][0] - 1)
            for b in banners:                      # 소단원 띠는 영역에서 제외
                if a.y0 < b[1] < y1:
                    y1 = min(y1, b[1] - 2)
                if y0 < b[3] < a.y1:
                    y0 = max(y0, b[3] + 2)
            y0, y1 = max(y0, SIDE / 2), min(y1, H - BOTTOM / 2)
            fallback = y1 - y0 < 6
            if fallback:                           # 이웃 줄과 겹쳐 잘려 버린 경우: 앵커 줄만이라도 확보
                y0, y1 = a.y0 - PAD, a.y1 + PAD
            if len(row) == 1:
                x0, x1 = left, right
            else:
                x0 = a.x1 + 1
                x1 = (row[k + 1].x0 - 3) if k + 1 < len(row) else right
            x1 = min(x1, x_limit.get(id(a), x1))
            box = (x0, y0, x1, y1)
            entry = {"anchor": a, "box": box, "col": col_index, "row": ri, "x": a.x0, "fallback": fallback,
                     "erase": [grow(a.rect)] + extra_erase[id(a)]}
            if is_header(a):
                headers.append(entry)
            else:
                sp = sorted(owned_spans[id(a)], key=lambda s: (round(s.y0 / 4), s.x0))
                entry["text"] = re.sub(r"\s+", " ", eq_text(" ".join(s.text for s in sp))).strip()
                items.append(entry)
    return items, headers


def analyze_page(page):
    """페이지 하나에서 (문항, 헤더) 목록을 pt 좌표로 돌려준다."""
    W, H = page.rect.width, page.rect.height
    spans, images = page_spans(page)
    anchors = [s for s in spans if is_marker(s) or is_header(s)]
    if not any(is_marker(s) for s in anchors):
        return [], []
    drawings = [tuple(d["rect"]) for d in page.get_drawings() if d.get("rect") is not None]

    divider = find_divider(page, W)
    two_col = divider is not None or any(a.x0 > W / 2 + 10 for a in anchors if is_marker(a))
    if two_col and divider is None:
        divider = W / 2

    items, headers = [], []
    if two_col:
        for side in (0, 1):
            col_anchors = [a for a in anchors if (a.cx > divider) == bool(side)]
            if not col_anchors:
                continue
            left = min(a.x0 for a in col_anchors) - 6
            right = (divider - 5) if side == 0 else (W - SIDE)
            it, hd = analyze_column(spans, drawings, images, left, right, col_anchors, H, side)
            items += it
            headers += hd
    else:
        left = min(a.x0 for a in anchors) - 6
        it, hd = analyze_column(spans, drawings, images, left, W - SIDE, anchors, H, 0)
        items += it
        headers += hd
    return items, headers


def order_key(e):
    return (e["page"], e["col"], e["row"], e["x"])


def attach_headers(doc_items, doc_hdrs):
    """읽기 순서(페이지→단→줄→x)로 훑으며 [a~b] 헤더를 범위 안 문항에 붙인다."""
    events = sorted([("hdr", h) for h in doc_hdrs] + [("item", it) for it in doc_items],
                    key=lambda e: order_key(e[1]))
    current = None
    for kind, obj in events:
        if kind == "hdr":
            a, b = HDR_RE.match(obj["anchor"].text).groups()
            current = (int(a), int(b or a), obj)
        else:
            n = int(obj["anchor"].text)
            obj["header"] = current[2] if current and current[0] <= n <= current[1] else None


def to_px(rect, z):
    x0, y0, x1, y1 = rect
    return {"x": int(x0 * z), "y": int(y0 * z), "w": int((x1 - x0) * z), "h": int((y1 - y0) * z)}


def process_pdf(pdf, dpi):
    doc = pymupdf.open(pdf)
    z = dpi / 72.0
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    pages, doc_items, doc_hdrs = [], [], []
    for pno, page in enumerate(doc):
        out = PAGE_DIR / f"{pdf.stem}_p{pno + 1:02d}.png"
        if not out.exists():
            page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False).save(out)
        W, H = page.rect.width, page.rect.height
        pages.append({"image": out.relative_to(ROOT).as_posix(), "width": int(W * z), "height": int(H * z)})
        items, hdrs = analyze_page(page)
        for e in items + hdrs:
            e["page"] = pno
        doc_items += items
        doc_hdrs += hdrs
    doc.close()

    attach_headers(doc_items, doc_hdrs)
    doc_items.sort(key=order_key)

    out_items, section, prev_num = [], 1, 0
    for seq, it in enumerate(doc_items, 1):
        n = int(it["anchor"].text)
        if n < prev_num:          # 번호가 다시 01 부터 → 새 소단원
            section += 1
        prev_num = n
        entry = {
            "seq": seq, "num": it["anchor"].text, "section": section, "page": it["page"],
            "box": to_px(it["box"], z),
            "header": None,
            "erase": [dict(page=it["page"], **to_px(e, z)) for e in it["erase"]],
            "text": it["text"],
        }
        if it["fallback"]:
            entry["check"] = True       # 영역 계산이 불안정했던 문항: crop_editor 로 확인 권장
        if it.get("header"):
            h = it["header"]
            entry["header"] = dict(page=h["page"], **to_px(h["box"], z),
                                   erase=[dict(page=h["page"], **to_px(e, z)) for e in h["erase"]])
        out_items.append(entry)
    return pages, out_items, section


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default=str(PDF_DIR))
    ap.add_argument("--only", default="", help="파일명에 포함된 문자열로 필터")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--reset", action="store_true", help="기존 결과를 무시하고 다시 탐지")
    a = ap.parse_args()

    pdfs = sorted(p for p in Path(a.pdf_dir).glob("*.pdf") if a.only in p.stem)
    if not pdfs:
        print("PDF 가 없습니다. 1단계를 먼저 실행하거나 work/pdf 에 PDF 를 넣으세요.")
        return

    data = {"dpi": a.dpi, "docs": {}}
    if CROPS.exists() and not a.reset:
        data = json.loads(CROPS.read_text(encoding="utf-8"))
        if data.get("dpi") != a.dpi:
            print(f"!! 기존 crops.json 의 dpi({data.get('dpi')}) 와 다릅니다. --reset 으로 다시 시작하세요.")
            return

    for pdf in pdfs:
        info = parse_filename(pdf)
        if info["grade"] is None or info["unit_no"] is None:
            print(f"!! 파일명에서 학년/단원을 읽지 못함, 건너뜀: {pdf.name}")
            continue
        if pdf.stem in data["docs"] and not a.reset:
            print(f"skip (이미 탐지됨): {pdf.name}")
            continue
        pages, items, sections = process_pdf(pdf, a.dpi)
        n_hdr = sum(1 for it in items if it["header"])
        n_txt = sum(1 for it in items if it["text"])
        n_chk = sum(1 for it in items if it.get("check"))
        kind = "해설" if info["is_answer"] else "문항"
        print(f"[ok] {pdf.stem}: {len(pages)}쪽, {kind} {len(items)}개, 소단원 {sections}개"
              + (f", 지시문 붙은 문항 {n_hdr}개" if n_hdr else "")
              + (f", 텍스트 정답 {n_txt}개" if info["is_answer"] else "")
              + (f", !! 확인 필요 {n_chk}개" if n_chk else ""))
        data["docs"][pdf.stem] = {"meta": info, "pages": pages, "items": items}

    CROPS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {CROPS}")
    print("다음: tools/crop_editor.html 로 확인하거나 바로 scripts/03_build_problems.py 실행")


if __name__ == "__main__":
    main()
