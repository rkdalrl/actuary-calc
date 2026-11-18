# HANDOFF — 단기납종신 계리 계산기

> 이 문서는 에이전트 간 인수인계용. 작업을 시작하는 에이전트는 먼저 읽고, 끝낼 때 "현재 상태", "작업 로그", "다음 할 일"을 갱신한다.
> 설계와 공식은 `CLAUDE.md`가 기준이며, 설계를 바꿀 때는 CLAUDE.md도 같이 고치고 로그에 남긴다.

## 현재 상태
- 단계: **1 / 6 완료** (생명표 로드 + 검증 테스트 7개 통과, git 첫 커밋)
- 다음 담당: Claude Code (사용자 Mac)
- 폴더: `~/Desktop/就活/3. Actuary_cal` (git 저장소, 원격 없음)
- 구현된 파일: `actuarial/lifetable.py` (`load_lifetable`, `get_qx`, `compute_lx`, `compute_dx`), `tests/test_actuarial.py`, `requirements.txt`, `pytest.ini`(pythonpath 설정)
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

## 다음 할 일
1. CLAUDE.md "구현 순서" 2단계: `actuarial/commutation.py` (D, N, C, M; 표 밖 인덱스 0 패딩) → 항등식 A_x = 1 − d·ä_x 테스트 (허용오차 1e-10)
   - lx·dx는 `lifetable.compute_lx/compute_dx`를 그대로 쓰면 됨
