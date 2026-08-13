"""
Calls an LLM to classify an incident and suggest a first troubleshooting
step. Returns structured JSON so it can be programmatically merged with
the deterministic ITIL priority matrix in priority_matrix.py.

Uses Gemini via its OpenAI-compatible endpoint. Swap GEMINI_MODEL / base_url
in .env if you want to point this at a different OpenAI-compatible model
(e.g. Ollama's endpoint) instead.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.environ["GEMINI_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

CATEGORIES = ["Hardware", "Software", "Network", "Access/Account", "Email", "Other"]

SYSTEM_PROMPT = f"""You are an IT service desk triage assistant. Given a ticket's
short description and description, classify it and respond with ONLY valid JSON,
no markdown fences, no preamble. Schema:

{{
  "category": one of {CATEGORIES},
  "impact": 1, 2, or 3 (1=High: many users/critical system, 2=Medium, 3=Low: single user, minor),
  "urgency": 1, 2, or 3 (1=High: needs fixing now, 2=Medium, 3=Low: can wait),
  "confidence": float 0.0-1.0 (how confident you are in this classification),
  "suggested_first_step": one concrete, specific troubleshooting action a Tier 1
      technician should try first (one sentence, actionable - not generic advice)
}}
"""


def classify_ticket(short_description: str, description: str) -> dict:
    user_prompt = f"Short description: {short_description}\nDescription: {description or 'N/A'}"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)

    # Basic guardrails - never trust raw model output blindly
    result["impact"] = int(result["impact"]) if result.get("impact") in (1, 2, 3) else 2
    result["urgency"] = int(result["urgency"]) if result.get("urgency") in (1, 2, 3) else 2
    result["confidence"] = float(result.get("confidence", 0.5))
    if result.get("category") not in CATEGORIES:
        result["category"] = "Other"

    return result
