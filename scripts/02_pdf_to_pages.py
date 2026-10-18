# -*- coding: utf-8 -*-
"""
2단계: PDF -> 페이지 PNG 렌더링 + 문항 영역 자동 탐지 -> work/crops.json

알고리즘 (OCR 없음, 여백 기반):
  1) 페이지를 그레이스케일로 렌더 (기본 200dpi)
  2) 상/하단 여백(머리말/꼬리말) 제거
  3) 세로 투영으로 2단(column) 경계 탐지 (가운데 빈 띠). 없으면 1단
  4) 각 단에서 가로 투영으로 "빈 줄 띠(min_gap px 이상)" 를 찾아 문항 블록으로 분할
  5) 너무 작은 블록(min_height 미만)은 이전 블록에 합침
결과는 tools/crop_editor.html 에서 눈으로 확인/수정 후 3단계로 넘깁니다.

사용법:
  python scripts/02_pdf_to_pages.py                # work/pdf/*.pdf 전체
  python scripts/02_pdf_to_pages.py --dpi 220 --min-gap 28
  python scripts/02_pdf_to_pages.py --only 수학2_연산학습지_1단원
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import parse_filename  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "work" / "pdf"
PAGE_DIR = ROOT / "work" / "pages"
CROPS = ROOT / "work" / "crops.json"


def render_pdf(pdf: Path, dpi: int):
    import fitz  # pymupdf
    from PIL import Image

    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf)
    pages = []
    zoom = dpi / 72.0
    for pno in range(len(doc)):
        page = doc[pno]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        out = PAGE_DIR / f"{pdf.stem}_p{pno + 1:02d}.png"
        img.save(out, optimize=True)
        pages.append((out, img))
    doc.close()
    return pages


def runs(mask):
    """bool 1D 배열에서 True 연속 구간 [(start, end)] (end exclusive)."""
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def detect_boxes(img, top_margin, bottom_margin, side_margin, min_gap, min_height, ink_thresh):
    g = np.asarray(img.convert("L"), dtype=np.uint8)
    H, W = g.shape
    ink = g < ink_thresh  # True = 글자/그림 픽셀

    y0, y1 = int(H * top_margin), int(H * (1 - bottom_margin))
    x0, x1 = int(W * side_margin), int(W * (1 - side_margin))
    body = ink[y0:y1, x0:x1]

    # --- 단(column) 탐지: 세로 투영에서 가운데 1/3 영역의 가장 넓은 빈 띠
    col_ink = body.sum(axis=0)
    empty_cols = col_ink <= max(1, body.shape[0] * 0.002)
    mid_lo, mid_hi = body.shape[1] // 3, body.shape[1] * 2 // 3
    best = None
    for s, e in runs(empty_cols):
        if e <= mid_lo or s >= mid_hi:
            continue
        if e - s >= 12 and (best is None or e - s > best[1] - best[0]):
            best = (s, e)
    if best:
        columns = [(0, best[0]), (best[1], body.shape[1])]
    else:
        columns = [(0, body.shape[1])]

    boxes = []
    for cx0, cx1 in columns:
        col = body[:, cx0:cx1]
        row_ink = col.sum(axis=1)
        ink_rows = row_ink > max(1, col.shape[1] * 0.004)
        segs = runs(ink_rows)
        if not segs:
            continue
        # 빈 띠가 min_gap 보다 작으면 같은 문항으로 이어붙임
        merged = [list(segs[0])]
        for s, e in segs[1:]:
            if s - merged[-1][1] < min_gap:
                merged[-1][1] = e
            else:
                merged.append([s, e])
        # 너무 낮은 블록(장식선, 번호만 떨어진 조각)은 앞 블록과 합치기
        final = []
        for s, e in merged:
            if final and (e - s) < min_height:
                final[-1][1] = e
            else:
                final.append([s, e])
        for s, e in final:
            if e - s < min_height and len(final) > 1:
                continue
            # 가로 방향 여백도 잘라내기
            sub = col[s:e]
            xs = np.where(sub.sum(axis=0) > 0)[0]
            if len(xs) == 0:
                continue
            bx0, bx1 = int(xs[0]), int(xs[-1]) + 1
            pad = 10
            boxes.append({
                "x": max(0, x0 + cx0 + bx0 - pad),
                "y": max(0, y0 + s - pad),
                "w": min(W, bx1 - bx0 + 2 * pad),
                "h": min(H, e - s + 2 * pad),
            })
    return boxes, (W, H), len(columns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default=str(PDF_DIR))
    ap.add_argument("--only", default="", help="파일명에 포함된 문자열로 필터")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--top-margin", type=float, default=0.07, help="페이지 높이 비율 (머리말 제거)")
    ap.add_argument("--bottom-margin", type=float, default=0.05, help="페이지 높이 비율 (꼬리말 제거)")
    ap.add_argument("--side-margin", type=float, default=0.04)
    ap.add_argument("--min-gap", type=int, default=24, help="문항 사이 최소 빈 줄 높이(px)")
    ap.add_argument("--min-height", type=int, default=60, help="문항 블록 최소 높이(px)")
    ap.add_argument("--ink-thresh", type=int, default=200)
    ap.add_argument("--reset", action="store_true", help="기존 crops.json 을 무시하고 다시 탐지")
    a = ap.parse_args()

    pdfs = sorted(p for p in Path(a.pdf_dir).glob("*.pdf") if a.only in p.stem)
    if not pdfs:
        print("PDF 가 없습니다. 1단계를 먼저 실행하거나 work/pdf 에 PDF 를 넣으세요.")
        return

    data = {"dpi": a.dpi, "docs": {}}
    if CROPS.exists() and not a.reset:
        data = json.loads(CROPS.read_text(encoding="utf-8"))

    for pdf in pdfs:
        info = parse_filename(pdf)
        if info["grade"] is None or info["unit_no"] is None:
            print(f"!! 파일명에서 학년/단원을 읽지 못함, 건너뜀: {pdf.name}")
            continue
        if pdf.stem in data["docs"] and not a.reset:
            print(f"skip (이미 탐지됨, --reset 으로 재탐지): {pdf.name}")
            continue
        print(f"[render] {pdf.name}")
        pages = render_pdf(pdf, a.dpi)
        doc_entry = {"meta": info, "pages": []}
        total = 0
        for out, img in pages:
            boxes, size, ncol = detect_boxes(
                img, a.top_margin, a.bottom_margin, a.side_margin,
                a.min_gap, a.min_height, a.ink_thresh)
            total += len(boxes)
            doc_entry["pages"].append({
                "image": out.relative_to(ROOT).as_posix(),
                "width": size[0], "height": size[1],
                "columns": ncol, "boxes": boxes,
            })
            print(f"   {out.name}: {ncol}단, 문항 후보 {len(boxes)}개")
        print(f"   => 총 {total}개 후보")
        data["docs"][pdf.stem] = doc_entry

    CROPS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {CROPS}")
    print("다음: tools/crop_editor.html 을 브라우저로 열어 영역을 확인/수정하세요 (README 참고).")


if __name__ == "__main__":
    main()
