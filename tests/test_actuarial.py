"""계리 계산 테스트."""

import numpy as np
import pandas as pd
import pytest

from actuarial.commutation import build_commutation
from actuarial.lifetable import apply_mortality_multiplier, compute_dx, compute_lx, get_qx, load_lifetable
from actuarial.product import (
    Expenses,
    gross_premium,
    monthly_premium,
    net_premium,
    projection,
    refund_rate,
    reserve,
    reserve_step,
    scenario_results,
    surrender_value,
    total_paid,
)

RAW_PATH = "data/raw/lifetable_2024_lx_qx.csv"


@pytest.fixture(scope="module")
def table():
    return load_lifetable()


# --- 생명표 ---

def test_shape(table):
    # 남녀 각 0~100세(100 = 100세 이상)
    for sex in ("M", "F"):
        assert len(get_qx(table, sex)) == 101


def test_q0_matches_pdf(table):
    assert get_qx(table, "M")[0] == pytest.approx(0.00261, abs=1e-12)
    assert get_qx(table, "F")[0] == pytest.approx(0.00214, abs=1e-12)


def test_l1_matches_pdf(table):
    # PDF 원문: l0 = 100,000, 남자 l1 = 99,739, 여자 l1 = 99,786
    lx_m = compute_lx(get_qx(table, "M"))
    lx_f = compute_lx(get_qx(table, "F"))
    assert lx_m[0] == 100_000 and lx_f[0] == 100_000
    assert round(lx_m[1]) == 99_739
    assert round(lx_f[1]) == 99_786


def test_last_age_qx_is_one(table):
    for sex in ("M", "F"):
        assert get_qx(table, sex)[-1] == 1.0


def test_dx_sums_to_radix(table):
    # 최고 연령 qx = 1이므로 모든 사람이 결국 사망
    for sex in ("M", "F"):
        assert compute_dx(get_qx(table, sex)).sum() == pytest.approx(100_000, rel=1e-12)


def test_lx_close_to_raw_pdf_lx(table):
    # 반올림된 qx로 계산한 lx와 PDF 원문 lx의 차이는 작아야 한다 (상대오차 1% 이내)
    raw = pd.read_csv(RAW_PATH)
    for sex, col in (("M", "male_lx"), ("F", "female_lx")):
        lx = compute_lx(get_qx(table, sex))
        np.testing.assert_allclose(lx, raw[col].to_numpy(dtype=float), rtol=1e-2)


def test_invalid_sex_raises(table):
    with pytest.raises(ValueError):
        get_qx(table, "X")


# --- 기수표 ---

RATES = [0.01, 0.025, 0.05]


@pytest.fixture(scope="module", params=[(s, i) for s in ("M", "F") for i in RATES])
def ct(request, table):
    sex, i = request.param
    return build_commutation(get_qx(table, sex), i)


def test_identity_A_equals_1_minus_d_a(ct):
    # A_x = 1 − d·ä_x, 모든 연령
    x = np.arange(ct.omega + 1)
    np.testing.assert_allclose(ct.A(x), 1.0 - ct.d * ct.a_due(x), rtol=0, atol=1e-10)


def test_commutation_definitions(ct):
    x = np.arange(ct.omega + 1)
    np.testing.assert_allclose(ct.Dx[x], ct.v**x * ct.lx[x], rtol=1e-14)
    np.testing.assert_allclose(ct.Cx[x], ct.v ** (x + 1) * ct.dx[x], rtol=1e-14)
    # Nx − N(x+1) = Dx, Mx − M(x+1) = Cx
    np.testing.assert_allclose(ct.Nx[x] - ct.Nx[x + 1], ct.Dx[x], rtol=1e-10, atol=1e-8)
    np.testing.assert_allclose(ct.Mx[x] - ct.Mx[x + 1], ct.Cx[x], rtol=1e-10, atol=1e-8)


def test_padding_beyond_omega_is_zero(ct):
    beyond = np.arange(ct.omega + 1, ct.omega + 50)
    for arr in (ct.Dx, ct.Nx, ct.Cx, ct.Mx):
        assert np.all(arr[beyond] == 0)
    # 표 밖까지 가는 기간도 동작: ä_{90:30} = ä_90 (101세 이후 생존자 없음)
    assert ct.a_due(90, 30) == pytest.approx(ct.a_due(90), rel=1e-14)


def test_temporary_annuity_bounds(ct):
    x = np.arange(15, 71)
    for m in (5, 7, 10):
        a_m = ct.a_due(x, m)
        assert np.all(a_m >= 1.0)
        assert np.all(a_m <= m)
        assert np.all(a_m <= ct.a_due(x))


def test_A_in_unit_interval_and_increasing_with_age(ct):
    A = ct.A(np.arange(ct.omega + 1))
    assert np.all((A > 0) & (A <= 1))
    assert np.all(np.diff(A[15:]) > 0)  # 성인 이후 나이가 많을수록 A_x 증가
    assert A[-1] == pytest.approx(ct.v)  # 최고 연령: 그해 말 확실히 사망


def test_zero_interest_A_is_one(table):
    # i = 0이면 언젠가 반드시 사망하므로 A_x = 1
    ct0 = build_commutation(get_qx(table, "M"), 0.0)
    np.testing.assert_allclose(ct0.A(np.arange(101)), 1.0, atol=1e-12)


def test_to_frame(table):
    df = build_commutation(get_qx(table, "F"), 0.025).to_frame()
    assert list(df.columns) == ["age", "lx", "dx", "Dx", "Nx", "Cx", "Mx"]
    assert len(df) == 101


# --- 상품: 단기납종신 ---

S = 100_000_000  # 가입금액 1억 원
AGES = [15, 30, 40, 55, 70]
TERMS = [5, 7, 10]
ZERO_EXP = Expenses(alpha=0, beta=0, beta_after=0, gamma=0)


def _cases():
    return [(x, m) for x in AGES for m in TERMS]


def test_net_premium_reference_value(table):
    # 2단계에서 확인한 참고값 (i=2.5%, 40세, 10년납, 1억)
    ct_m = build_commutation(get_qx(table, "M"), 0.025)
    ct_f = build_commutation(get_qx(table, "F"), 0.025)
    assert net_premium(ct_m, 40, 10, S) == pytest.approx(4_118_395, abs=1)
    assert net_premium(ct_f, 40, 10, S) == pytest.approx(3_557_201, abs=1)


def test_equivalence_principle(ct):
    # 수지상등: P·ä_{x:m} = S·A_x
    for x, m in _cases():
        P = net_premium(ct, x, m, S)
        assert P * ct.a_due(x, m) == pytest.approx(S * ct.A(x), rel=1e-12)


def test_reserve_zero_at_issue_nonnegative_increasing(ct):
    for x, m in _cases():
        k = np.arange(0, ct.omega - x + 1)
        kV = reserve(ct, x, m, S, k)
        assert kV[0] == pytest.approx(0.0, abs=1e-6)  # 0V = 0
        assert np.all(kV >= -1e-6)  # kV ≥ 0
        assert np.all(np.diff(kV) > 0)  # k에 대해 단조 증가


def test_reserve_after_payment_is_single_premium(ct):
    for x, m in _cases():
        k = np.arange(m, m + 10)
        np.testing.assert_allclose(reserve(ct, x, m, S, k), S * ct.A(x + k), rtol=1e-12)


def test_gross_equals_net_without_expenses(ct):
    for x, m in _cases():
        assert gross_premium(ct, x, m, S, ZERO_EXP) == pytest.approx(net_premium(ct, x, m, S), rel=1e-12)


def test_gross_greater_than_net_with_expenses(ct):
    for exp in (Expenses(), Expenses(0.01, 0, 0, 0), Expenses(0, 0.001, 0, 0),
                Expenses(0, 0, 0.001, 0), Expenses(0, 0, 0, 0.01)):
        for x, m in _cases():
            assert gross_premium(ct, x, m, S, exp) > net_premium(ct, x, m, S)


def test_surrender_value_bounds(ct):
    exp = Expenses()
    for x, m in _cases():
        k = np.arange(0, 31)
        kV = reserve(ct, x, m, S, k)
        cv = surrender_value(ct, x, m, S, k, exp)
        assert np.all(cv <= kV + 1e-6)  # CV_k ≤ kV (부동소수 오차 허용)
        assert np.all(cv >= 0)
        full = k >= min(m, 7)  # 상각 완료 후 CV_k = kV
        np.testing.assert_allclose(cv[full], kV[full], rtol=1e-12)


def test_monthly_premium_slightly_above_annual_over_12(ct):
    # ä^(12) < ä 이므로 월납 × 12 > 연납, 차이는 수 % 이내
    for x, m in _cases():
        G = gross_premium(ct, x, m, S)
        mp = monthly_premium(ct, x, m, G)
        assert G < 12 * mp < 1.05 * G


def test_refund_rate(table):
    ct25 = build_commutation(get_qx(table, "M"), 0.025)
    G = gross_premium(ct25, 40, 10, S)
    k = np.arange(0, 31)
    cv = surrender_value(ct25, 40, 10, S, k)
    rate = refund_rate(cv, G, 10, k)
    assert np.isnan(rate[0])  # 낸 보험료가 없으면 정의하지 않음
    np.testing.assert_allclose(rate[1:], cv[1:] / total_paid(G, 10, k[1:]) * 100, rtol=1e-12)


def test_projection_table(table):
    ct25 = build_commutation(get_qx(table, "F"), 0.025)
    df = projection(ct25, 40, 10, S)
    assert list(df["k"]) == list(range(31))
    assert list(df.columns) == ["k", "age", "reserve", "surrender_value", "total_paid", "refund_rate_pct"]
    # 70세 가입은 생명표 끝(100세)까지 30년
    assert len(projection(ct25, 70, 10, S)) == 31


def test_invalid_inputs(table):
    ct25 = build_commutation(get_qx(table, "M"), 0.025)
    with pytest.raises(ValueError):
        net_premium(ct25, 95, 10, S)  # 105세까지 납입 불가
    with pytest.raises(ValueError):
        reserve(ct25, 80, 10, S, 30)  # 110세는 표 밖
    with pytest.raises(ValueError):
        Expenses(gamma=1.0)


# --- 학습 모드: 준비금 재귀식, 가정 변경 시나리오 ---


def test_reserve_recursion(ct):
    # ((k−1)V + P)(1+i) = q_{x+k−1}·S + p_{x+k−1}·kV, 납입 후에는 P = 0
    for x, m in _cases():
        k = np.arange(1, ct.omega - x + 1)
        V = reserve(ct, x, m, S, np.arange(0, ct.omega - x + 1))
        age = x + k - 1
        q = ct.dx[age] / ct.lx[age]
        P = np.where(k <= m, net_premium(ct, x, m, S), 0.0)
        lhs = (V[:-1] + P) * (1 + ct.i)
        rhs = q * S + (1 - q) * V[1:]
        np.testing.assert_allclose(lhs, rhs, rtol=1e-9, atol=1e-4)


def test_reserve_step_waterfall_adds_up(ct):
    for x, m in _cases():
        for k in (1, m, m + 1, 25):
            st_ = reserve_step(ct, x, m, S, k)
            total = (st_["prev_reserve"] + st_["premium"] + st_["interest"]
                     - st_["death_cost"] + st_["survivor_share"])
            assert total == pytest.approx(st_["reserve"], rel=1e-9, abs=1e-4)
            assert (st_["premium"] > 0) == (k <= m)


def test_multiplier_one_matches_base_exactly(table):
    for sex in ("M", "F"):
        qx = get_qx(table, sex)
        assert np.array_equal(apply_mortality_multiplier(qx, 1.0), qx)
        base = scenario_results(build_commutation(qx, 0.025), 40, 10, S)
        scen = scenario_results(build_commutation(apply_mortality_multiplier(qx, 1.0, 30, 80), 0.025), 40, 10, S)
        for key in ("net_premium", "gross_premium", "reserve_k", "refund_rate_k"):
            assert scen[key] == base[key]


def test_multiplier_above_one_raises_net_premium(table):
    for sex in ("M", "F"):
        qx = get_qx(table, sex)
        for mult in (1.1, 2.0, 3.0):
            q2 = apply_mortality_multiplier(qx, mult)
            assert q2[-1] == 1.0 and np.all(q2 <= 1.0)
            for x, m in _cases():
                base = net_premium(build_commutation(qx, 0.025), x, m, S)
                assert net_premium(build_commutation(q2, 0.025), x, m, S) > base


def test_multiplier_age_range_and_validation(table):
    qx = get_qx(table, "M")
    q2 = apply_mortality_multiplier(qx, 2.0, 40, 60)
    np.testing.assert_array_equal(q2[:40], qx[:40])
    np.testing.assert_array_equal(q2[61:], qx[61:])
    np.testing.assert_allclose(q2[40:61], np.minimum(qx[40:61] * 2, 1))
    assert np.array_equal(get_qx(table, "M"), qx)  # 원본 불변
    with pytest.raises(ValueError):
        apply_mortality_multiplier(qx, 0)
    with pytest.raises(ValueError):
        apply_mortality_multiplier(qx, 2.0, 60, 40)
