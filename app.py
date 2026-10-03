"""Regulatory Change Monitoring Tool - Streamlit dashboard."""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import db
import generate_synthetic

st.set_page_config(page_title="Regulatory Change Monitor", page_icon="📋", layout="wide")

IMPACT_ORDER = ["High", "Medium", "Low"]
IMPACT_COLOR = {"High": "#c0392b", "Medium": "#e69f00", "Low": "#7f8c8d"}


def explode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    out = df.assign(**{col: df[col].fillna("").str.split(", ")}).explode(col)
    return out[out[col] != ""]


def build_briefing(df: pd.DataFrame, days: int) -> str:
    since = pd.Timestamp(date.today() - timedelta(days=days))
    recent = df[df["published"] >= since]
    today = pd.Timestamp(date.today())
    lines = [
        "# Regulatory Compliance Briefing",
        f"_Period: {since.date()} to {today.date()}_",
        "",
    ]
    if recent["is_sample"].any():
        lines += ["> **Contains SAMPLE data. For demonstration only.**", ""]
    lines += [
        "## Summary",
        f"- {len(recent)} changes recorded",
        f"- {int((recent['impact'] == 'High').sum())} high impact, "
        f"{int(recent['action_req'].sum())} requiring action",
        "",
        "## Action required (by deadline)",
    ]
    act = recent[recent["action_req"] == 1].sort_values(
        ["deadline", "published"], na_position="last"
    )
    if act.empty:
        lines.append("- None this period.")
    for _, r in act.iterrows():
        dl = r["deadline"].date().isoformat() if pd.notna(r["deadline"]) else "no fixed date"
        lines.append(f"- **[{r['impact']}] {r['title']}** ({r['source']}) - deadline: {dl}")
        lines.append(f"  - Topics: {r['topics']} | Affects: {r['audiences']}")
    lines += ["", "## Other changes"]
    rest = recent[recent["action_req"] == 0].sort_values("published", ascending=False)
    if rest.empty:
        lines.append("- None.")
    for _, r in rest.iterrows():
        lines.append(f"- {r['published'].date()} {r['source']}: {r['title']} ({r['impact']})")
    lines += [
        "",
        "---",
        "_Automated keyword classification. Not legal advice; verify against the source._",
    ]
    return "\n".join(lines)


# ---------- header ----------
st.title("📋 Regulatory Change Monitor")
st.caption(
    "Tracks AUSTRAC, ATO, Fair Work and related changes affecting law firms. "
    "Classification is automated (keyword rules) and is not legal advice."
)

conn = db.connect()

# ---------- sidebar: data ----------
with st.sidebar:
    st.header("Data")
    if st.button("Load sample data"):
        n = generate_synthetic.load(conn)
        st.success(f"Loaded {n} sample items.")
    if st.button("Remove sample data"):
        st.info(f"Removed {db.clear_sample(conn)} sample items.")

df = db.load_df(conn)

if df.empty:
    st.info(
        "No data yet. Click **Load sample data** in the sidebar to generate the synthetic dataset."
    )
    st.stop()

if df["is_sample"].any():
    st.warning("Showing SAMPLE data (synthetic, for demonstration only).")

# ---------- sidebar: filters ----------
with st.sidebar:
    st.header("Filters")
    sources = st.multiselect("Agency", sorted(df["source"].unique()))
    all_topics = sorted(explode(df, "topics")["topics"].unique())
    topics = st.multiselect("Topic", all_topics)
    all_aud = sorted(explode(df, "audiences")["audiences"].unique())
    aud = st.multiselect("Affects", all_aud)
    impact = st.multiselect("Impact", IMPACT_ORDER)
    status = st.multiselect("Status", ["New", "Reviewed", "Actioned"])
    min_d, max_d = df["published"].min().date(), df["published"].max().date()
    date_range = st.date_input("Published between", (min_d, max_d), min_value=min_d, max_value=max_d)
    text = st.text_input("Search text")

view = df.copy()
if sources:
    view = view[view["source"].isin(sources)]
if impact:
    view = view[view["impact"].isin(impact)]
if status:
    view = view[view["status"].isin(status)]
if topics:
    view = view[view["topics"].apply(lambda s: any(t in s.split(", ") for t in topics))]
if aud:
    view = view[view["audiences"].apply(lambda s: any(a in s.split(", ") for a in aud))]
if isinstance(date_range, tuple) and len(date_range) == 2:
    view = view[(view["published"].dt.date >= date_range[0]) & (view["published"].dt.date <= date_range[1])]
if text:
    t = text.lower()
    view = view[view["title"].str.lower().str.contains(t) | view["summary"].fillna("").str.lower().str.contains(t)]

# ---------- KPIs ----------
today = pd.Timestamp(date.today())
open_actions = view[(view["action_req"] == 1) & (view["status"] != "Actioned")]
due_30 = open_actions[(open_actions["deadline"] >= today) & (open_actions["deadline"] <= today + pd.Timedelta(days=30))]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Changes (filtered)", len(view))
k2.metric("High impact", int((view["impact"] == "High").sum()))
k3.metric("Open actions", len(open_actions))
k4.metric("Due in 30 days", len(due_30))

tab_act, tab_time, tab_all, tab_brief = st.tabs(
    ["⚠️ Action required", "📈 Trends", "🗂 All changes", "📝 Weekly briefing"]
)

# ---------- action required ----------
with tab_act:
    if open_actions.empty:
        st.success("No open actions for the current filters.")
    else:
        acts = open_actions.sort_values(["deadline", "published"], na_position="last")
        for _, r in acts.iterrows():
            dl = r["deadline"]
            if pd.notna(dl):
                days_left = (dl - today).days
                dl_txt = f"Deadline {dl.date()} ({days_left} days)" if days_left >= 0 else f"Deadline {dl.date()} (passed)"
            else:
                dl_txt = "No fixed deadline"
            with st.container(border=True):
                c1, c2 = st.columns([5, 2])
                c1.markdown(f"**{r['title']}**")
                c1.caption(f"{r['source']} · {r['published'].date()} · {r['topics']} · Affects: {r['audiences']}")
                c1.write(r["summary"])
                if r["link"]:
                    c1.markdown(f"[Source]({r['link']})")
                c2.markdown(f"**Impact: {r['impact']}**")
                c2.write(dl_txt)
                new_status = c2.selectbox(
                    "Status", ["New", "Reviewed", "Actioned"],
                    index=["New", "Reviewed", "Actioned"].index(r["status"]),
                    key=f"st_{r['id']}",
                )
                if new_status != r["status"]:
                    db.set_status(conn, r["id"], new_status)
                    st.rerun()

# ---------- trends ----------
with tab_time:
    if view.empty:
        st.info("Nothing to chart.")
    else:
        m = view.assign(month=view["published"].dt.to_period("M").dt.to_timestamp())
        by_month = m.groupby(["month", "impact"]).size().reset_index(name="count")
        st.subheader("Changes per month by impact")
        st.altair_chart(
            alt.Chart(by_month).mark_bar().encode(
                x=alt.X("yearmonth(month):O", title="Month", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("count:Q", title="Changes"),
                color=alt.Color("impact:N", scale=alt.Scale(
                    domain=IMPACT_ORDER, range=[IMPACT_COLOR[i] for i in IMPACT_ORDER])),
                tooltip=["yearmonth(month):O", "impact:N", "count:Q"],
            ).properties(height=280),
            width="stretch",
        )
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("By topic")
            tp = explode(view, "topics")["topics"].value_counts().reset_index()
            tp.columns = ["topic", "count"]
            st.altair_chart(
                alt.Chart(tp).mark_bar().encode(
                    y=alt.Y("topic:N", sort="-x", title=None),
                    x=alt.X("count:Q", title="Changes"),
                    tooltip=["topic", "count"]).properties(height=280),
                width="stretch")
        with c2:
            st.subheader("By agency")
            ag = view["source"].value_counts().reset_index()
            ag.columns = ["agency", "count"]
            st.altair_chart(
                alt.Chart(ag).mark_bar().encode(
                    y=alt.Y("agency:N", sort="-x", title=None),
                    x=alt.X("count:Q", title="Changes"),
                    tooltip=["agency", "count"]).properties(height=280),
                width="stretch")

# ---------- all changes ----------
with tab_all:
    show = view[["published", "source", "title", "impact", "topics", "audiences",
                 "action_req", "deadline", "status", "link"]].copy()
    show["published"] = show["published"].dt.date
    show["deadline"] = show["deadline"].dt.date
    show["action_req"] = show["action_req"].map({1: "Yes", 0: ""})
    st.dataframe(
        show, hide_index=True, width="stretch",
        column_config={"link": st.column_config.LinkColumn("Source")},
    )
    st.download_button("Download CSV", show.to_csv(index=False), "regulatory_changes.csv", "text/csv")

# ---------- briefing ----------
with tab_brief:
    days = st.slider("Briefing period (days)", 7, 90, 30)
    md = build_briefing(df, days)
    st.markdown(md)
    st.download_button("Download briefing (.md)", md, "compliance_briefing.md", "text/markdown")
