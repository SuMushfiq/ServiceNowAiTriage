"""
Tests for vt_client.check_url.

The stubbed tests cover the verdict branching and need no network access or
API key. The live tests hit VirusTotal for real - they're slow (an uncached
scan takes ~40s) and spend free-tier quota, so they only run on request:

    python test_vt_client.py           # stubbed tests only
    python test_vt_client.py --live    # stubbed + live tests
"""

import sys

import requests

import vt_client


class FakeResponse:
    """Stands in for a requests.Response carrying a canned JSON payload."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def check_url_with_stats(stats: dict) -> str:
    """Run check_url against a stubbed analysis reporting the given stats.

    Restores the real requests functions afterwards so the stubs can't leak
    into the live tests when both run in the same process.
    """
    real_post, real_get = requests.post, requests.get
    requests.post = lambda *args, **kwargs: FakeResponse({"data": {"id": "stub-analysis-id"}})
    requests.get = lambda *args, **kwargs: FakeResponse(
        {"data": {"attributes": {"status": "completed", "stats": stats}}}
    )
    try:
        return vt_client.check_url("http://example.com")
    finally:
        requests.post, requests.get = real_post, real_get


STUBBED_CASES = [
    ({"malicious": 5, "suspicious": 2, "harmless": 60}, "malicious"),
    ({"malicious": 0, "suspicious": 3, "harmless": 60}, "suspicious"),
    ({"malicious": 0, "suspicious": 0, "harmless": 70}, "clean"),
    ({"harmless": 70}, "clean"),  # VirusTotal can omit the keys entirely
    ({"malicious": 1, "suspicious": 9}, "malicious"),  # malicious outranks suspicious
]

# google.com is reliably clean; the EICAR file is flagged by engines by design
# (it's a harmless AV test string, not real malware).
LIVE_CASES = [
    ("https://www.google.com", "clean"),
    ("https://secure.eicar.org/eicar.com.txt", "malicious"),
]


def report(passed: bool, label: str) -> int:
    print(f"  {'PASS' if passed else 'FAIL'}  {label}")
    return 0 if passed else 1


def run_stubbed_tests() -> int:
    print("Stubbed verdict tests:")
    failures = 0
    for stats, expected in STUBBED_CASES:
        actual = check_url_with_stats(stats)
        failures += report(actual == expected, f"stats={stats} -> expected {expected}, got {actual}")
    return failures


def run_live_tests() -> int:
    print("\nLive VirusTotal tests:")
    failures = 0
    for url, expected in LIVE_CASES:
        actual = vt_client.check_url(url)
        failures += report(actual == expected, f"{url} -> expected {expected}, got {actual}")
    return failures


def main():
    failures = run_stubbed_tests()

    if "--live" in sys.argv:
        failures += run_live_tests()
    else:
        print("\nSkipping live tests (pass --live to run them).")

    print(f"\n{'All tests passed.' if failures == 0 else f'{failures} test(s) failed.'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
