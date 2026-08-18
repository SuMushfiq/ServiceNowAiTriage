"""
Streamlit dashboard for reviewing incidents that have already been through
the AI triage pipeline (triage.py).

Reviewing is read-only; the Blocked URL Triage section is the one place that
writes back, and only when the technician explicitly posts a work note.

Usage:
    streamlit run dashboard.py
"""

import re
from collections import Counter

import streamlit as st

from servicenow_client import get_all_incidents, add_work_note
from triage import already_triaged, CONFIDENCE_THRESHOLD

# vt_client reads VIRUSTOTAL_API_KEY at import time, so a missing key would
# otherwise take down the whole dashboard rather than just the URL section.
try:
    from vt_client import check_url

    VIRUSTOTAL_READY = True
except KeyError:
    VIRUSTOTAL_READY = False

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


# Wording that suggests a user hit a blocked or unreachable site. ServiceNow
# text often carries a curly apostrophe, so normalise before matching.
BLOCKED_URL_KEYWORDS = ("blocked", "can't access", "cant access", "url")


def is_blocked_url_ticket(row: dict) -> bool:
    if (row.get("category") or "").strip().lower() != "network":
        return False
    haystack = f"{row.get('short_description', '')} {row.get('description', '')}"
    haystack = haystack.lower().replace("’", "'")
    return any(keyword in haystack for keyword in BLOCKED_URL_KEYWORDS)


def route_verdict(verdict: str) -> tuple[str, str]:
    """Map a VirusTotal verdict onto the team that should own the ticket."""
    if verdict in ("malicious", "suspicious"):
        return (
            "Security",
            f"VirusTotal flagged this URL as {verdict} — do not request an "
            "override, escalate for investigation.",
        )
    return (
        "Network",
        "URL appears safe — likely a policy-based block (e.g. a web filtering/"
        "proxy tool such as Zscaler, if used by the org). Check proxy logs and "
        "category classification for an override.",
    )


def build_url_triage_note(result: dict) -> str:
    """Format the triage answers into a [URL-TRIAGE] work note.

    The prefix deliberately differs from [AI-TRIAGED] so already_triaged()
    in triage.py doesn't mistake these for classifier output.
    """
    return (
        "[URL-TRIAGE] Blocked URL triage\n"
        f"URL: {result['url']}\n"
        f"Device / hostname: {result['device'] or 'not provided'}\n"
        f"Affected user(s) or team: {result['affected'] or 'not provided'}\n"
        f"Screenshot: {result['screenshot'] or 'not provided'}\n"
        f"VirusTotal verdict: {result['verdict']}\n"
        f"Suggested team: {result['team']}\n"
        f"Reason: {result['reason']}"
    )


@st.cache_data(ttl=60)
def load_triaged_incidents():
    incidents = get_all_incidents()
    triaged = [i for i in incidents if already_triaged(i)]
    return [
        {
            "sys_id": i["sys_id"],
            "number": i["number"],
            "short_description": i["short_description"],
            "description": i.get("description", ""),
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
    "prioritized it, and its suggested first troubleshooting step. Reviewing "
    "is read-only — only the Blocked URL Triage section below writes back, "
    "and only when you post a work note."
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

st.divider()
st.subheader("🔒 Blocked URL Triage")
st.markdown(
    "For tickets where a user reports a blocked or unreachable site: check the "
    "URL's reputation against VirusTotal, then route it to the team that should "
    "own it."
)

blocked_candidates = [r for r in rows if is_blocked_url_ticket(r)]

if not blocked_candidates:
    st.caption(
        "No triaged tickets currently match the blocked-URL pattern "
        "(category 'network' plus wording like blocked / can't access / url)."
    )
else:
    ticket_labels = {f"{r['number']} — {r['short_description']}": r for r in blocked_candidates}
    selected_label = st.selectbox("Ticket", list(ticket_labels))
    url_ticket = ticket_labels[selected_label]

    with st.form("blocked_url_triage"):
        submitted_url = st.text_input("URL being accessed *", placeholder="https://example.com/path")

        field_col1, field_col2 = st.columns(2)
        device = field_col1.text_input("Device / hostname")
        affected = field_col2.text_input("Affected user(s) or team")

        screenshot = st.file_uploader(
            "Screenshot of the error", type=["png", "jpg", "jpeg", "gif", "webp"]
        )
        st.caption(
            "The screenshot is accepted for the demo but not sent anywhere — "
            "ServiceNow attachment upload isn't wired up yet."
        )

        check_submitted = st.form_submit_button("Check URL reputation", type="primary")

    if check_submitted:
        # Drop any previous result so a failed check can't leave a stale
        # verdict on screen looking like it belongs to this submission.
        st.session_state.pop("url_triage", None)

        if not submitted_url.strip():
            st.error("URL is required.")
        elif not VIRUSTOTAL_READY:
            st.error("VIRUSTOTAL_API_KEY isn't set, so the reputation check can't run.")
        else:
            with st.spinner("Checking the URL against VirusTotal…"):
                try:
                    verdict = check_url(submitted_url.strip())
                except Exception as exc:
                    st.error(f"VirusTotal lookup failed: {exc}")
                else:
                    team, reason = route_verdict(verdict)
                    st.session_state.url_triage = {
                        "ticket_number": url_ticket["number"],
                        "sys_id": url_ticket["sys_id"],
                        "url": submitted_url.strip(),
                        "device": device.strip(),
                        "affected": affected.strip(),
                        "screenshot": screenshot.name if screenshot else "",
                        "verdict": verdict,
                        "team": team,
                        "reason": reason,
                    }

    result = st.session_state.get("url_triage")

    # Only show a stored result against the ticket it was actually run for,
    # so switching tickets can't post one ticket's verdict onto another.
    if result and result["ticket_number"] == url_ticket["number"]:
        verdict_banner = {
            "malicious": st.error,
            "suspicious": st.warning,
            "clean": st.success,
        }[result["verdict"]]
        verdict_banner(f"VirusTotal verdict: **{result['verdict'].upper()}**")

        with st.container(border=True):
            st.markdown(f"**Suggested team:** {result['team']}")
            st.markdown(f"**Reason:** {result['reason']}")

        if st.button("Post to ServiceNow"):
            try:
                add_work_note(result["sys_id"], build_url_triage_note(result))
            except Exception as exc:
                st.error(f"Failed to post the work note: {exc}")
            else:
                st.success(f"Work note posted to {result['ticket_number']}.")
                load_triaged_incidents.clear()
