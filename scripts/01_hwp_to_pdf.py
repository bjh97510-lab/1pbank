# -*- coding: utf-8 -*-
"""
1단계: HWP -> PDF 일괄 변환 (한글 COM 자동화, Windows + 한컴오피스 필요)

사용법:
  python scripts/01_hwp_to_pdf.py                 # source/*.hwp -> work/pdf/*.pdf
  python scripts/01_hwp_to_pdf.py --in 폴더 --out 폴더
  python scripts/01_hwp_to_pdf.py --visible       # 한글 창을 보이게 (디버깅)

주의:
  - 처음 실행 시 "보안 승인" 대화상자가 뜨면 "모두 허용" 을 누르세요.
    (한글 > 도구 > 환경 설정 > 기타 > 보안 모듈 등록 으로 FilePathCheckDLL 등록하면 생략 가능)
  - 한글이 설치되어 있지 않은 PC 에서는 HWP 를 수동으로 PDF 로 저장한 뒤 work/pdf 에 넣고 2단계로 가세요.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def convert_all(in_dir: Path, out_dir: Path, visible: bool):
    try:
        import win32com.client  # noqa
        import pythoncom
    except ImportError:
        print("pywin32 가 필요합니다:  pip install pywin32")
        sys.exit(1)

    hwps = sorted(list(in_dir.glob("*.hwp")) + list(in_dir.glob("*.hwpx")))
    if not hwps:
        print(f"HWP 파일이 없습니다: {in_dir}")
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    pythoncom.CoInitialize()
    try:
        hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
    except Exception:
        # gen_py 캐시 문제 시 late-binding 으로 폴백
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
    try:
        # 보안 모듈이 등록되어 있으면 승인 대화상자 없이 파일 접근 가능
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    except Exception:
        pass
    hwp.XHwpWindows.Item(0).Visible = visible

    ok, fail = 0, []
    for i, src in enumerate(hwps, 1):
        dst = out_dir / (src.stem + ".pdf")
        if dst.exists():
            print(f"[{i}/{len(hwps)}] skip (exists) {dst.name}")
            ok += 1
            continue
        print(f"[{i}/{len(hwps)}] {src.name}")
        try:
            if not hwp.Open(str(src.resolve()), "HWP", "forceopen:true"):
                raise RuntimeError("Open 실패")
            # 모든 글꼴/수식/그림이 그대로 유지되는 PDF 로 저장
            hwp.SaveAs(str(dst.resolve()), "PDF", "")
            time.sleep(0.3)
            hwp.Clear(1)  # 저장 안 하고 닫기
            if not dst.exists():
                raise RuntimeError("PDF 가 생성되지 않음")
            ok += 1
        except Exception as e:
            print(f"   !! 실패: {e}")
            fail.append(src.name)
            try:
                hwp.Clear(1)
            except Exception:
                pass

    try:
        hwp.Quit()
    except Exception:
        pass
    pythoncom.CoUninitialize()

    print(f"\n완료: 성공 {ok} / 실패 {len(fail)}  ->  {out_dir}")
    for f in fail:
        print("  실패:", f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", default=str(ROOT / "source"))
    ap.add_argument("--out", dest="out_dir", default=str(ROOT / "work" / "pdf"))
    ap.add_argument("--visible", action="store_true")
    a = ap.parse_args()
    convert_all(Path(a.in_dir), Path(a.out_dir), a.visible)


if __name__ == "__main__":
    main()
