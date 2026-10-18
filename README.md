# 중학 수학 학습지 자동 생성기

HWP 문제 파일 → 문항 PNG + `problems.json` → 조건(학년·단원·난이도·문항 수)에 맞는
A4 시험지 / 정답·해설지를 브라우저에서 생성·인쇄하는 프로젝트입니다.

```
1pbank/
├─ (동아출판) ...zip          # 원본 자료
├─ requirements.txt
├─ config/units.json           # 학년별 단원명, 학습지 종류 → 난이도 매핑 (수정 가능)
├─ scripts/
│   ├─ 00_unzip.py             # ZIP → source/*.hwp (한글 파일명 복원)
│   ├─ 01_hwp_to_pdf.py        # HWP → work/pdf/*.pdf   (한글 COM 자동화)
│   ├─ 02_pdf_to_pages.py      # PDF → work/pages/*.png + 문항 영역 자동 탐지 → work/crops.json
│   ├─ 03_build_problems.py    # crops.json → web/images/*.png + web/problems.json
│   └─ common.py               # 파일명 파서 / ID 생성
├─ tools/crop_editor.html      # 자동 탐지된 문항 영역을 눈으로 확인·수정하는 도구
└─ web/
    ├─ index.html              # 학습지 생성 웹 앱 (단일 파일, Tailwind CDN)
    ├─ problems.json           # 3단계 결과
    └─ images/                 # 문항/해설 PNG
```

> **원본 자료 구조에 대한 메모**
> 받은 HWP는 "문제 1개 = 파일 1개"가 아니라 **단원별 학습지(여러 문항) + 별도 해설 HWP** 입니다.
> 따라서 페이지를 렌더링한 뒤 **문항 단위로 자동 분할**하고, 해설은 같은 순번의 블록과 1:1로 짝지웁니다.
> 파일명이 `[중2]_[1단원]_[상]_001.hwp` 규칙이면 그대로 인식되고, 난이도도 파일명에서 읽습니다.

---

## 0. 준비 (최초 1회)

1. **Python 3.10 이상 설치** — https://www.python.org/downloads/ 에서 설치 시 *Add python.exe to PATH* 체크.
   (현재 PC에는 Microsoft Store 별칭만 있어 `python` 이 실제로 실행되지 않습니다.)
2. **한컴오피스 한글** 이 설치되어 있어야 1단계(HWP→PDF)가 동작합니다. (이 PC에는 등록되어 있음)
3. 패키지 설치:
   ```powershell
   cd C:\project\1pbank
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

---

## 1단계. HWP → PNG → problems.json

### 1-1. ZIP 풀기
```powershell
python scripts\00_unzip.py
```
`source/` 에 HWP 60여 개가 생성됩니다.

### 1-2. HWP → PDF (한글 자동화)
```powershell
python scripts\01_hwp_to_pdf.py            # source/*.hwp → work/pdf/*.pdf
python scripts\01_hwp_to_pdf.py --visible  # 한글 창을 보면서 진행 (문제 발생 시)
```
- 처음 실행 시 한글의 **보안 승인 창**이 뜨면 "모두 허용"을 누르세요.
- 한글이 없는 PC라면 HWP를 수동으로 **PDF로 저장** 해 `work/pdf/` 에 넣고 다음 단계로 진행하면 됩니다.

### 1-3. PDF → 페이지 PNG + 문항 영역 자동 탐지
```powershell
python scripts\02_pdf_to_pages.py                     # 기본 200dpi
python scripts\02_pdf_to_pages.py --min-gap 30        # 문항이 너무 잘게 나뉘면 값을 키움
python scripts\02_pdf_to_pages.py --min-gap 16        # 두 문항이 하나로 붙으면 값을 줄임
python scripts\02_pdf_to_pages.py --only 수학2_연산학습지_1단원 --reset   # 특정 파일만 재탐지
```
여백(빈 줄) 기반으로 2단 레이아웃을 인식하고 문항 블록을 나눕니다. 결과는 `work/crops.json` 에 저장됩니다.

### 1-4. 영역 확인·수정 (권장)
```powershell
python -m http.server 8000          # 프로젝트 루트에서 실행
```
브라우저에서 http://localhost:8000/tools/crop_editor.html 접속.
- 좌측에서 문서/페이지 선택 → 파란 상자가 자동 탐지된 문항입니다.
- 빈 곳 드래그 = 새 영역, 상자 드래그 = 이동, 우하단 핸들 = 크기, Del = 삭제.
- 문항 번호 순서가 어긋나면 **번호 재정렬** 버튼.
- **저장** 을 누르면(Chrome/Edge) `work/crops.json` 을 바로 덮어씁니다. 다른 브라우저는 다운로드 후 수동 교체.
- 문제 문서와 해설 문서의 **블록 수가 같아야** 해설이 올바르게 짝지어집니다. 3단계에서 불일치 시 경고가 출력됩니다.

### 1-5. 문항 이미지 잘라내기 + problems.json 생성
```powershell
python scripts\03_build_problems.py
python scripts\03_build_problems.py --answers answers.csv   # 정답 텍스트 일괄 입력 (id,answer)
```
`web/problems.json` 예시:
```json
{
  "id": "MATH_2_01_C_001",
  "grade": "중2",
  "unit": "1. 유리수와 순환소수",
  "unit_no": 1,
  "sheet_type": "연산학습지",
  "difficulty": "중",
  "image_url": "images/MATH_2_01_연산학습지_001.png",
  "answer": "",
  "explanation_image": "images/MATH_2_01_연산학습지_ans_001.png",
  "source": "(동아출판) 중학_수학2_연산학습지_1단원"
}
```
- **난이도**: 파일명에 `[상]/[중]/[하]` 가 있으면 그 값을, 없으면 `config/units.json` 의
  `_difficulty_by_sheet_type` 매핑(준비학습지=하, 연산학습지=중)을 사용합니다. 필요 시 JSON을 직접 수정해도 됩니다.
- **단원명**: `config/units.json` 테이블을 교과서 목차에 맞게 수정하세요(현재 값은 2022 개정 기준 추정치).
- **정답 텍스트**: HWP 해설에서 자동 추출하지 않습니다(OCR 미사용). 해설 이미지가 그 역할을 하며,
  정답표가 필요하면 `answers.csv` 로 입력하면 됩니다. 기존 problems.json 의 answer 값은 재생성 시 보존됩니다.

---

## 2단계. 웹 앱 실행

```powershell
python -m http.server 8000 --directory web
```
http://localhost:8000 접속 → `problems.json` 자동 로드.

- 데이터 없이 UI만 보려면 상단 **데모 데이터** 버튼 (SVG 가짜 문항 132개).
- `file://` 로 직접 열면 fetch 가 막히므로 **problems.json 직접 열기** 버튼으로 파일을 선택하면 됩니다
  (이 경우 이미지 경로가 index.html 기준 상대경로이므로 web/ 폴더에서 열어야 이미지가 보입니다).

### 기능
| 영역 | 내용 |
|---|---|
| 필터 | 학년(중1/2/3) → 단원 체크(난이도별 보유 수 표시) → 학습지 종류 → 전체 문항 수+비율 또는 난이도별 개수 |
| 검증 | 난이도/단원 부족 시 경고, 옵션으로 다른 난이도에서 자동 보충, 출제되지 않은 단원 안내 |
| 추출 | 단원 라운드로빈 + 무작위, 출제 순서는 하→중→상 |
| 미리보기 | A4(210×297mm) 2단 레이아웃, 1쪽 헤더(제목/이름/점수), 문항 번호 뱃지, 쪽 번호. 이미지 높이를 미리 계산해 **문항이 페이지 경계에서 잘리지 않도록** JS 로 페이지 분할 |
| 교체 | 미리보기에서 문항에 마우스를 올리면 **↻ 교체** → 같은 난이도의 다른 문제로 교체 |
| 출력 | **인쇄 / PDF 저장** (브라우저 인쇄창, `@page A4 margin 0`), **정답 및 해설지** 탭(정답표 + 해설 이미지 2단) |
| 교사용 | "문항 옆에 단원·난이도 표시" 체크 시 메타 정보 노출 |

---

## 3단계. Antigravity 환경에 배포·연결

앱은 **정적 파일 3종**(`index.html`, `problems.json`, `images/`)만 있으면 동작하므로 어떤 정적 호스팅에도 올릴 수 있습니다.

1. **Antigravity 에서 프로젝트 열기**: `C:\project\1pbank` 폴더를 워크스페이스로 엽니다.
2. **문제 DB 생성**: 위 1단계를 터미널에서 실행해 `web/problems.json` 과 `web/images/` 를 만듭니다.
3. **로컬 미리보기**: Antigravity 터미널에서 `python -m http.server 8000 --directory web` 실행 후
   내장 브라우저/프리뷰로 http://localhost:8000 을 엽니다. (Live Server 류 확장을 쓸 경우 루트를 `web/` 으로 지정)
4. **배포**:
   - 가장 단순: `web/` 폴더를 그대로 Netlify Drop / GitHub Pages / Vercel 정적 사이트로 업로드.
   - 사내망: `web/` 을 IIS·Nginx 의 정적 폴더에 복사.
   - 문항 이미지가 수천 장이면 `images/` 만 별도 CDN/스토리지에 두고 `problems.json` 의 `image_url` 을 절대 URL 로 바꾸면 됩니다
     (3단계 스크립트 실행 후 `sed`/파이썬으로 접두어 치환).
5. **데이터 갱신 흐름**: HWP 추가 → `00~03` 스크립트 재실행(이미 변환된 PDF·탐지된 문서는 건너뜀) → `web/` 재배포.
   problems.json 의 기존 `answer` 는 자동 보존됩니다.
6. Antigravity 에이전트에게 UI 수정을 맡길 때는 `web/index.html` 한 파일만 대상으로 지정하면 됩니다
   (외부 의존성은 Tailwind CDN 하나뿐).

---

## 자주 겪는 문제

| 증상 | 해결 |
|---|---|
| `python` 이 Store 를 열거나 아무 출력 없이 종료 | python.org 설치 후 `설정 > 앱 > 앱 실행 별칭` 에서 python 별칭 끄기 |
| 1단계에서 한글 보안 승인 창이 매번 뜸 | 한글 > 도구 > 환경 설정 > 기타 > *보안 모듈 등록* 혹은 그냥 "모두 허용" |
| 문항이 둘로 쪼개짐 / 둘이 붙음 | `--min-gap` 값을 조절해 `--reset` 으로 재탐지, 또는 crop_editor 로 수정 |
| 머리말·꼬리말이 문항으로 잡힘 | `--top-margin 0.09 --bottom-margin 0.07` 처럼 여백 비율을 키움 |
| 해설 매칭이 어긋남 | crop_editor 에서 문제 문서와 해설 문서의 블록 수·순서를 맞춘 뒤 3단계 재실행 |
| 인쇄 시 2쪽에 빈 페이지 | 브라우저 인쇄 설정에서 여백 "없음", 배율 100%, 머리글/바닥글 해제 |
