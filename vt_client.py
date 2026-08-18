"""
Thin wrapper around the VirusTotal v3 API for checking a URL's reputation.
Docs: https://docs.virustotal.com/reference/url

VirusTotal analysis is asynchronous: submitting a URL returns an analysis
id, and the actual verdict has to be polled for until it's ready.
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://www.virustotal.com/api/v3"
HEADERS = {"x-apikey": os.environ["VIRUSTOTAL_API_KEY"]}

POLL_INTERVAL_SECONDS = 2
POLL_ATTEMPTS = 30
# VirusTotal fills in stats incrementally and can leave an analysis flagged
# "in-progress" long after every engine that's going to report has reported,
# so treat stats that have stopped changing as final rather than waiting for
# a "completed" status that may never arrive.
STABLE_POLLS_REQUIRED = 3


def check_url(url: str) -> str:
    """Submit a URL to VirusTotal and return a verdict: "clean", "suspicious", or "malicious"."""
    submit_resp = requests.post(f"{BASE_URL}/urls", headers=HEADERS, data={"url": url}, timeout=30)
    submit_resp.raise_for_status()
    analysis_id = submit_resp.json()["data"]["id"]

    analysis_url = f"{BASE_URL}/analyses/{analysis_id}"
    attributes = {}
    previous_stats = None
    stable_polls = 0

    for _ in range(POLL_ATTEMPTS):
        analysis_resp = requests.get(analysis_url, headers=HEADERS, timeout=30)
        analysis_resp.raise_for_status()
        attributes = analysis_resp.json()["data"]["attributes"]

        if attributes.get("status") == "completed":
            break

        stats = attributes.get("stats") or {}
        if sum(stats.values()) > 0:
            stable_polls = stable_polls + 1 if stats == previous_stats else 0
            previous_stats = stats
            if stable_polls >= STABLE_POLLS_REQUIRED:
                break

        time.sleep(POLL_INTERVAL_SECONDS)

    stats = attributes.get("stats") or {}
    if sum(stats.values()) == 0:
        raise TimeoutError(f"VirusTotal returned no engine results for {url!r} in time")

    if stats.get("malicious", 0) > 0:
        return "malicious"
    if stats.get("suspicious", 0) > 0:
        return "suspicious"
    return "clean"
