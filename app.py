"""단기납종신보험 보험료·준비금·환급률 계산기 (Streamlit 화면)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from actuarial.commutation import build_commutation
from actuarial.lifetable import get_qx, load_lifetable
from actuarial.product import (
    Expenses,
    gross_premium,
    monthly_premium,
    net_premium,
    projection,
)

st.set_page_config(page_title="단기납종신 계리 계산기", page_icon="📊", layout="wide")


@st.cache_data
def cached_lifetable() -> pd.DataFrame:
    return load_lifetable()


def won(value: float) -> str:
    """원 단위 표시 (표시할 때만 반올림)."""
    return f"{value:,.0f}원"


# --- 사이드바 입력 ---
st.sidebar.header("가입 조건")
sex_label = st.sidebar.radio("성별", ["남자", "여자"], horizontal=True)
sex = "M" if sex_label == "남자" else "F"
x = st.sidebar.slider("가입연령 (세)", min_value=15, max_value=70, value=40)
m = st.sidebar.selectbox("납입기간 (년)", [5, 7, 10], index=2)
S = st.sidebar.number_input(
    "가입금액 (원)", min_value=10_000_000, max_value=10_000_000_000, value=100_000_000, step=10_000_000
)
i_pct = st.sidebar.number_input("예정이율 (%)", min_value=1.0, max_value=5.0, value=2.5, step=0.25, format="%.2f")

st.sidebar.header("사업비 (예시값)")
alpha_pct = st.sidebar.number_input("α 신계약비 (가입금액 대비 %, 1회)", 0.0, 20.0, 3.0, 0.1, format="%.2f")
beta_pct = st.sidebar.number_input("β 납입 중 유지비 (가입금액 대비 %, 매년)", 0.0, 5.0, 0.3, 0.05, format="%.2f")
beta_after_pct = st.sidebar.number_input("β' 납입 후 유지비 (가입금액 대비 %, 매년)", 0.0, 5.0, 0.1, 0.05, format="%.2f")
gamma_pct = st.sidebar.number_input("γ 수금비 (영업보험료 대비 %, 납입 중)", 0.0, 50.0, 2.0, 0.5, format="%.2f")
st.sidebar.caption("사업비 기본값은 예시이며 실제 상품의 사업비가 아닙니다.")

i = i_pct / 100
exp = Expenses(alpha=alpha_pct / 100, beta=beta_pct / 100, beta_after=beta_after_pct / 100, gamma=gamma_pct / 100)

# --- 계산 ---
qx = get_qx(cached_lifetable(), sex)
ct = build_commutation(qx, i)
P = net_premium(ct, x, m, S)
G = gross_premium(ct, x, m, S, exp)
P_month = monthly_premium(ct, x, m, P)
G_month = monthly_premium(ct, x, m, G)
proj = projection(ct, x, m, S, exp, years=30)

# --- 상단 지표 ---
st.title("단기납종신보험 계리 계산기")
st.caption(
    f"{sex_label} {x}세 · {m}년납 종신 · 가입금액 {won(S)} · 예정이율 {i_pct:.2f}% · 통계청 2024 완전생명표"
)

c1, c2, c3 = st.columns(3)
c1.metric("순보험료 (연납)", won(P))
c1.metric("순보험료 (월납, 근사치)", won(P_month))
c2.metric("영업보험료 (연납)", won(G))
c2.metric("영업보험료 (월납, 근사치)", won(G_month))
c3.metric("총납입보험료 (연납 기준)", won(G * m))
st.caption("월납 보험료는 Woolhouse 2항 근사로 환산한 근사치입니다.")

tab1, tab2, tab3 = st.tabs(["준비금·환급금", "민감도", "계산식·기수표"])

# --- 탭 1: 준비금·환급금 ---
with tab1:
    rate10 = proj.loc[proj["k"] == 10, "refund_rate_pct"].iloc[0]
    rate_m = proj.loc[proj["k"] == m, "refund_rate_pct"].iloc[0]
    a, b, _ = st.columns([1, 1, 2])
    a.metric("⭐ 10년 시점 환급률", f"{rate10:.1f}%")
    b.metric(f"납입 완료({m}년) 시점 환급률", f"{rate_m:.1f}%")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=proj["k"], y=proj["reserve"], name="책임준비금", mode="lines"))
    fig.add_trace(go.Scatter(x=proj["k"], y=proj["surrender_value"], name="해지환급금 (근사)", mode="lines"))
    fig.add_trace(
        go.Scatter(x=proj["k"], y=proj["total_paid"], name="총납입보험료", mode="lines", line=dict(dash="dash"))
    )
    fig.add_vline(x=10, line_dash="dot", line_color="gray", annotation_text="10년")
    fig.update_layout(
        xaxis_title="경과연도 (년)",
        yaxis_title="금액 (원)",
        yaxis_tickformat=",",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    table = pd.DataFrame(
        {
            "경과연도": proj["k"],
            "연령": proj["age"],
            "책임준비금": proj["reserve"],
            "해지환급금(근사)": proj["surrender_value"],
            "총납입보험료": proj["total_paid"],
            # k = 0은 낸 보험료가 없어 환급률이 정의되지 않으므로 "-"로 표시
            "환급률(%)": [("-" if np.isnan(v) else f"{v:.1f}") for v in proj["refund_rate_pct"]],
        }
    )

    def highlight_10(row):
        style = "background-color: rgba(255, 200, 0, 0.3); font-weight: bold" if row["경과연도"] == 10 else ""
        return [style] * len(row)

    styled = table.style.apply(highlight_10, axis=1).format(
        {
            "책임준비금": "{:,.0f}",
            "해지환급금(근사)": "{:,.0f}",
            "총납입보험료": "{:,.0f}",
        }
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=420)
    st.caption(
        "해지환급금은 '책임준비금 − 미상각 신계약비(상각기간 min(납입기간, 7년), 정액)'의 단순 근사입니다. "
        "실제 표준해약공제나 저해지·무해지 구조와 다르며, 시판 단기납종신은 저해지 구조와 납입 후 가산 등으로 "
        "10년 시점 환급률이 더 높게 설계되므로 이 계산기의 결과가 더 낮게 나오는 것이 정상입니다."
    )

# --- 탭 2: 민감도 ---
with tab2:
    rates = np.round(np.arange(1.0, 5.0 + 1e-9, 0.25), 2)
    gross_by_rate = [gross_premium(build_commutation(qx, r / 100), x, m, S, exp) for r in rates]

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=rates, y=gross_by_rate, mode="lines+markers", name="영업보험료 (연납)"))
    fig2.add_trace(
        go.Scatter(
            x=[i_pct], y=[G], mode="markers", name="현재 예정이율", marker=dict(size=14, symbol="star")
        )
    )
    fig2.update_layout(
        xaxis_title="예정이율 (%)",
        yaxis_title="영업보험료 연납 (원)",
        yaxis_tickformat=",",
        legend=dict(orientation="h", y=1.1),
        margin=dict(t=40),
    )
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("예정이율이 높을수록 미래 보험금의 현재가치가 작아져 보험료가 낮아집니다. (다른 조건은 그대로)")

    sens = pd.DataFrame({"예정이율(%)": rates, "영업보험료(연납)": gross_by_rate})
    st.dataframe(
        sens.style.format({"예정이율(%)": "{:.2f}", "영업보험료(연납)": "{:,.0f}"}),
        use_container_width=True,
        hide_index=True,
    )

# --- 탭 3: 계산식·기수표 ---
with tab3:
    st.subheader("가정")
    st.markdown(
        "- 연 1회 연초 납입, 사망보험금은 사망 연도 말 지급 (이산 모형)\n"
        "- 예정이율 $i$, $v = 1/(1+i)$, $d = i/(1+i)$"
    )

    st.subheader("기수표")
    st.latex(r"D_x = v^x l_x \qquad N_x = \sum_{t \ge x} D_t \qquad C_x = v^{x+1} d_x \qquad M_x = \sum_{t \ge x} C_t")
    st.latex(r"A_x = \frac{M_x}{D_x} \qquad \ddot{a}_{x:\overline{m}|} = \frac{N_x - N_{x+m}}{D_x} \qquad \ddot{a}_x = \frac{N_x}{D_x}")

    st.subheader("보험료")
    st.latex(r"P = \frac{S \cdot A_x}{\ddot{a}_{x:\overline{m}|}}")
    st.latex(
        r"G = \frac{S A_x + \alpha S + \beta S\, \ddot{a}_{x:\overline{m}|} + \beta' S\,(\ddot{a}_x - \ddot{a}_{x:\overline{m}|})}"
        r"{(1-\gamma)\, \ddot{a}_{x:\overline{m}|}}"
    )
    st.markdown("월납 환산 (Woolhouse 2항 근사):")
    st.latex(
        r"\ddot{a}^{(12)}_{x:\overline{m}|} \approx \ddot{a}_{x:\overline{m}|} - \frac{11}{24}\left(1 - {}_mE_x\right),"
        r"\quad {}_mE_x = \frac{D_{x+m}}{D_x},"
        r"\quad \text{월납} = \frac{\text{연납} \cdot \ddot{a}_{x:\overline{m}|} / \ddot{a}^{(12)}_{x:\overline{m}|}}{12}"
    )

    st.subheader("책임준비금 (순보험료식, 장래법)")
    st.latex(
        r"{}_kV = \begin{cases} S\,A_{x+k} - P\,\ddot{a}_{x+k:\overline{m-k}|} & (k < m) \\ S\,A_{x+k} & (k \ge m) \end{cases}"
    )

    st.subheader("해지환급금 (근사)·환급률")
    st.latex(r"\text{미상각 신계약비}_k = \alpha S \cdot \max\!\left(0,\ 1 - \frac{k}{\min(m, 7)}\right)")
    st.latex(r"CV_k = \max\left(0,\ {}_kV - \text{미상각 신계약비}_k\right)")
    st.latex(r"\text{환급률}_k = \frac{CV_k}{G \cdot \min(k, m)} \times 100\%")

    st.subheader(f"기수표 ({sex_label}, 예정이율 {i_pct:.2f}%)")
    comm = ct.to_frame()
    st.dataframe(
        comm.style.format({c: "{:,.4f}" for c in ["lx", "dx", "Dx", "Nx", "Cx", "Mx"]}),
        use_container_width=True,
        hide_index=True,
        height=360,
    )
    st.download_button(
        "기수표 CSV 다운로드",
        data=comm.to_csv(index=False).encode("utf-8-sig"),  # 엑셀에서 한글이 깨지지 않도록 BOM 포함
        file_name=f"commutation_{sex}_{i_pct:.2f}.csv",
        mime="text/csv",
    )

# --- 하단 고지 ---
st.divider()
st.caption(
    "학습·포트폴리오용 계산기이며 실제 상품의 보험료와 다를 수 있음. "
    "데이터: 통계청 2024년 완전생명표(Human Life-Table Database 수록본)."
)
