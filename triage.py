"""
Main entry point. Pulls open incidents from your ServiceNow PDI, runs
each through the AI classifier + ITIL priority matrix, and writes the
result back as a category/priority update plus a work note.

Tickets the model is unsure about (confidence < CONFIDENCE_THRESHOLD)
are flagged for human review instead of auto-applied - this is the
"know the limits of the AI" behaviour worth pointing to in interviews.

Usage:
    python triage.py            # triage all open, untriaged incidents
    python triage.py --seed     # create a handful of test incidents first
"""

import sys
import time

from servicenow_client import get_open_incidents, update_incident, add_work_note, create_test_incident
from classifier import classify_ticket
from priority_matrix import calculate_priority

CONFIDENCE_THRESHOLD = 0.6

TEST_TICKETS = [
    ("Outlook frozen and won't respond", "My Outlook has been frozen for 20 minutes, I can't send emails, whole team is affected on the shared inbox."),
    ("Can't connect to office wifi", "My laptop won't connect to the office wifi this morning, works fine on my phone."),
    ("New starter needs system access", "New employee starting Monday needs AD account, email, and access to the shared drive."),
    ("Mouse not working", "My wireless mouse isn't responding, already tried new batteries."),
    ("VPN keeps dropping", "VPN disconnects every 10-15 minutes while working from home, affecting my ability to access client files."),
]


def seed_test_data():
    print("Seeding test incidents into your PDI...")
    for short_desc, desc in TEST_TICKETS:
        result = create_test_incident(short_desc, desc)
        print(f"  Created {result['number']}: {short_desc}")


def already_triaged(incident: dict) -> bool:
    # Simple marker check since we're not adding a custom field for this starter version.
    return "[AI-TRIAGED]" in (incident.get("work_notes") or "")


def triage_incident(incident: dict):
    number = incident["number"]
    short_desc = incident["short_description"]

    print(f"\nTriaging {number}: {short_desc}")

    classification = classify_ticket(short_desc, incident.get("description", ""))
    priority, priority_label = calculate_priority(classification["impact"], classification["urgency"])

    print(f"  Category: {classification['category']}")
    print(f"  Impact/Urgency: {classification['impact']}/{classification['urgency']} -> {priority_label}")
    print(f"  Confidence: {classification['confidence']:.2f}")

    if classification["confidence"] < CONFIDENCE_THRESHOLD:
        note = (
            f"[AI-TRIAGED] LOW CONFIDENCE ({classification['confidence']:.2f}) - flagged for human review.\n"
            f"AI suggestion: category={classification['category']}, priority={priority_label}\n"
            f"Suggested first step: {classification['suggested_first_step']}"
        )
        add_work_note(incident["sys_id"], note)
        print("  -> Low confidence, flagged for human review (not auto-applied).")
        return

    update_incident(incident["sys_id"], {
        "category": classification["category"].lower(),
        "priority": priority,
        "urgency": classification["urgency"],
        "impact": classification["impact"],
    })
    note = f"[AI-TRIAGED] Suggested first step: {classification['suggested_first_step']}"
    add_work_note(incident["sys_id"], note)
    print(f"  -> Updated in ServiceNow as {priority_label}.")


def main():
    if "--seed" in sys.argv:
        seed_test_data()
        time.sleep(2)  # let ServiceNow index the new records

    incidents = get_open_incidents()
    untriaged = [i for i in incidents if not already_triaged(i)]

    print(f"Found {len(untriaged)} untriaged open incident(s).")

    for incident in untriaged:
        triage_incident(incident)

    print("\nDone.")


if __name__ == "__main__":
    main()
