"""
Streamlit dashboard for reviewing incidents that have already been through
the AI triage pipeline (triage.py). Read-only - makes no changes to ServiceNow.

Usage:
    streamlit run dashboard.py
"""

import re
from collections import Counter

import streamlit as st

from servicenow_client import get_all_incidents
from triage import already_triaged, CONFIDENCE_THRESHOLD

# Matches both note formats written by triage.py: the auto-applied path's
# "(confidence 0.95)" and the low-confidence path's "LOW CONFIDENCE (0.55)".
# Older tickets triaged before this format existed won't match at all, so
# confidence stays None for those rather than being guessed.
CONFIDENCE_RE = re.compile(r"confidence[:\s(]+([0-9.]+)", re.IGNORECASE)

# work_notes is a ServiceNow journal field, so its display value is the full
# history of every note ever added (newest first), each entry separated by
# a blank line. Stop at that boundary (or end of string) so retriaged
# tickets don't leak older entries' text into the current one.
FIRST_STEP_RE = re.compile(r"Suggested first step:\s*(.*?)(?:\n\s*\n|\Z)", re.DOTALL)


def extract_confidence(work_notes: str):
    match = CONFIDENCE_RE.search(work_notes or "")
    return float(match.group(1)) if match else None


def extract_first_step(work_notes: str):
    match = FIRST_STEP_RE.search(work_notes or "")
    return match.group(1).strip() if match else None


def is_flagged_for_review(work_notes: str) -> bool:
    return "LOW CONFIDENCE" in (work_notes or "")


@st.cache_data(ttl=60)
def load_triaged_incidents():
    incidents = get_all_incidents()
    triaged = [i for i in incidents if already_triaged(i)]
    return [
        {
            "number": i["number"],
            "short_description": i["short_description"],
            "category": i.get("category", ""),
            "priority": i.get("priority", ""),
            "confidence": extract_confidence(i.get("work_notes", "")),
            "flagged_for_review": is_flagged_for_review(i.get("work_notes", "")),
            "suggested_first_step": extract_first_step(i.get("work_notes", "")),
        }
        for i in triaged
    ]


st.set_page_config(page_title="AI Triage Dashboard", layout="wide")
st.title("🎫 AI Ticket Triage Dashboard")
st.markdown(
    "Shows every ServiceNow incident that's been processed by the AI triage "
    "pipeline ([triage.py](triage.py)): how the model classified and "
    "prioritized it, and its suggested first troubleshooting step. Read-only "
    "— nothing here writes back to ServiceNow."
)

rows = load_triaged_incidents()

if rows:
    flagged = sum(1 for r in rows if r["flagged_for_review"])
    auto_applied = len(rows) - flagged

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Triaged tickets", len(rows))
    metric_col2.metric("Auto-applied", f"{auto_applied / len(rows):.0%}")
    metric_col3.metric(f"Flagged for review (confidence < {CONFIDENCE_THRESHOLD})", f"{flagged / len(rows):.0%}")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        category_counts = dict(sorted(Counter(r["category"] or "Uncategorized" for r in rows).items()))
        st.subheader("Tickets by category")
        st.bar_chart(category_counts)

    with chart_col2:
        # Priority display values come back as "1 - Critical" etc, so a plain
        # string sort already puts them in P1..P4 order.
        priority_counts = dict(sorted(Counter(r["priority"] or "Unset" for r in rows).items()))
        st.subheader("Tickets by priority")
        st.bar_chart(priority_counts)

st.subheader("Triaged tickets")

table_columns = ["number", "short_description", "category", "priority", "confidence"]
table_rows = [{k: r[k] for k in table_columns} for r in rows]

event = st.dataframe(
    table_rows,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

st.subheader("AI-suggested first step")

selected = event.selection.rows if rows else []
if not selected:
    st.caption("Select a ticket in the table above to see its AI-suggested first troubleshooting step.")
else:
    ticket = rows[selected[0]]
    with st.container(border=True):
        header_col, badge_col = st.columns([3, 1])
        header_col.markdown(f"#### {ticket['number']} — {ticket['short_description']}")
        badge_col.markdown(f"**{ticket['priority']}**")

        meta_col1, meta_col2 = st.columns(2)
        meta_col1.markdown(f"**Category:** {ticket['category'] or '—'}")
        confidence_text = f"{ticket['confidence']:.0%}" if ticket["confidence"] is not None else "not recorded"
        status_text = "flagged for review" if ticket["flagged_for_review"] else "auto-applied"
        meta_col2.markdown(f"**Confidence:** {confidence_text} ({status_text})")

        st.markdown("**Suggested first step:**")
        if ticket["suggested_first_step"]:
            st.info(ticket["suggested_first_step"])
        else:
            st.caption("No suggested first step found in this ticket's work notes.")
