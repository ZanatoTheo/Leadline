"""Toy checker: full marks when the label matches the expected label."""


def check(input, output, expected):
    match = 1.0 if output.get("label") == expected.get("label") else 0.0
    reasons = [] if match else [f"expected {expected.get('label')}, got {output.get('label')}"]
    return {"total": match, "parts": {"label_match": match}, "reasons": reasons}


def check_out_of_range(input, output, expected):
    return {"total": 1.5, "parts": {}, "reasons": []}
