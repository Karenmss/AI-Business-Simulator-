"""Deterministic Stage 1 business simulation engine for Career Venture Lab.

Money is represented internally as Decimal dollars quantized to cents.
The ledger stores dated, auditable simulation runs; no paid APIs are used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from math import floor, pi, sin
from typing import Any, Iterable
import json
import uuid

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Any) -> Decimal:
    """Convert a value to Decimal dollars, rounded to cents."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def dec(value: Any) -> Decimal:
    return Decimal(str(value))


def as_money_string(value: Decimal) -> str:
    return f"{money(value):.2f}"


class StateError(ValueError):
    """Raised when a snapshot or ledger operation violates state rules."""


@dataclass
class Settings:
    team_id: str = "Marketing"
    pathway_id: str = "MKT-2"
    selected_course: str = "Precalculus"
    selected_level: str = "Advanced"
    base_price: Decimal = Decimal("250.00")
    D0: int = 12
    staff_hours: Decimal = Decimal("80")
    hours_per_unit: Decimal = Decimal("8")
    opening_cash: Decimal = Decimal("4000.00")
    client_media_budget: Decimal = Decimal("0.00")
    revision_hours_per_package: Decimal = Decimal("0")
    extra_revision_hourly_cost: Decimal = Decimal("5.00")
    refund_amount: Decimal = Decimal("0.00")
    loan_principal: Decimal = Decimal("0.00")
    interest: Decimal = Decimal("0.00")
    additional_capex: Decimal = Decimal("0.00")
    new_owner_cash: Decimal = Decimal("0.00")
    loan_cash: Decimal = Decimal("0.00")
    random_seed: int = 17

    def validate(self) -> None:
        if self.team_id != "Marketing":
            raise ValueError("Stage 1 is configured for team_id='Marketing'.")
        if self.pathway_id != "MKT-2":
            raise ValueError("Stage 1 is configured for pathway_id='MKT-2'.")
        if self.base_price <= 0:
            raise ValueError("base_price must be greater than zero.")
        if self.D0 < 0 or int(self.D0) != self.D0:
            raise ValueError("D0 must be an integer greater than or equal to zero.")
        for name in ("staff_hours", "revision_hours_per_package",
                     "extra_revision_hourly_cost", "opening_cash",
                     "client_media_budget", "refund_amount", "loan_principal",
                     "interest", "additional_capex", "new_owner_cash", "loan_cash"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be greater than or equal to zero.")
        if self.hours_per_unit <= 0:
            raise ValueError("hours_per_unit must be greater than zero.")
        if self.selected_level not in {"Foundation", "Applied", "Advanced"}:
            raise ValueError("selected_level must be Foundation, Applied, or Advanced.")


@dataclass
class RunResult:
    run_id: str
    simulation_date: str
    requested: int
    capacity: int
    sold: int
    price: Decimal
    revenue: Decimal
    variable_per_unit: Decimal
    variable_expense: Decimal
    fixed_expense: Decimal
    marketing_expense: Decimal
    refund_amount: Decimal
    interest: Decimal
    principal: Decimal
    capex: Decimal
    new_owner_cash: Decimal
    loan_cash: Decimal
    total_expense: Decimal
    operating_profit: Decimal
    opening_cash: Decimal
    ending_cash: Decimal
    transaction_type: str = "actual"
    client_media_budget: Decimal = ZERO

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        for key, value in list(out.items()):
            if isinstance(value, Decimal):
                out[key] = as_money_string(value)
        return out


VARIABLE_LINES = {
    "designer_labor": Decimal("40.00"),
    "licensed_assets": Decimal("10.00"),
    "printing_delivery": Decimal("20.00"),
    "quality_revision_allowance": Decimal("10.00"),
}
FIXED_LINES = {
    "software": Decimal("250.00"),
    "workspace": Decimal("300.00"),
    "admin": Decimal("200.00"),
    "hosting": Decimal("150.00"),
}


def capacity_for(settings: Settings) -> int:
    productive_hours = settings.hours_per_unit + settings.revision_hours_per_package
    return max(0, floor(settings.staff_hours / productive_hours))


def variable_per_unit(settings: Settings) -> Decimal:
    base_variable = sum(VARIABLE_LINES.values(), ZERO)
    revision_cost = settings.revision_hours_per_package * settings.extra_revision_hourly_cost
    return money(base_variable + revision_cost)


def simulate_month(
    settings: Settings,
    *,
    simulation_date: str,
    requested: int | None = None,
    capacity_override: int | None = None,
    marketing_expense: Decimal | int | float = ZERO,
    opening_cash: Decimal | None = None,
    run_id: str | None = None,
    transaction_type: str = "actual",
) -> RunResult:
    settings.validate()
    date.fromisoformat(f"{simulation_date}-01" if len(simulation_date) == 7 else simulation_date)
    req = settings.D0 if requested is None else int(requested)
    if req < 0:
        raise ValueError("requested units cannot be negative.")
    cap = capacity_for(settings) if capacity_override is None else int(capacity_override)
    if cap < 0:
        raise ValueError("capacity_override cannot be negative.")
    sold = min(req, cap)
    price = money(settings.base_price)
    vpu = variable_per_unit(settings)
    revenue = money(price * sold)
    variable_exp = money(vpu * sold)
    fixed_exp = money(sum(FIXED_LINES.values(), ZERO))
    marketing = money(marketing_expense)
    if marketing < 0:
        raise ValueError("marketing expense cannot be negative.")
    refund = money(settings.refund_amount)
    interest = money(settings.interest)
    principal = money(settings.loan_principal)
    capex = money(settings.additional_capex)
    owner_cash = money(settings.new_owner_cash)
    loan_cash = money(settings.loan_cash)
    total_expense = money(variable_exp + fixed_exp + marketing + refund)
    profit = money(revenue - variable_exp - fixed_exp - marketing - refund)
    opening = money(settings.opening_cash if opening_cash is None else opening_cash)
    ending = money(
        opening + revenue - variable_exp - fixed_exp - marketing - refund
        - interest - principal - capex + owner_cash + loan_cash
    )
    return RunResult(
        run_id=run_id or str(uuid.uuid4()),
        simulation_date=simulation_date,
        requested=req,
        capacity=cap,
        sold=sold,
        price=price,
        revenue=revenue,
        variable_per_unit=vpu,
        variable_expense=variable_exp,
        fixed_expense=fixed_exp,
        marketing_expense=marketing,
        refund_amount=refund,
        interest=interest,
        principal=principal,
        capex=capex,
        new_owner_cash=owner_cash,
        loan_cash=loan_cash,
        total_expense=total_expense,
        operating_profit=profit,
        opening_cash=opening,
        ending_cash=ending,
        transaction_type=transaction_type,
        client_media_budget=money(settings.client_media_budget),
    )


def _json_settings(settings: Settings) -> dict[str, Any]:
    result = asdict(settings)
    for key, value in list(result.items()):
        if isinstance(value, Decimal):
            result[key] = as_money_string(value)
    return result


def _settings_from_json(raw: dict[str, Any]) -> Settings:
    decimal_fields = {
        "base_price", "staff_hours", "hours_per_unit", "opening_cash",
        "client_media_budget", "revision_hours_per_package",
        "extra_revision_hourly_cost", "refund_amount", "loan_principal",
        "interest", "additional_capex", "new_owner_cash", "loan_cash",
    }
    clean = dict(raw)
    for key in decimal_fields:
        if key in clean:
            clean[key] = dec(clean[key])
    return Settings(**clean)


@dataclass
class LedgerState:
    settings: Settings = field(default_factory=Settings)
    state_version: int = 1
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ledger: list[dict[str, Any]] = field(default_factory=list)
    used_run_ids: set[str] = field(default_factory=set)

    def add_run(self, result: RunResult) -> None:
        if result.run_id in self.used_run_ids:
            raise StateError(f"Duplicate run_id rejected: {result.run_id}")
        if result.transaction_type not in {"actual", "projected"}:
            raise ValueError("transaction_type must be 'actual' or 'projected'.")
        self.used_run_ids.add(result.run_id)
        self.ledger.append(result.to_dict())
        self.state_version += 1

    def current_cash(self) -> Decimal:
        actuals = [r for r in self.ledger if r["transaction_type"] == "actual"]
        if not actuals:
            return money(self.settings.opening_cash)
        actuals.sort(key=lambda r: (r["simulation_date"], r["run_id"]))
        return money(actuals[-1]["ending_cash"])

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "team_id": self.settings.team_id,
            "pathway_id": self.settings.pathway_id,
            "snapshot_id": self.snapshot_id,
            "state_version": self.state_version,
            "settings": _json_settings(self.settings),
            "ledger": self.ledger,
            "used_run_ids": sorted(self.used_run_ids),
        }

    def export_json(self) -> str:
        return json.dumps(self.to_snapshot(), indent=2, sort_keys=True)

    @classmethod
    def from_snapshot(cls, payload: str | dict[str, Any], current_state_version: int) -> "LedgerState":
        raw = json.loads(payload) if isinstance(payload, str) else payload
        if raw.get("schema_version") != 1:
            raise StateError("Unsupported snapshot schema_version.")
        if raw.get("team_id") != "Marketing":
            raise StateError("Snapshot team_id mismatch; expected Marketing.")
        if raw.get("pathway_id") != "MKT-2":
            raise StateError("Snapshot pathway_id mismatch; expected MKT-2.")
        incoming_version = int(raw.get("state_version", -1))
        if incoming_version != int(current_state_version):
            raise StateError(
                f"Stale snapshot rejected: snapshot state_version={incoming_version}, "
                f"current state_version={current_state_version}."
            )
        settings = _settings_from_json(raw["settings"])
        settings.validate()
        ledger = list(raw.get("ledger", []))
        run_ids = [row["run_id"] for row in ledger]
        if len(run_ids) != len(set(run_ids)):
            raise StateError("Snapshot contains duplicate run_ids.")
        if set(raw.get("used_run_ids", run_ids)) != set(run_ids):
            raise StateError("Snapshot run_id index does not reconcile with ledger.")
        state = cls(
            settings=settings,
            state_version=incoming_version,
            snapshot_id=str(raw["snapshot_id"]),
            ledger=ledger,
            used_run_ids=set(run_ids),
        )
        # Reconcile all actual cash balances chronologically.
        actuals = sorted(
            [r for r in ledger if r.get("transaction_type") == "actual"],
            key=lambda r: (r["simulation_date"], r["run_id"]),
        )
        prior_close = money(settings.opening_cash)
        for row in actuals:
            if money(row["opening_cash"]) != prior_close:
                raise StateError("Snapshot cash reconciliation failed: opening cash does not match prior close.")
            expected = money(
                money(row["opening_cash"]) + money(row["revenue"])
                - money(row["variable_expense"]) - money(row["fixed_expense"])
                - money(row["marketing_expense"]) - money(row.get("refund_amount", 0))
                - money(row.get("interest", 0)) - money(row.get("principal", 0))
                - money(row.get("capex", 0)) + money(row.get("new_owner_cash", 0))
                + money(row.get("loan_cash", 0))
            )
            if expected != money(row["ending_cash"]):
                raise StateError("Snapshot cash reconciliation failed: ending cash does not match ledger.")
            prior_close = expected
        return state


def replay_fixture(settings: Settings, rows: Iterable[dict[str, Any]]) -> list[RunResult]:
    """Replay monthly fixture rows from a clean opening-cash balance."""
    cash = money(settings.opening_cash)
    results = []
    for row in rows:
        result = simulate_month(
            settings,
            simulation_date=row["month"],
            requested=int(row["requested"]),
            capacity_override=int(row["capacity_override"]),
            marketing_expense=money(row["ad_cost"]),
            opening_cash=cash,
            run_id=f"fixture-{row['month']}",
        )
        cash = result.ending_cash
        results.append(result)
    return results


def seasonal_demand(settings: Settings, month_index: int) -> Decimal:
    """Fictional monthly seasonal demand; t=4 peak and t=10 minimum."""
    if not 1 <= int(month_index) <= 12:
        raise ValueError("month_index must be between 1 and 12.")
    value = dec(settings.D0) * (
        Decimal("1") + Decimal("0.20") * dec(sin(2 * pi * (int(month_index) - 1) / 12))
    )
    return value


def applied_curve(settings: Settings, points: int = 101) -> list[dict[str, float]]:
    """Continuous applied demand/revenue/cost/profit values across [0, 2*p0]."""
    p0 = float(settings.base_price)
    d0 = float(settings.D0)
    cap = capacity_for(settings)
    v = float(variable_per_unit(settings))
    fixed = float(sum(FIXED_LINES.values(), ZERO))
    rows = []
    for i in range(points):
        p = (2 * p0) * i / (points - 1)
        q = max(0.0, 2 * d0 - (d0 / p0) * p) if d0 else 0.0
        s = min(float(cap), q)
        revenue = p * s
        cost = fixed + v * s
        rows.append({"price": p, "demand": q, "sales": s, "revenue": revenue,
                     "cost": cost, "profit": revenue - cost})
    return rows


def breakpoint_price(settings: Settings) -> Decimal | None:
    if settings.D0 == 0:
        return None
    return money(settings.base_price * (Decimal("2") - dec(capacity_for(settings)) / dec(settings.D0)))

# --- Streamlit user interface ---

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

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
        if FIXTURE_PATH.exists():
            with FIXTURE_PATH.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        else:
            # Embedded synthetic fixture keeps the two-file deployment self-contained.
            rows = [
                {"month": "2027-01", "requested": "12", "capacity_override": "10", "ad_cost": "0"},
                {"month": "2027-02", "requested": "13", "capacity_override": "10", "ad_cost": "100"},
                {"month": "2027-03", "requested": "11", "capacity_override": "7", "ad_cost": "0"},
            ]
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
