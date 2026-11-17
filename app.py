from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import (
    LedgerState, Settings, StateError, applied_curve, breakpoint_price,
    capacity_for, money, replay_fixture, seasonal_demand, simulate_month,
    variable_per_unit,
)

st.set_page_config(page_title="Career Venture Lab | Stage 1", page_icon="📈", layout="wide")

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "sample_data" / "monthly_fixture.csv"


def init_state():
    if "lab" not in st.session_state:
        st.session_state.lab = LedgerState()
    if "notice" not in st.session_state:
        st.session_state.notice = ""


init_state()
lab: LedgerState = st.session_state.lab

st.title("Career Venture Lab")
st.caption("Stage 1 · Marketing pathway MKT-2 · Local-business marketing agency")
st.info(
    "Stage 1 is a deterministic, local-first simulator. No paid APIs or live AI responses are used. "
    "Stage 2–4 items are listed as unfinished below."
)

with st.sidebar:
    st.header("Team & pathway")
    st.text_input("Team ID", value=lab.settings.team_id, disabled=True)
    st.text_input("Pathway ID", value=lab.settings.pathway_id, disabled=True)
    st.text_input("Selected course", value=lab.settings.selected_course, disabled=True)
    st.selectbox("Math level", ["Foundation", "Applied", "Advanced"],
                 index=["Foundation", "Applied", "Advanced"].index(lab.settings.selected_level),
                 key="level_select")
    st.caption(f"Snapshot: {lab.snapshot_id[:8]}… · State version: {lab.state_version}")

    st.header("Business inputs")
    with st.form("business_inputs"):
        price = st.number_input("Package price (USD)", min_value=0.01, value=float(lab.settings.base_price), step=5.0)
        d0 = st.number_input("Requested units/month at base price (D0)", min_value=0, value=int(lab.settings.D0), step=1)
        staff = st.number_input("Productive staff hours/month", min_value=0.0, value=float(lab.settings.staff_hours), step=1.0)
        hours = st.number_input("Productive hours/unit", min_value=0.01, value=float(lab.settings.hours_per_unit), step=0.5)
        revisions = st.number_input("Additional revision hours/package", min_value=0.0, value=float(lab.settings.revision_hours_per_package), step=0.5)
        revision_cost = st.number_input("Extra revision hourly cost (USD)", min_value=0.0, value=float(lab.settings.extra_revision_hourly_cost), step=1.0)
        opening = st.number_input("Opening cash (USD)", min_value=0.0, value=float(lab.settings.opening_cash), step=100.0)
        media = st.number_input("Client media budget (pass-through, separate)", min_value=0.0, value=float(lab.settings.client_media_budget), step=25.0)
        submitted = st.form_submit_button("Update inputs")
    if submitted:
        s = lab.settings
        s.base_price, s.D0 = Decimal(str(price)), int(d0)
        s.staff_hours, s.hours_per_unit = Decimal(str(staff)), Decimal(str(hours))
        s.revision_hours_per_package = Decimal(str(revisions))
        s.extra_revision_hourly_cost = Decimal(str(revision_cost))
        s.opening_cash, s.client_media_budget = money(opening), money(media)
        try:
            s.validate()
            lab.state_version += 1
            st.success("Inputs updated.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

capacity = capacity_for(lab.settings)
vpu = variable_per_unit(lab.settings)
fixed = Decimal("900.00")

if st.session_state.notice:
    st.success(st.session_state.notice)
    st.session_state.notice = ""

tabs = st.tabs(["Overview & run", "Dated ledger", "Precalculus panel", "Save / restore", "Stage roadmap"])

with tabs[0]:
    st.subheader("Operating snapshot")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Monthly capacity", f"{capacity} packages")
    c2.metric("Variable cost / package", f"${vpu:,.2f}")
    c3.metric("Fixed monthly cost", "$900.00")
    c4.metric("Actual closing cash", f"${lab.current_cash():,.2f}")
    st.caption("Variable cost lines: designer labor $40 + licensed assets $10 + printing/delivery $20 + quality/revision allowance $10.")
    st.caption("Fixed monthly lines: software $250 + workspace $300 + admin $200 + hosting $150. Advertising is an additional campaign line.")

    st.markdown("#### Run a monthly simulation")
    with st.form("run_sim"):
        a, b, c = st.columns(3)
        run_date = a.date_input("Simulation date", value=date.today().replace(day=1))
        requested = b.number_input("Requested units", min_value=0, value=int(lab.settings.D0), step=1)
        ad_cost = c.number_input("Agency marketing expense (USD)", min_value=0.0, value=0.0, step=25.0)
        kind = st.radio("Record as", ["actual", "projected"], horizontal=True)
        submitted_run = st.form_submit_button("Calculate and add ledger entry")
    if submitted_run:
        rid = f"{kind}-{run_date.isoformat()}-{lab.state_version}"
        opening_cash = lab.current_cash() if kind == "actual" else lab.current_cash()
        result = simulate_month(
            lab.settings, simulation_date=run_date.strftime("%Y-%m"),
            requested=int(requested), marketing_expense=money(ad_cost),
            opening_cash=opening_cash, run_id=rid, transaction_type=kind,
        )
        try:
            lab.add_run(result)
            st.session_state.notice = f"{kind.title()} run saved: {result.sold} sold, profit ${result.operating_profit:,.2f}."
            st.rerun()
        except StateError as exc:
            st.error(str(exc))

    if lab.ledger:
        latest = lab.ledger[-1]
        st.markdown("#### Latest calculation")
        cols = st.columns(5)
        cols[0].metric("Sold", latest["sold"])
        cols[1].metric("Revenue", f"${float(latest['revenue']):,.2f}")
        cols[2].metric("Total expense", f"${float(latest['total_expense']):,.2f}")
        cols[3].metric("Operating profit", f"${float(latest['operating_profit']):,.2f}")
        cols[4].metric("Ending cash", f"${float(latest['ending_cash']):,.2f}")

    st.markdown("#### Startup financing & opening position")
    startup = pd.DataFrame([
        ("Owner contribution", 6500), ("Equipment assets", 1500),
        ("Pre-opening expense", -1000), ("Opening inventory", 0),
        ("Post-startup spendable cash", 4000), ("Retained earnings", -1000),
    ], columns=["Item", "USD"])
    st.dataframe(startup, hide_index=True, use_container_width=True)
    st.caption("The opening cash input is the post-startup spendable cash balance. Equipment and pre-opening expense are not monthly operating cash flows.")

with tabs[1]:
    st.subheader("One dated ledger · daily / monthly / yearly views")
    st.caption("Actual simulated transactions and projected scenarios remain separately labeled. Projections never change actual closing cash.")
    view = st.radio("View", ["Daily", "Monthly", "Yearly"], horizontal=True)
    if lab.ledger:
        df = pd.DataFrame(lab.ledger)
        df["date"] = pd.to_datetime(df["simulation_date"] + "-01")
        df["period"] = df["date"].dt.strftime("%Y-%m-%d" if view == "Daily" else "%Y-%m" if view == "Monthly" else "%Y")
        numeric = ["revenue", "total_expense", "operating_profit", "ending_cash"]
        for col in numeric:
            df[col] = pd.to_numeric(df[col])
        grouped = df.groupby(["period", "transaction_type"], as_index=False)[numeric].sum()
        st.dataframe(grouped, hide_index=True, use_container_width=True)
        st.markdown("#### Ledger entries")
        st.dataframe(df.drop(columns=["date", "period"]), hide_index=True, use_container_width=True)
        csv_bytes = df.drop(columns=["date", "period"]).to_csv(index=False).encode()
        st.download_button("Download ledger CSV", csv_bytes, "career_venture_ledger.csv", "text/csv")
    else:
        st.info("No transactions yet. Run a monthly calculation or replay the built-in fixture.")

    if st.button("Replay built-in fixture from $4,000 opening cash"):
        with FIXTURE_PATH.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # Fixture replay is an explicit fresh replay: reset the actual ledger.
        lab.ledger = []
        lab.used_run_ids = set()
        cash = money("4000")
        for result in replay_fixture(lab.settings, rows):
            result.opening_cash = cash
            cash = result.ending_cash
            lab.add_run(result)
        st.session_state.notice = "Fixture replay completed from a clean $4,000 opening balance."
        st.rerun()

with tabs[2]:
    st.subheader("Precalculus math skills · Advanced selected")
    st.write("Course: **Precalculus** · Pathway: **MKT-2** · Business context: local-business marketing agency")
    level = st.selectbox("Skill level", ["Foundation", "Applied", "Advanced"],
                         index=["Foundation", "Applied", "Advanced"].index(lab.settings.selected_level),
                         key="math_level")
    skill_map = {
        "Foundation": "Average cost and asymptotes",
        "Applied": "Piecewise demand, revenue, cost, and profit",
        "Advanced": "Seasonal trigonometric demand model",
    }
    st.markdown(f"**Named skill:** {skill_map[level]}")
    cap = capacity_for(lab.settings)
    v = float(vpu)
    F = 900.0
    if level == "Foundation":
        st.latex(r"A(s)=\frac{F}{s}+v,\quad 0<s\leq \mathrm{capacity}")
        st.write(f"Here, F = $900, v = ${v:,.2f}, and capacity = {cap} packages.")
        st.write("Domain: 0 < s ≤ capacity. Units: average USD cost per delivered package.")
        st.write("Assumptions: monthly fixed costs remain $900; variable cost per package is constant; s is continuous for this model.")
        st.write("Vertical asymptote: s = 0 (average cost is undefined at zero sales). Horizontal asymptote: y = v.")
        if cap > 0:
            xs = [i * cap / 100 for i in range(1, 101)]
            ys = [F / x + v for x in xs]
            st.line_chart(pd.DataFrame({"Average cost ($/unit)": ys}, index=xs))
            st.dataframe(pd.DataFrame({"Sales s (units)": xs[::10], "A(s) USD/unit": ys[::10]}), hide_index=True)
        st.info("Interpretation prompt: Why does average cost rise sharply as sales approach zero?")
    elif level == "Applied":
        st.latex(r"q(p)=\max(0,2D_0-(D_0/p_0)p)")
        st.latex(r"s(p)=\min(\mathrm{capacity},q(p)),\quad R(p)=p\,s(p)")
        st.latex(r"C(s(p))=F+v\,s(p),\quad P(p)=R(p)-C(s(p))")
        p0, d0 = float(lab.settings.base_price), int(lab.settings.D0)
        st.write(f"Substitution: q(p) = max(0, {2*d0} - {d0/p0:.6f}·p).")
        st.write(f"Domain: 0 ≤ p ≤ 2p₀ = ${2*p0:,.2f}. Units: p in USD/package; q and s in packages; R, C, P in USD.")
        st.write("Assumptions: linear unrounded demand, nonnegative demand, fixed capacity, constant unit variable cost.")
        bp = breakpoint_price(lab.settings)
        st.write(f"Capacity/demand breakpoint: p = p₀(2 − capacity/D₀) = **${bp:,.2f}**." if bp is not None else "D₀ = 0, so the breakpoint formula is undefined.")
        curve = pd.DataFrame(applied_curve(lab.settings))
        st.line_chart(curve.set_index("price")[["demand", "sales"]])
        st.line_chart(curve.set_index("price")[["revenue", "cost", "profit"]])
        st.dataframe(curve.iloc[::10].round(2), hide_index=True, use_container_width=True)
        st.warning("This is continuous analysis. Actual deliveries use whole units: requested units are rounded to the integer input, then sold = min(requested, capacity). The continuous curve is not the rounded operational result.")
        st.info("Interpretation prompts: Where does capacity stop binding? At what prices does modeled demand reach zero? How does the profit curve change around the breakpoint?")
    else:
        st.latex(r"D(t)=D_0\left(1+0.20\sin\left(\frac{2\pi(t-1)}{12}\right)\right)")
        st.write("Period: 12 months. Peak: t = 4 at 1.2·D₀. Minimum: t = 10 at 0.8·D₀.")
        st.write("Domain: integer month index t = 1,…,12. Units: D(t) in requested packages/month. Assumptions: fictional seasonal pattern, stable baseline D₀, fixed monthly capacity.")
        rows = []
        for t in range(1, 13):
            demand = seasonal_demand(lab.settings, t)
            rows.append({"Month index": t, "Original demand": float(demand),
                         "Realized sales (capacity clipped)": min(float(cap), float(demand))})
        seasonal_df = pd.DataFrame(rows)
        st.line_chart(seasonal_df.set_index("Month index"))
        st.dataframe(seasonal_df.round(2), hide_index=True)
        st.warning("Extrapolation limit: this is a fictional teaching model, not a forecast. It assumes a repeating 12-month pattern and should not be extrapolated to other markets or years without evidence.")
        st.info("Interpretation prompt: In which months is demand above capacity, and how much demand is unmet?")

with tabs[3]:
    st.subheader("Manual JSON snapshot export / import")
    st.caption("Snapshots are portable JSON files. Import is accepted only for the Marketing team, MKT-2 pathway, and an exact state_version match.")
    snapshot_text = lab.export_json()
    st.download_button("Export current snapshot JSON", snapshot_text, "career_venture_snapshot.json", "application/json")
    uploaded = st.file_uploader("Import a snapshot JSON file", type=["json"])
    expected_version = st.number_input("Current state_version required for import", min_value=0, value=int(lab.state_version), step=1)
    if st.button("Validate and restore uploaded snapshot", disabled=uploaded is None):
        try:
            restored = LedgerState.from_snapshot(uploaded.getvalue().decode("utf-8"), int(expected_version))
            st.session_state.lab = restored
            st.session_state.notice = "Snapshot restored and cash ledger reconciled."
            st.rerun()
        except Exception as exc:
            st.error(f"Import rejected: {exc}")
    st.code(snapshot_text, language="json")

with tabs[4]:
    st.subheader("Stage roadmap")
    st.markdown("""
    <badge>Stage 1 · Working</badge>
    - Inputs and deterministic capacity / unit-economics calculations
    - Monthly simulations, unique run IDs, dated actual/projected ledger
    - Daily / monthly / yearly ledger aggregation views
    - JSON snapshot export/import with team, pathway, version, and cash-reconciliation checks
    - Precalculus Foundation, Applied, and Advanced seasonal math panels
    - Synthetic CSV fixture and automated tests

    **Stage 2 · Not implemented:** customer research workflows, campaign planning, and evidence-backed market sizing.

    **Stage 3 · Not implemented:** richer operating decisions, staffing / inventory planning, and scenario comparison tools.

    **Stage 4 · Not implemented:** multi-team collaboration, hosted persistence, authentication, and production reporting.

    These later stages are intentionally not simulated or represented as completed.
    """)
    st.caption("Deployment is manual. This project does not deploy, publish, or connect to paid APIs automatically.")
