# AI-Powered IT Helpdesk Triage Assistant

Pulls open incidents from a ServiceNow PDI, classifies them with an LLM,
calculates ITIL priority (Impact x Urgency) deterministically, and writes
the category/priority/suggested first step back into ServiceNow — flagging
low-confidence classifications for human review instead of auto-applying them.

Also includes a Streamlit dashboard for reviewing what the pipeline did, and
a VirusTotal-backed workflow for triaging "this site is blocked" tickets.

## Quick start

1. **Get your PDI details.** In ServiceNow, note your instance URL and your
   admin username/password (Developer Program > your instance).

2. **Get a Gemini API key** from Google AI Studio. `classifier.py` talks to
   Gemini through its OpenAI-compatible endpoint, so pointing it at any other
   OpenAI-compatible server (e.g. Ollama) is just a `base_url` change.

3. **Get a VirusTotal API key** (free tier) from your profile at
   virustotal.com — only needed for the Blocked URL Triage section of the
   dashboard.

4. **Set up the project:**
   ```bash
   cd servicenow-ai-triage
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   # edit .env with your ServiceNow + Gemini + VirusTotal details
   ```

5. **Seed test tickets and run the triage pipeline:**
   ```bash
   python triage.py --seed
   ```
   This creates 5 realistic sample incidents in your PDI, then triages
   every open incident it finds. Check the Incident table in ServiceNow
   afterwards — you'll see category, priority, and a work note with the
   AI's suggested first troubleshooting step on each ticket.

6. **Run again any time** with just `python triage.py` (no `--seed`) to
   triage newly logged tickets, or `python triage.py --retriage` to
   reprocess every open incident regardless of whether it's been triaged
   before (useful after changing the classifier).

7. **Launch the dashboard:**
   ```bash
   streamlit run dashboard.py
   ```

## How it works

- `servicenow_client.py` — thin REST wrapper over the Table API (GET/PATCH
  incidents, add work notes).
- `classifier.py` — sends the ticket text to the LLM, gets back structured
  JSON: category, impact, urgency, confidence, suggested first step. The
  category list is pinned to ServiceNow's actual `incident.category` choice
  values, since the Table API silently discards anything else.
- `priority_matrix.py` — a hand-coded ITIL Impact x Urgency matrix. The
  model classifies impact/urgency from the ticket text; this table (not
  the model) calculates the actual priority — kept deterministic on purpose.
- `triage.py` — orchestrates the above and applies a confidence threshold:
  anything under 0.6 gets flagged as a work note for human review rather
  than auto-applied to the ticket.
- `vt_client.py` — checks a URL's reputation against the VirusTotal v3 API
  and reduces the engine vote counts to `clean` / `suspicious` / `malicious`.
- `dashboard.py` — Streamlit UI for reviewing triaged tickets (volume by
  category and priority, auto-applied vs flagged rate, per-ticket detail)
  plus the Blocked URL Triage workflow below.

## Blocked URL Triage

A common Tier 1 ticket is "I can't get to this site" — which is usually
either a genuine security block or an over-broad web filtering policy, and
the two want completely different owners.

The dashboard filters to network-category tickets whose text mentions a
blocked or inaccessible site, then collects the URL, the device/hostname,
the affected user(s) or team, and optionally a screenshot of the error. It
checks the URL through `vt_client.py` and suggests a routing team:

| Verdict | Suggested team | Reasoning |
| --- | --- | --- |
| `malicious` / `suspicious` | Security | VirusTotal flagged it — escalate for investigation rather than requesting an override. |
| `clean` | Network | Likely a policy-based block from a web filtering/proxy tool; check proxy logs and category classification for an override. |

Posting writes the answers, the verdict, and the suggested team/reason back
to the ticket as a work note prefixed `[URL-TRIAGE]` — deliberately distinct
from the `[AI-TRIAGED]` prefix so `already_triaged()` can't confuse the two.

The screenshot field is accepted but not uploaded; ServiceNow attachment
support isn't wired up.

## Testing

```bash
python test_vt_client.py           # stubbed tests only
python test_vt_client.py --live    # also hits VirusTotal for real
```

The stubbed tests cover the verdict branching — that `malicious` outranks
`suspicious`, and that absent stats keys default to `clean` rather than
raising — with no network access or API key required. The live tests check
a known-clean URL and the EICAR test file end-to-end, and are gated behind
`--live` because they're slow and spend free-tier quota.

The split exists because of a bug the live tests initially hid. `check_url`
originally polled until VirusTotal reported `status == "completed"`. The
first live run against the EICAR URL passed, which looked like confirmation
but was luck: that particular analysis happened to reach `completed`. Re-running
it later timed out instead. Polling the API directly showed why — VirusTotal
fills in `stats` incrementally and can leave an analysis `in-progress`
long after every engine that's going to report has reported, so the verdict
was sitting there fully populated and stable while the code waited for a
status that never arrived. Polling now settles for stats that have stopped
changing, and only raises if no engine ever reported.

## Tech stack

- **Python 3.12**
- **ServiceNow Table API** — incident read/write, basic auth against a PDI.
- **Google Gemini** via its OpenAI-compatible endpoint (`openai` client,
  `GEMINI_MODEL` pinned to a specific model rather than a `-latest` alias,
  since those move to newer models with tighter free-tier quotas).
- **VirusTotal API v3** — URL reputation.
- **Streamlit** — dashboard UI.
- `requests`, `python-dotenv` — HTTP and config.

## What I'd improve next

- Add a proper `u_ai_triaged` custom field instead of the work-note marker
  used to avoid re-triaging tickets. `--retriage` makes reprocessing easy,
  but the marker itself is still a string match against a journal field.
- Track AI-suggested priority vs. the priority a human tech actually sets,
  to measure real-world classification accuracy over time — the dashboard
  reports volume and confidence, but not agreement rate.
- Wire up ServiceNow attachment upload so the URL triage screenshot lands
  on the ticket instead of being discarded.
- Add retry/backoff around the API calls; free-tier LLM rate limits are the
  most common cause of a mid-run failure.

## Limitations

This is a portfolio/demo project, not production software — no retry
logic on API failures, no auth beyond basic ServiceNow credentials, and
the confidence score is self-reported by the model rather than calibrated
against ground truth.
