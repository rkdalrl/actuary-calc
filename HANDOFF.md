# HANDOFF — 단기납종신 계리 계산기

> 이 문서는 에이전트 간 인수인계용. 작업을 시작하는 에이전트는 먼저 읽고, 끝낼 때 "현재 상태", "작업 로그", "다음 할 일"을 갱신한다.
> 설계와 공식은 `CLAUDE.md`가 기준이며, 설계를 바꿀 때는 CLAUDE.md도 같이 고치고 로그에 남긴다.

## 현재 상태
- 단계: **2 / 6 완료** (기수표 + 항등식 테스트, 전체 테스트 39개 통과)
- 다음 담당: Claude Code (사용자 Mac)
- 폴더: `~/Desktop/就活/3. Actuary_cal` (git 저장소, 원격 없음)
- 구현된 파일: `actuarial/lifetable.py` (`load_lifetable`, `get_qx`, `compute_lx`, `compute_dx`), `actuarial/commutation.py` (`build_commutation(qx, i)` → `CommutationTable`: 배열 `lx, dx, Dx, Nx, Cx, Mx`(최고연령 뒤 0 패딩 200칸), 메서드 `A(x)`, `a_due(x, n=None)`, `E(x, n)`, `to_frame()`, 속성 `v`, `d`), `tests/test_actuarial.py`, `requirements.txt`, `pytest.ini`(pythonpath 설정)
- 테스트 실행: 폴더에서 `python3 -m pytest -q`

## 확정된 결정사항
| 항목 | 결정 | 결정일 |
|---|---|---|
| 상품 | 단기납종신보험 (5·7·10년납) | 2026-11-18 |
| 범위 | 순보험료 + 영업보험료(사업비 α·β·β'·γ) + 준비금 + 해지환급금 + 환급률 | 2026-11-18 |
| 해지환급금 | 근사치 (준비금 − 미상각 신계약비, 상각기간 min(m,7)) | 2026-11-18 |
| 데이터 | 통계청 2024 완전생명표 (lifetable.de PDF 경유) | 2026-11-18 |
| 스택 | Python + Streamlit | 2026-11-18 |
| 구현 담당 | Claude Code | 2026-11-18 |

## 미해결 / 확인 필요
- [x] 생명표 확보 완료: 최고연령 구간은 "100+" (qx=1.00000)
- [ ] 사업비 기본값은 예시값 (실제 상품 수준 아님)
- [ ] 해지공제 상각기간 min(m,7) 규정 재확인 필요
- [ ] 2025 생명표 공표(2026년 12월 예상) 시 데이터 교체 검토

## 작업 로그
- 2026-11-18 (채팅 Claude): 요구사항 정리, CLAUDE.md 설계서 작성, 본 문서 생성. 클라우드 환경에서 생명표 다운로드 시도 → 네트워크 차단(403)으로 실패, 1단계에서 Mac에서 받도록 설계.
- 2026-11-18 (채팅 Claude): 원격 VM에서도 다운로드 시도 → 403 차단. `data/raw/` 폴더만 생성됨. Claude Code(Mac 로컬 터미널)에서 받으면 됨. 실패 시 사용자가 브라우저로 PDF를 받아 `data/raw/kor2024.pdf`로 저장.
- 2026-11-18 (채팅 Claude): 웹 가져오기 도구로 PDF 표 추출 → `data/lifetable_2024.csv`, `data/raw/lifetable_2024_lx_qx.csv` 저장. 남녀 각 0~100+세(101행), lx–qx 일관성 검증 200건 전부 통과.
- 2026-11-18 (Claude Code): 1단계 완료. `actuarial/lifetable.py` 작성(CSV 형식 검증: 열·성별·연령 연속성·qx 범위·최고연령 qx=1). 테스트 7개 통과(q0·l1 검증값, 101행, dx 합 = l0, 원본 PDF lx와 상대오차 1% 이내, 잘못된 성별 예외). 수집 스크립트(`scripts/fetch_lifetable.py`)는 선택 사항이라 생략. git init 후 첫 커밋.
- 2026-11-18 (Claude Code): 2단계 완료. `actuarial/commutation.py` 작성. 테스트 추가(i = 1%·2.5%·5% × 남녀): A_x = 1 − d·ä_x(1e-10), D·C 정의 및 N·M 차분, 표 밖 0 패딩, ä_{x:m} 범위, A_x 범위·연령 증가, i=0이면 A_x=1, to_frame. 전체 39개 통과. 커밋.

## 다음 할 일
1. CLAUDE.md "구현 순서" 3단계: `actuarial/product.py` (순보험료 P, 영업보험료 G, 월납 환산, 준비금 kV, 해지환급금 CV, 환급률) → CLAUDE.md 4절 나머지 테스트
   - A_x, ä_x, ä_{x:m}, mEx는 `CommutationTable.A / a_due / E`를 쓰면 됨 (배열 인덱스 입력도 가능)
   - 참고값(i=2.5%, 1억, 40세, 10년납 순보험료): 남 약 4,118,395원, 여 약 3,557,201원
