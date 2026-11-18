"""단기납종신보험 보험료·준비금·환급률 계산기 (Streamlit 화면)."""

import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from actuarial.commutation import build_commutation
from actuarial.lifetable import apply_mortality_multiplier, get_qx, load_lifetable
from actuarial.product import (
    Expenses,
    gross_premium,
    monthly_premium,
    net_premium,
    projection,
    reserve_step,
    scenario_results,
)

st.set_page_config(page_title="단기납종신 계리 계산기", page_icon="📊", layout="wide")


@st.cache_data
def cached_lifetable() -> pd.DataFrame:
    return load_lifetable()


def latex_num(expr: str) -> None:
    """천 단위 쉼표 뒤에 공백이 생기지 않도록 {,}로 바꿔 수식을 표시한다."""
    st.latex(re.sub(r"(?<=\d),(?=\d{3})", "{,}", expr))


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

tab1, tab2, tab3, tab4 = st.tabs(["준비금·환급금", "민감도", "계산식·기수표", "학습 모드"])

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

# --- 탭 4: 학습 모드 ---
with tab4:
    st.info("공부용 화면입니다. 각 그래프 옆에 공식과 실제로 대입한 숫자를 함께 보여 줍니다. (사이드바 조건 기준)")
    lt = cached_lifetable()
    qx_by_sex = {"M": get_qx(lt, "M"), "F": get_qx(lt, "F")}
    sex_name = {"M": "남자", "F": "여자"}

    # 1. 생명표 → 생존곡선
    st.subheader("① 생명표 → 생존곡선")
    left, right = st.columns([3, 2])
    with left:
        ages_all = np.arange(len(qx))
        fig_lt = make_subplots(rows=1, cols=2, subplot_titles=("사망확률 qx (로그 축)", "생존자 수 lx"))
        for s_code, color in (("M", "#1f77b4"), ("F", "#e45756")):
            ct_s = build_commutation(qx_by_sex[s_code], i)
            fig_lt.add_trace(
                go.Scatter(x=ages_all, y=qx_by_sex[s_code], name=sex_name[s_code], line=dict(color=color)),
                row=1, col=1,
            )
            fig_lt.add_trace(
                go.Scatter(x=ages_all, y=ct_s.lx[ages_all], name=sex_name[s_code], line=dict(color=color), showlegend=False),
                row=1, col=2,
            )
        fig_lt.update_yaxes(type="log", row=1, col=1)
        fig_lt.update_yaxes(tickformat=",", row=1, col=2)
        fig_lt.update_xaxes(title_text="연령 (세)")
        fig_lt.add_vline(x=x, line_dash="dot", line_color="gray")
        fig_lt.update_layout(height=400, legend=dict(orientation="h", y=-0.25), margin=dict(t=40))
        st.plotly_chart(fig_lt, use_container_width=True)
    with right:
        st.markdown(f"**{sex_label} {x}세 기준 대입**")
        latex_num(r"l_{x+1} = l_x\,(1 - q_x)")
        latex_num(
            rf"l_{{{x + 1}}} = {ct.lx[x]:,.1f} \times (1 - {qx[x]:.5f}) = {ct.lx[x + 1]:,.1f}"
        )
        latex_num(r"d_x = l_x \cdot q_x")
        latex_num(rf"d_{{{x}}} = {ct.lx[x]:,.1f} \times {qx[x]:.5f} = {ct.dx[x]:,.1f}")
        st.caption("l₀ = 100,000명에서 출발해 매년 qx 비율만큼 사망한다고 보고 생존자 수를 이어서 계산합니다.")

    # 2. 수지상등 원칙
    st.subheader("② 수지상등 원칙: 수입 현가 = 지출 현가")
    with_exp = st.toggle("사업비 포함 (영업보험료 기준)", value=False, key="learn_with_exp")
    a_m = float(ct.a_due(x, m))
    a_whole = float(ct.a_due(x))
    A_x = float(ct.A(x))
    left, right = st.columns([3, 2])
    with left:
        fig_eq = go.Figure()
        if not with_exp:
            fig_eq.add_trace(go.Bar(x=["보험료 수입 현가"], y=[P * a_m], name="순보험료 현가 P·ä"))
            fig_eq.add_trace(go.Bar(x=["보험금 지출 현가"], y=[S * A_x], name="보험금 현가 S·A"))
        else:
            parts_in = [("순보험료 현가 P·ä", P * a_m), ("사업비 현가 (G−P)·ä", (G - P) * a_m)]
            parts_out = [
                ("보험금 현가 S·A", S * A_x),
                ("신계약비 α·S", exp.alpha * S),
                ("납입 중 유지비 β·S·ä(x:m)", exp.beta * S * a_m),
                ("납입 후 유지비 β'·S·(ä(x)−ä(x:m))", exp.beta_after * S * (a_whole - a_m)),
                ("수금비 γ·G·ä(x:m)", exp.gamma * G * a_m),
            ]
            for name, val in parts_in:
                fig_eq.add_trace(go.Bar(x=["영업보험료 수입 현가"], y=[val], name=name))
            for name, val in parts_out:
                fig_eq.add_trace(go.Bar(x=["보험금·사업비 지출 현가"], y=[val], name=name))
            fig_eq.update_layout(barmode="stack")
        fig_eq.update_layout(yaxis_tickformat=",", yaxis_title="현재가치 (원)", height=420, margin=dict(t=30))
        st.plotly_chart(fig_eq, use_container_width=True)
    with right:
        if not with_exp:
            latex_num(r"P \cdot \ddot{a}_{x:\overline{m}|} = S \cdot A_x")
            latex_num(rf"{P:,.0f} \times {a_m:.4f} = {P * a_m:,.0f}")
            latex_num(rf"{S:,.0f} \times {A_x:.6f} = {S * A_x:,.0f}")
            st.caption("가입 시점에서 앞으로 받을 순보험료의 현재가치와 앞으로 줄 보험금의 현재가치가 같도록 P를 정합니다.")
        else:
            latex_num(
                r"G(1-\gamma)\ddot{a}_{x:\overline{m}|} = S A_x + \alpha S + \beta S \ddot{a}_{x:\overline{m}|}"
                r" + \beta' S (\ddot{a}_x - \ddot{a}_{x:\overline{m}|})"
            )
            latex_num(rf"G \cdot \ddot{{a}}_{{x:\overline{{m}}|}} = {G:,.0f} \times {a_m:.4f} = {G * a_m:,.0f}")
            total_out = sum(v for _, v in parts_out)
            latex_num(rf"\text{{지출 현가 합계}} = {total_out:,.0f}")
            st.caption("영업보험료 수입 현가는 순보험료 현가 위에 사업비 현가가 쌓인 것이고, 지출 쪽 합계와 같습니다.")

    # 3. 준비금이 쌓이는 원리
    st.subheader("③ 준비금이 쌓이는 원리 (재귀식)")
    k_max = min(30, ct.omega - x)
    k_sel = st.slider("경과연도 k", min_value=1, max_value=k_max, value=min(m, k_max), key="learn_k")
    step = reserve_step(ct, x, m, S, k_sel)
    left, right = st.columns([3, 2])
    with left:
        fig_wf = go.Figure(
            go.Waterfall(
                x=[f"{k_sel - 1}V (전년말 준비금)", "+ 보험료 P", "+ 이자", "− 사망보험금 기대지급 q·S", "+ 생존자 분배", f"{k_sel}V"],
                measure=["absolute", "relative", "relative", "relative", "relative", "total"],
                y=[step["prev_reserve"], step["premium"], step["interest"], -step["death_cost"], step["survivor_share"], 0],
                text=[
                    f"{v:,.0f}"
                    for v in (step["prev_reserve"], step["premium"], step["interest"], -step["death_cost"],
                              step["survivor_share"], step["reserve"])
                ],
                textposition="outside",
            )
        )
        fig_wf.update_layout(yaxis_tickformat=",", height=420, margin=dict(t=30), showlegend=False)
        st.plotly_chart(fig_wf, use_container_width=True)
    with right:
        latex_num(r"\left({}_{k-1}V + P\right)(1+i) = q_{x+k-1}\,S + p_{x+k-1}\,{}_kV")
        lhs = (step["prev_reserve"] + step["premium"]) * (1 + i)
        rhs = step["q"] * S + step["p"] * step["reserve"]
        latex_num(
            rf"({step['prev_reserve']:,.0f} + {step['premium']:,.0f}) \times {1 + i:.4f} = {lhs:,.0f}"
        )
        latex_num(rf"q \cdot S = {step['q']:.5f} \times {S:,.0f} = {step['q'] * S:,.0f}")
        latex_num(
            rf"p \cdot {{}}_{{{k_sel}}}V = {step['p']:.5f} \times {step['reserve']:,.0f} = {step['p'] * step['reserve']:,.0f}"
        )
        latex_num(rf"q \cdot S + p \cdot {{}}_{{{k_sel}}}V = {rhs:,.0f}")
        if k_sel > m:
            st.caption(f"k = {k_sel}년은 납입 완료({m}년) 이후라 보험료 P = 0입니다.")
        st.caption(
            f"{step['age']}세 초의 준비금에 보험료를 더하고 1년 이자를 붙인 뒤, 그해 사망자 몫의 보험금을 빼고 "
            "사망자 몫의 준비금을 생존자에게 나누면 다음 해 준비금이 됩니다."
        )

    # 4. 슬라이더로 공식 체험
    st.subheader("④ 슬라이더로 공식 체험")
    s1, s2 = st.columns(2)
    learn_i_pct = s1.slider("예정이율 (%)", 1.0, 5.0, float(i_pct), 0.25, key="learn_i")
    learn_x = s2.slider("가입연령 (세)", 15, 70, int(x), key="learn_x")
    ct_l = build_commutation(qx, learn_i_pct / 100)
    D, N, M_, Nm = ct_l.Dx[learn_x], ct_l.Nx[learn_x], ct_l.Mx[learn_x], ct_l.Nx[learn_x + m]
    A_l, a_l, am_l = M_ / D, N / D, (N - Nm) / D
    P_l = S * A_l / am_l
    f1, f2 = st.columns(2)
    with f1:
        latex_num(rf"A_{{{learn_x}}} = \frac{{M_{{{learn_x}}}}}{{D_{{{learn_x}}}}} = \frac{{{M_:,.2f}}}{{{D:,.2f}}} = {A_l:.6f}")
        latex_num(rf"\ddot{{a}}_{{{learn_x}}} = \frac{{N_{{{learn_x}}}}}{{D_{{{learn_x}}}}} = \frac{{{N:,.2f}}}{{{D:,.2f}}} = {a_l:.4f}")
    with f2:
        latex_num(
            rf"\ddot{{a}}_{{{learn_x}:\overline{{{m}}}|}} = \frac{{N_{{{learn_x}}} - N_{{{learn_x + m}}}}}{{D_{{{learn_x}}}}}"
            rf" = \frac{{{N:,.2f} - {Nm:,.2f}}}{{{D:,.2f}}} = {am_l:.4f}"
        )
        latex_num(rf"P = \frac{{S \cdot A_{{{learn_x}}}}}{{\ddot{{a}}_{{{learn_x}:\overline{{{m}}}|}}}} = \frac{{{S:,.0f} \times {A_l:.6f}}}{{{am_l:.4f}}} = {P_l:,.0f}")
    st.caption(
        f"{sex_label}, {m}년납, 가입금액 {won(S)} 기준. 예정이율을 올리면 A가 작아져 보험료가 내려가고, "
        "가입연령을 올리면 A가 커지고 ä가 작아져 보험료가 올라갑니다."
    )

    # 5. 가정 변경 시나리오
    st.subheader("⑤ 가정 변경 시나리오")
    st.caption("사이드바 조건이 '기준 가정'이고, 아래에서 바꾼 값이 '변경 가정'입니다.")

    defaults = {
        "sc_mult_M": 1.0,
        "sc_mult_F": 1.0,
        "sc_ages": (0, ct.omega),
        "sc_i": float(i_pct),
        "sc_alpha": float(alpha_pct),
        "sc_beta": float(beta_pct),
        "sc_beta_after": float(beta_after_pct),
        "sc_gamma": float(gamma_pct),
    }
    # 사이드바(기준 가정)가 바뀌면, 사용자가 직접 바꾸지 않은 시나리오 값은 새 기준을 따라가게 한다
    prev_base = st.session_state.get("sc_base", {})
    for key, val in defaults.items():
        if key not in st.session_state or st.session_state[key] == prev_base.get(key):
            st.session_state[key] = val
    st.session_state["sc_base"] = defaults

    def preset_male_double():
        st.session_state["sc_mult_M"] = 2.0
        st.session_state["sc_ages"] = (0, ct.omega)

    def preset_rate_down():
        st.session_state["sc_i"] = max(0.0, float(i_pct) - 1.0)

    def preset_no_expense():
        for key in ("sc_alpha", "sc_beta", "sc_beta_after", "sc_gamma"):
            st.session_state[key] = 0.0

    b1, b2, b3 = st.columns(3)
    b1.button("예시: 남성 사망률 전 연령 2배", on_click=preset_male_double, use_container_width=True)
    b2.button("예시: 예정이율 −1%p", on_click=preset_rate_down, use_container_width=True)
    b3.button("예시: 사업비 0", on_click=preset_no_expense, use_container_width=True)

    c_a, c_b, c_c = st.columns(3)
    with c_a:
        st.slider("남자 사망률 배수", 0.5, 3.0, step=0.1, key="sc_mult_M")
        st.slider("여자 사망률 배수", 0.5, 3.0, step=0.1, key="sc_mult_F")
        st.slider("배수 적용 연령 구간 (세)", 0, ct.omega, key="sc_ages")
    with c_b:
        st.number_input("예정이율 (%)", 0.0, 6.0, step=0.25, format="%.2f", key="sc_i")
        st.number_input("α 신계약비 (%)", 0.0, 20.0, step=0.1, format="%.2f", key="sc_alpha")
        st.number_input("β 납입 중 유지비 (%)", 0.0, 5.0, step=0.05, format="%.2f", key="sc_beta")
    with c_c:
        st.number_input("β' 납입 후 유지비 (%)", 0.0, 5.0, step=0.05, format="%.2f", key="sc_beta_after")
        st.number_input("γ 수금비 (%)", 0.0, 50.0, step=0.5, format="%.2f", key="sc_gamma")
        st.caption(f"계산에는 사이드바에서 고른 성별({sex_label})의 배수가 쓰입니다.")

    age_from, age_to = st.session_state["sc_ages"]
    qx_sc = apply_mortality_multiplier(qx, st.session_state[f"sc_mult_{sex}"], age_from, age_to)
    ct_sc = build_commutation(qx_sc, st.session_state["sc_i"] / 100)
    exp_sc = Expenses(
        alpha=st.session_state["sc_alpha"] / 100,
        beta=st.session_state["sc_beta"] / 100,
        beta_after=st.session_state["sc_beta_after"] / 100,
        gamma=st.session_state["sc_gamma"] / 100,
    )
    base_res = scenario_results(ct, x, m, S, exp)
    sc_res = scenario_results(ct_sc, x, m, S, exp_sc)

    rows = [
        ("순보험료 (연납, 원)", "net_premium", "{:,.0f}"),
        ("영업보험료 (연납, 원)", "gross_premium", "{:,.0f}"),
        ("10년 시점 책임준비금 (원)", "reserve_k", "{:,.0f}"),
        ("10년 시점 환급률 (%)", "refund_rate_k", "{:.1f}"),
    ]
    comp = pd.DataFrame(
        {
            "항목": [r[0] for r in rows],
            "기준": [r[2].format(base_res[r[1]]) for r in rows],
            "변경": [r[2].format(sc_res[r[1]]) for r in rows],
            "증감(%)": [f"{(sc_res[r[1]] / base_res[r[1]] - 1) * 100:+.2f}%" for r in rows],
        }
    )
    st.dataframe(comp, use_container_width=True, hide_index=True)

    pb, ps = base_res["projection"], sc_res["projection"]
    fig_sc = make_subplots(rows=1, cols=2, subplot_titles=("책임준비금", "환급률 (%)"))
    for proj_df, label, dash in ((pb, "기준", "solid"), (ps, "변경", "dash")):
        fig_sc.add_trace(
            go.Scatter(x=proj_df["k"], y=proj_df["reserve"], name=f"{label} 준비금", line=dict(dash=dash)),
            row=1, col=1,
        )
        fig_sc.add_trace(
            go.Scatter(x=proj_df["k"], y=proj_df["refund_rate_pct"], name=f"{label} 환급률", line=dict(dash=dash)),
            row=1, col=2,
        )
    fig_sc.update_xaxes(title_text="경과연도 (년)")
    fig_sc.update_yaxes(tickformat=",", row=1, col=1)
    fig_sc.update_layout(height=430, legend=dict(orientation="h", y=-0.3), margin=dict(t=40))
    st.plotly_chart(fig_sc, use_container_width=True)

# --- 하단 고지 ---
st.divider()
st.caption(
    "학습·포트폴리오용 계산기이며 실제 상품의 보험료와 다를 수 있음. "
    "데이터: 통계청 2024년 완전생명표(Human Life-Table Database 수록본)."
)
