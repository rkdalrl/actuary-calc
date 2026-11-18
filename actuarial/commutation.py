"""기수표 D, N, C, M 계산."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from actuarial.lifetable import RADIX, compute_dx, compute_lx

# 최고 연령 뒤에 붙이는 0 패딩 길이 (x+n이 표 밖이어도 동작하도록)
PAD = 200


@dataclass(frozen=True)
class CommutationTable:
    """예정이율 i에서의 기수표. 배열 인덱스 = 연령, 최고 연령 뒤는 0으로 패딩."""

    i: float
    omega: int  # 표의 최고 연령 (예: 100)
    lx: np.ndarray
    dx: np.ndarray
    Dx: np.ndarray
    Nx: np.ndarray
    Cx: np.ndarray
    Mx: np.ndarray

    @property
    def v(self) -> float:
        return 1.0 / (1.0 + self.i)

    @property
    def d(self) -> float:
        return self.i / (1.0 + self.i)

    def A(self, x):
        """종신보험 일시납 순보험료 A_x = Mx / Dx."""
        x = np.asarray(x)
        return self.Mx[x] / self.Dx[x]

    def a_due(self, x, n=None):
        """기시급 연금 현가. n이 없으면 종신 ä_x = Nx/Dx, 있으면 ä_{x:n} = (Nx − N_{x+n})/Dx."""
        x = np.asarray(x)
        if n is None:
            return self.Nx[x] / self.Dx[x]
        n = np.asarray(n)
        return (self.Nx[x] - self.Nx[x + n]) / self.Dx[x]

    def E(self, x, n):
        """생존 할인율 nEx = D_{x+n} / Dx."""
        x, n = np.asarray(x), np.asarray(n)
        return self.Dx[x + n] / self.Dx[x]

    def to_frame(self) -> pd.DataFrame:
        """표 범위(0~omega)의 기수표를 DataFrame으로."""
        ages = np.arange(self.omega + 1)
        return pd.DataFrame(
            {
                "age": ages,
                "lx": self.lx[ages],
                "dx": self.dx[ages],
                "Dx": self.Dx[ages],
                "Nx": self.Nx[ages],
                "Cx": self.Cx[ages],
                "Mx": self.Mx[ages],
            }
        )


def build_commutation(qx: np.ndarray, i: float, radix: float = RADIX) -> CommutationTable:
    """qx와 예정이율 i로 기수표를 만든다."""
    if i <= -1:
        raise ValueError(f"예정이율이 올바르지 않습니다: {i}")
    qx = np.asarray(qx, dtype=float)
    omega = len(qx) - 1
    v = 1.0 / (1.0 + i)
    ages = np.arange(omega + 1)

    lx = compute_lx(qx, radix)
    dx = compute_dx(qx, radix)

    Dx = v**ages * lx
    Cx = v ** (ages + 1) * dx
    # Nx = Σ_{t≥x} Dt, Mx = Σ_{t≥x} Ct (뒤에서부터 누적합)
    Nx = np.cumsum(Dx[::-1])[::-1]
    Mx = np.cumsum(Cx[::-1])[::-1]

    pad = np.zeros(PAD)
    return CommutationTable(
        i=i,
        omega=omega,
        lx=np.concatenate((lx, pad)),
        dx=np.concatenate((dx, pad)),
        Dx=np.concatenate((Dx, pad)),
        Nx=np.concatenate((Nx, pad)),
        Cx=np.concatenate((Cx, pad)),
        Mx=np.concatenate((Mx, pad)),
    )
