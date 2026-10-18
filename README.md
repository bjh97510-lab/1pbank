# 중학 수학 학습지 자동 생성기

HWP 문제 파일 → 문항 PNG + `problems.json` → 조건(학년·단원·난이도·문항 수)에 맞는
A4 시험지 / 정답·해설지를 브라우저에서 생성·인쇄하는 프로젝트입니다.

- 배포 주소: https://1pbank.vercel.app/
- 현재 데이터: 동아출판 2022 개정 중1·중2 연산학습지/준비학습지 **4,042문항** (모든 문항에 해설 이미지, 3,018문항에 정답 텍스트)

```
1pbank/
├─ (동아출판) ...zip          # 원본 자료 (저장소에는 올리지 않음)
├─ vercel.json / .vercelignore # Vercel 정적 배포 설정 (web/ 폴더만 서빙)
├─ config/units.json           # 학년별 단원명 (해설 PDF 에서 자동 추출), 학습지 종류 → 난이도 매핑
├─ scripts/
│   ├─ requirements.txt        # Python 의존성
│   ├─ 00_unzip.py             # ZIP → source/*.hwp (한글 파일명 복원)
│   ├─ 01_hwp_to_pdf.py        # HWP → work/pdf/*.pdf   (한글 COM 자동화)
│   ├─ 02_pdf_to_pages.py      # PDF → work/pages/*.png + 문항 영역 탐지 → work/crops.json
│   ├─ 03_build_problems.py    # crops.json → web/images/*.png + web/problems.json
│   ├─ extract_units.py        # 해설 PDF 에서 대단원 제목 읽어 config/units.json 갱신
│   ├─ debug_overlay.py        # 탐지 결과를 페이지 위에 그려 확인 (work/debug/*.png)
│   ├─ validate.py             # problems.json 무결성 검사 + 분포 출력
│   └─ common.py               # 파일명 파서 / 설정 로드
├─ tools/crop_editor.html      # 탐지된 문항 영역을 브라우저에서 확인·수정하는 도구
└─ web/
    ├─ index.html              # 학습지 생성 웹 앱 (단일 파일, Tailwind CDN)
    ├─ problems.json           # 문항 메타데이터
    └─ images/                 # 문항/해설 PNG (MATH_1_01_C_001.png, ..._ans.png)
```

> **원본 자료 구조에 대한 메모**
> 받은 HWP는 "문제 1개 = 파일 1개"가 아니라 **단원별 학습지(수십~수백 문항) + 별도 해설 HWP** 입니다.
> 그래서 PDF 로 변환한 뒤 **텍스트 레이어의 문항 번호(전용 글꼴·색)** 를 기준으로 문항을 잘라내고,
> 해설은 읽기 순서 n번째 문항 ↔ n번째 정답 으로 짝지었습니다 (모든 문서에서 개수가 정확히 일치).
> 파일명이 `[중2]_[1단원]_[상]_001.hwp` 규칙이면 그대로 인식되고, 난이도도 파일명에서 읽습니다.

---

## 0. 준비 (최초 1회)

1. **Python 3.10 이상** (이 PC에는 3.12 가 사용자 계정에 설치되어 있고 `.venv` 가 만들어져 있음)
2. **한컴오피스 한글** — 1단계(HWP→PDF)에만 필요
3. 패키지 설치:
   ```powershell
   cd C:\project\1pbank
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r scripts/requirements.txt
   ```

---

## 1단계. HWP → PNG → problems.json

```powershell
python scripts\00_unzip.py            # ZIP → source/*.hwp
python scripts\01_hwp_to_pdf.py       # source/*.hwp → work/pdf/*.pdf  (한글 창이 자동으로 열렸다 닫힘)
python scripts\02_pdf_to_pages.py     # PDF → 페이지 PNG + 문항 영역 탐지 → work/crops.json
python scripts\extract_units.py       # 해설 PDF 의 대단원 제목으로 config/units.json 갱신
python scripts\03_build_problems.py   # 문항 이미지 생성 + web/problems.json
python scripts\validate.py            # 무결성 검사 / 분포
```

- 1단계에서 한글의 **보안 승인 창**이 뜨면 "모두 허용". 한글이 없는 PC 라면 HWP 를 수동으로 PDF 저장해 `work/pdf/` 에 넣으면 됩니다.
- 2단계는 이미 처리된 문서를 건너뜁니다. 다시 탐지하려면 `--reset`, 특정 문서만은 `--only 수학2_연산학습지_1단원`.
- 3단계는 이미 있는 이미지를 다시 만들지 않습니다(메타데이터만 갱신). 이미지까지 다시 만들려면 `--force`.
- 로그에 `!! 확인 필요 N개` 가 나오면 그 문항은 영역 계산이 불안정했던 것이므로 아래 도구로 확인하세요.

### 문항 탐지 방식 (02_pdf_to_pages.py)
- 문항 번호는 `HanSantteutDotumBold` 글꼴 + 주황(연산)/분홍(준비) 색으로만 찍혀 있어 정확히 찾을 수 있습니다.
- `[06~10]` 같은 **묶음 지시문**은 범위 안의 각 문항 이미지 위에 함께 붙입니다. 지시문 옆에 놓인 그림이 아래 문항들 옆까지 이어지면 그림은 지시문 쪽에 넣고 문항은 그림 왼쪽까지만 자릅니다.
- 글자·선·그림은 "자기 위쪽에서 가장 가까운 번호 줄"에 소속시키고, 영역 = 번호 + 소속 요소의 합집합 (분수·트리 그림도 잘리지 않음).
- 원래 번호와 `[a~b]` 라벨은 흰색으로 지워서 학습지에서 새로 매기는 번호와 충돌하지 않습니다.
- 정답 텍스트는 수식 글꼴(HyhwpEQ) 의 숫자·기호·영문자를 복원해 추출합니다. 분수·순환소수 점 등 복원 불가한 기호가 있으면 이미지로만 제공됩니다.

### 확인·수정 도구
```powershell
python scripts\debug_overlay.py --doc 수학1_연산학습지_5단원 --page 1    # work/debug/*.png 에 영역을 그려 줌
python -m http.server 8000                                           # 프로젝트 루트에서
```
http://localhost:8000/tools/crop_editor.html 에서 파란 상자(문항)/초록 점선(지시문)/회색(지워지는 번호)을 확인하고
드래그로 이동·크기 조절, Del 로 삭제, **저장**(Chrome/Edge 는 work/crops.json 직접 덮어쓰기) 후 3단계를 `--force` 로 다시 실행합니다.

### problems.json 형식
```json
{
  "id": "MATH_2_01_C_001",
  "grade": "중2",
  "unit": "1. 유리수와 순환소수",
  "unit_no": 1,
  "sheet_type": "연산학습지",
  "section": 1,
  "num": "01",
  "difficulty": "하",
  "image_url": "images/MATH_2_01_C_001.png",
  "answer": "0.4",
  "explanation_image": "images/MATH_2_01_C_001_ans.png",
  "source": "(동아출판) 중학_수학2_연산학습지_1단원"
}
```
- **난이도**: 파일명에 `[상]/[중]/[하]` 가 있으면 그 값. 없으면 연산학습지는 **소단원 안에서의 위치**로 추정합니다
  (앞 1/3 = 하, 중간 = 중, 뒤 1/3 = 상 — 연산학습지가 쉬운 것부터 배열되는 점을 이용한 추정치). 준비학습지는 `하`.
  필요하면 `problems.json` 의 `difficulty` 를 직접 고치면 됩니다 (3단계를 다시 돌리면 덮어쓰이므로 주의).
- **정답 텍스트 수동 입력**: `id,answer` 형식 CSV 를 `--answers answers.csv` 로 넘기면 `answer_manual` 로 보존됩니다.

---

## 2단계. 웹 앱 실행

```powershell
python -m http.server 8000 --directory web
```
http://localhost:8000 접속 → `problems.json` 자동 로드. 데이터 없이 UI 만 보려면 **데모 데이터** 버튼.

| 영역 | 내용 |
|---|---|
| 필터 | 학년 → 단원 체크(난이도별 보유 수 표시) → 학습지 종류 → 전체 문항 수+비율 또는 난이도별 개수 |
| 검증 | 난이도/단원 부족 시 경고, 다른 난이도에서 자동 보충 옵션, 출제되지 않은 단원 안내 |
| 추출 | 단원 라운드로빈 + 무작위, 출제 순서는 하→중→상 |
| 미리보기 | A4 2단, 1쪽 헤더(제목/이름/점수), 번호 뱃지, 쪽 번호. 이미지 높이를 미리 계산해 문항이 페이지 경계에서 잘리지 않게 분할 |
| 교체 | 문항에 마우스를 올리면 **↻ 교체** → 같은 난이도의 다른 문제로 교체 |
| 풀이 공간 | 문항마다 점 격자 풀이 공간(없음~40mm)과 **정답** 기입란, 문제 글자 크기(90~120%) 선택 |
| 출제 순서 | 하→중→상(기본) / 상→중→하 / 무작위 |
| 출력 | **인쇄 / PDF 저장**, **정답 및 해설지** 탭(정답표 + 해설 이미지 2단) |

URL 파라미터로 바로 생성할 수도 있습니다 (Antigravity 프리뷰·자동화용):
`index.html?auto=1&grade=중2&n=20&work=20&ans=1&order=asc&scale=100&meta=0&tab=exam&title=...&school=...`

문항 이미지는 200dpi 로 만들어졌으므로 인쇄 시 원본 학습지와 같은 크기로 나옵니다 (단 폭을 넘는 경우만 축소).

---

## 3단계. 배포 (Vercel / Antigravity)

- **Vercel**: GitHub 저장소를 Import 하면 끝. 루트의 `vercel.json` 이 "빌드 없음, `web/` 폴더를 정적으로 서빙" 으로 설정되어 있고
  `.vercelignore` 가 스크립트·원본 자료를 업로드에서 제외합니다. `/web` 으로 접속해도 루트로 리다이렉트됩니다.
  (설정이 없으면 Vercel 이 requirements.txt 를 보고 Python 앱으로 오인해 `PYTHON_ENTRYPOINT_NOT_FOUND` 오류가 납니다.)
- **Antigravity**: `C:\project\1pbank` 를 워크스페이스로 열고, 터미널에서 `python -m http.server 8000 --directory web` 으로 미리보기.
  UI 수정은 `web/index.html` 한 파일만 대상으로 지정하면 됩니다 (외부 의존성은 Tailwind CDN 하나).
- **데이터 갱신 흐름**: HWP 추가 → `00~03` 재실행(이미 변환·탐지된 문서는 건너뜀) → `web/` 커밋·푸시 → Vercel 자동 배포.
- 문항 이미지가 더 커지면 `images/` 만 별도 스토리지에 두고 `image_url` 을 절대 URL 로 바꿀 수 있습니다.

---

## 자주 겪는 문제

| 증상 | 해결 |
|---|---|
| `python` 이 Store 를 열거나 아무 출력 없이 종료 | python.org / winget 으로 설치 후 `설정 > 앱 > 앱 실행 별칭` 에서 python 별칭 끄기 |
| 1단계에서 한글 보안 승인 창이 매번 뜸 | "모두 허용" 또는 한글 > 도구 > 환경 설정 > 기타 > 보안 모듈 등록 |
| 문항이 잘못 잘림 | `debug_overlay.py` 로 확인 → `crop_editor.html` 로 수정 → `03 --force` |
| 문항/정답 개수 불일치 경고 | 개수가 같으면 순서대로 매칭(출판사 번호 오타에 안전). 다르면 crop_editor 로 맞춘 뒤 재실행 |
| 인쇄 시 빈 페이지 | 브라우저 인쇄 설정에서 여백 "없음", 배율 100%, 머리글/바닥글 해제 |
