"""생명표 로드와 lx·dx 계산."""

from pathlib import Path

import numpy as np
import pandas as pd

# 기본 생명표 파일 (통계청 2024 완전생명표)
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "lifetable_2024.csv"

# 기수 l0
RADIX = 100_000


def load_lifetable(path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    """생명표 CSV(sex, age, qx)를 읽고 형식을 검증한다."""
    df = pd.read_csv(path, dtype={"sex": str, "age": int, "qx": float})

    if set(df.columns) != {"sex", "age", "qx"}:
        raise ValueError(f"열 이름이 예상과 다릅니다: {list(df.columns)}")
    if set(df["sex"]) != {"M", "F"}:
        raise ValueError(f"성별 값이 예상과 다릅니다: {sorted(set(df['sex']))}")

    for sex, g in df.groupby("sex"):
        ages = g["age"].to_numpy()
        # 연령은 0부터 1세 간격으로 빠짐없이 있어야 한다
        if not np.array_equal(ages, np.arange(len(ages))):
            raise ValueError(f"{sex}: 연령이 0부터 연속적이지 않습니다")
        qx = g["qx"].to_numpy()
        if np.any((qx < 0) | (qx > 1)):
            raise ValueError(f"{sex}: qx가 0~1 범위를 벗어났습니다")
        # 최고 연령 구간("100세 이상")은 qx = 1.0
        if qx[-1] != 1.0:
            raise ValueError(f"{sex}: 최고 연령의 qx가 1.0이 아닙니다")

    return df.sort_values(["sex", "age"]).reset_index(drop=True)


def get_qx(df: pd.DataFrame, sex: str) -> np.ndarray:
    """성별('M' 또는 'F')의 qx 배열. 인덱스 = 연령."""
    if sex not in ("M", "F"):
        raise ValueError(f"성별은 'M' 또는 'F'여야 합니다: {sex}")
    return df.loc[df["sex"] == sex, "qx"].to_numpy(dtype=float)


def compute_lx(qx: np.ndarray, radix: float = RADIX) -> np.ndarray:
    """l0 = radix, l(x+1) = l(x)·(1 − q(x))."""
    survival = np.concatenate(([1.0], np.cumprod(1.0 - qx[:-1])))
    return radix * survival


def compute_dx(qx: np.ndarray, radix: float = RADIX) -> np.ndarray:
    """dx = lx · qx (최고 연령에서는 dx = lx)."""
    return compute_lx(qx, radix) * qx


def apply_mortality_multiplier(
    qx: np.ndarray, multiplier: float, age_from: int = 0, age_to: int | None = None
) -> np.ndarray:
    """가정 변경 시나리오용 qx: 연령 구간 [age_from, age_to]에 min(qx × 배수, 1) 적용.

    최고 연령의 qx = 1은 그대로 유지한다. 원본 배열은 바꾸지 않는다.
    """
    if multiplier <= 0:
        raise ValueError(f"사망률 배수는 양수여야 합니다: {multiplier}")
    omega = len(qx) - 1
    age_to = omega if age_to is None else age_to
    if not 0 <= age_from <= age_to <= omega:
        raise ValueError(f"적용 연령 구간이 올바르지 않습니다: {age_from}~{age_to}")
    q = np.array(qx, dtype=float)
    q[age_from : age_to + 1] = np.minimum(q[age_from : age_to + 1] * multiplier, 1.0)
    q[omega] = 1.0
    return q
