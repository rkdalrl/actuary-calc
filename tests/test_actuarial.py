"""계리 계산 테스트."""

import numpy as np
import pandas as pd
import pytest

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
