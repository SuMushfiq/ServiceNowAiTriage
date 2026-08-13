# AI-Powered IT Helpdesk Triage Assistant

Pulls open incidents from a ServiceNow PDI, classifies them with an LLM,
calculates ITIL priority (Impact x Urgency) deterministically, and writes
the category/priority/suggested first step back into ServiceNow — flagging
low-confidence classifications for human review instead of auto-applying them.

## Quick start

1. **Get your PDI details.** In ServiceNow, note your instance URL and your
   admin username/password (Developer Program > your instance).

2. **Get an OpenAI API key** (or point `classifier.py` at a local Ollama
   server by changing the `OpenAI(...)` client's `base_url`).

3. **Set up the project:**
   ```bash
   cd servicenow-ai-triage
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   # edit .env with your ServiceNow + OpenAI details
   ```

4. **Seed test tickets and run the triage pipeline:**
   ```bash
   python triage.py --seed
   ```
   This creates 5 realistic sample incidents in your PDI, then triages
   every open incident it finds. Check the Incident table in ServiceNow
   afterwards — you'll see category, priority, and a work note with the
   AI's suggested first troubleshooting step on each ticket.

5. **Run again any time** with just `python triage.py` (no `--seed`) to
   triage newly logged tickets.

## How it works

- `servicenow_client.py` — thin REST wrapper over the Table API (GET/PATCH
  incidents, add work notes).
- `classifier.py` — sends the ticket text to the LLM, gets back structured
  JSON: category, impact, urgency, confidence, suggested first step.
- `priority_matrix.py` — a hand-coded ITIL Impact x Urgency matrix. The
  model classifies impact/urgency from the ticket text; this table (not
  the model) calculates the actual priority — kept deterministic on purpose.
- `triage.py` — orchestrates the above and applies a confidence threshold:
  anything under 0.6 gets flagged as a work note for human review rather
  than auto-applied to the ticket.

## What I'd improve next

- Add a proper `u_ai_triaged` custom field instead of the description-marker
  hack used to avoid re-triaging tickets.
- Track AI-suggested priority vs. the priority a human tech actually sets,
  to measure real-world classification accuracy over time.
- Add a small Streamlit dashboard showing volume by category and the
  AI/human agreement rate.

## Limitations

This is a portfolio/demo project, not production software — no retry
logic on API failures, no auth beyond basic ServiceNow credentials, and
the confidence score is self-reported by the model rather than calibrated
against ground truth.
