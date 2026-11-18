"""단기납종신보험(m년납 종신보험): 보험료, 준비금, 해지환급금, 환급률."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from actuarial.commutation import CommutationTable

# 해지공제(미상각 신계약비) 최대 상각기간 (년)
MAX_AMORTIZATION_YEARS = 7


@dataclass(frozen=True)
class Expenses:
    """사업비 가정 (모두 비율). 기본값은 예시이며 실제 상품 값이 아님."""

    alpha: float = 0.03  # 신계약비: 가입금액 대비, 계약 시 1회
    beta: float = 0.003  # 납입 중 유지비: 가입금액 대비, 납입기간 중 매년
    beta_after: float = 0.001  # 납입 후 유지비(β'): 가입금액 대비, 납입 완료 후 매년
    gamma: float = 0.02  # 수금비: 영업보험료 대비, 납입기간 중 매년

    def __post_init__(self):
        for name in ("alpha", "beta", "beta_after", "gamma"):
            if getattr(self, name) < 0:
                raise ValueError(f"사업비 {name}는 음수일 수 없습니다")
        if self.gamma >= 1:
            raise ValueError("수금비 γ는 1보다 작아야 합니다")


def _check_inputs(ct: CommutationTable, x: int, m: int) -> None:
    if m <= 0:
        raise ValueError(f"납입기간은 양수여야 합니다: {m}")
    if not 0 <= x <= ct.omega - m:
        raise ValueError(f"가입연령 {x}세, 납입기간 {m}년은 생명표 범위(0~{ct.omega}세) 밖입니다")


def net_premium(ct: CommutationTable, x: int, m: int, S: float) -> float:
    """연납 순보험료 P = S·A_x / ä_{x:m}."""
    _check_inputs(ct, x, m)
    return float(S * ct.A(x) / ct.a_due(x, m))


def gross_premium(ct: CommutationTable, x: int, m: int, S: float, exp: Expenses = Expenses()) -> float:
    """연납 영업보험료 (수지상등).

    G = [S·A_x + α·S + β·S·ä_{x:m} + β'·S·(ä_x − ä_{x:m})] / [(1 − γ)·ä_{x:m}]
    """
    _check_inputs(ct, x, m)
    a_m = ct.a_due(x, m)
    a_whole = ct.a_due(x)
    outgo = S * ct.A(x) + exp.alpha * S + exp.beta * S * a_m + exp.beta_after * S * (a_whole - a_m)
    return float(outgo / ((1.0 - exp.gamma) * a_m))


def a_due_monthly(ct: CommutationTable, x: int, m: int) -> float:
    """월납 기시급 유기연금 현가 (Woolhouse 2항 근사).

    ä^(12)_{x:m} ≈ ä_{x:m} − (11/24)·(1 − mEx)
    """
    _check_inputs(ct, x, m)
    return float(ct.a_due(x, m) - 11.0 / 24.0 * (1.0 - ct.E(x, m)))


def monthly_premium(ct: CommutationTable, x: int, m: int, annual_premium: float) -> float:
    """연납 보험료를 같은 현가의 월납 보험료로 환산 (근사치).

    월납 = (연납 · ä_{x:m} / ä^(12)_{x:m}) / 12
    """
    return float(annual_premium * ct.a_due(x, m) / a_due_monthly(ct, x, m) / 12.0)


def _check_k(ct: CommutationTable, x: int, k: np.ndarray) -> None:
    if np.any(k < 0) or np.any(x + k > ct.omega):
        raise ValueError(f"경과연도는 0 이상, 가입연령 + 경과연도 ≤ {ct.omega}이어야 합니다")


def reserve(ct: CommutationTable, x: int, m: int, S: float, k) -> np.ndarray:
    """순보험료식 책임준비금 (장래법, 경과 k년 말).

    k < m: kV = S·A_{x+k} − P·ä_{x+k : m−k}
    k ≥ m: kV = S·A_{x+k}
    """
    k = np.atleast_1d(np.asarray(k, dtype=int))
    _check_k(ct, x, k)
    P = net_premium(ct, x, m, S)
    remaining = np.maximum(m - k, 0)  # 남은 납입기간 (0이면 연금 현가 = 0)
    return S * ct.A(x + k) - P * ct.a_due(x + k, remaining)


def unamortized_acquisition(k, m: int, S: float, alpha: float) -> np.ndarray:
    """미상각 신계약비 = α·S·max(0, 1 − k / min(m, 7)) (정액 상각)."""
    k = np.atleast_1d(np.asarray(k, dtype=float))
    period = min(m, MAX_AMORTIZATION_YEARS)
    return alpha * S * np.maximum(0.0, 1.0 - k / period)


def surrender_value(ct: CommutationTable, x: int, m: int, S: float, k, exp: Expenses = Expenses()) -> np.ndarray:
    """해지환급금 (근사) CV_k = max(0, kV − 미상각 신계약비_k).

    실제 표준해약공제·저해지/무해지 구조와 다른 단순 근사다.
    """
    kV = reserve(ct, x, m, S, k)
    return np.maximum(0.0, kV - unamortized_acquisition(k, m, S, exp.alpha))


def total_paid(G: float, m: int, k) -> np.ndarray:
    """경과 k년 말까지 낸 총 영업보험료 = G·min(k, m)."""
    k = np.atleast_1d(np.asarray(k, dtype=float))
    return G * np.minimum(k, m)


def refund_rate(cv, G: float, m: int, k) -> np.ndarray:
    """환급률(%) = CV_k / (G·min(k, m)) × 100. 낸 보험료가 0인 k = 0은 NaN."""
    paid = total_paid(G, m, k)
    cv = np.atleast_1d(np.asarray(cv, dtype=float))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(paid > 0, cv / paid * 100.0, np.nan)


def projection(
    ct: CommutationTable,
    x: int,
    m: int,
    S: float,
    exp: Expenses = Expenses(),
    years: int = 30,
) -> pd.DataFrame:
    """경과연도 k = 0~years(생명표 끝까지)의 준비금·환급금·환급률 표."""
    k = np.arange(0, min(years, ct.omega - x) + 1)
    G = gross_premium(ct, x, m, S, exp)
    kV = reserve(ct, x, m, S, k)
    cv = surrender_value(ct, x, m, S, k, exp)
    return pd.DataFrame(
        {
            "k": k,
            "age": x + k,
            "reserve": kV,
            "surrender_value": cv,
            "total_paid": total_paid(G, m, k),
            "refund_rate_pct": refund_rate(cv, G, m, k),
        }
    )


def reserve_step(ct: CommutationTable, x: int, m: int, S: float, k: int) -> dict:
    """경과 k년째 1년 동안 준비금이 쌓이는 과정 (학습 모드 폭포형 차트용).

    재귀식: ((k−1)V + P)(1+i) = q·S + p·kV   (납입 후에는 P = 0)
    (k−1)V → + P → + 이자 → − 사망보험금 기대지급 q·S → + 생존자 분배 q·kV → kV
    """
    if k < 1:
        raise ValueError("경과연도 k는 1 이상이어야 합니다")
    prev_V, V = reserve(ct, x, m, S, [k - 1, k])
    age = x + k - 1  # 그해 초의 연령
    q = ct.dx[age] / ct.lx[age]
    P = net_premium(ct, x, m, S) if k <= m else 0.0  # k년째 초에 보험료를 내는지
    interest = (prev_V + P) * ct.i
    death_cost = q * S
    survivor_share = q * V  # 사망자 몫의 준비금이 생존자에게 넘어감 (p·kV → kV)
    return {
        "k": k,
        "age": age,
        "q": q,
        "p": 1.0 - q,
        "prev_reserve": prev_V,
        "premium": P,
        "interest": interest,
        "death_cost": death_cost,
        "survivor_share": survivor_share,
        "reserve": V,
    }


def scenario_results(ct: CommutationTable, x: int, m: int, S: float, exp: Expenses = Expenses(), k: int = 10) -> dict:
    """가정 변경 시나리오 비교용 핵심 결과. 시나리오는 바뀐 qx·i로 만든 CommutationTable을 넘긴다."""
    proj = projection(ct, x, m, S, exp)
    row = proj.loc[proj["k"] == k].iloc[0]
    return {
        "net_premium": net_premium(ct, x, m, S),
        "gross_premium": gross_premium(ct, x, m, S, exp),
        "reserve_k": float(row["reserve"]),
        "refund_rate_k": float(row["refund_rate_pct"]),
        "projection": proj,
    }
