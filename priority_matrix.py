"""
Standard ITIL Impact x Urgency priority matrix.

This is deliberately NOT left up to the LLM to decide - the model
classifies impact and urgency from the ticket text, and this table
does the actual priority calculation. That split is the whole point:
it shows you understand the ITIL framework rather than just trusting
an LLM to output "P1" because it sounds urgent.

Impact:  1 = High (many users / critical system), 2 = Medium, 3 = Low
Urgency: 1 = High (needs fixing now), 2 = Medium, 3 = Low
"""

# (impact, urgency) -> ServiceNow priority value (1=Critical ... 4=Low)
PRIORITY_MATRIX = {
    (1, 1): 1,  # Critical
    (1, 2): 2,  # High
    (1, 3): 3,  # Moderate
    (2, 1): 2,  # High
    (2, 2): 3,  # Moderate
    (2, 3): 4,  # Low
    (3, 1): 3,  # Moderate
    (3, 2): 4,  # Low
    (3, 3): 4,  # Low
}

PRIORITY_LABELS = {1: "Critical (P1)", 2: "High (P2)", 3: "Moderate (P3)", 4: "Low (P4)"}


def calculate_priority(impact: int, urgency: int) -> tuple[int, str]:
    priority = PRIORITY_MATRIX[(impact, urgency)]
    return priority, PRIORITY_LABELS[priority]
