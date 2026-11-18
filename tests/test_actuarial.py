"""계리 계산 테스트."""

import numpy as np
import pandas as pd
import pytest

from actuarial.commutation import build_commutation
from actuarial.lifetable import compute_dx, compute_lx, get_qx, load_lifetable

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
