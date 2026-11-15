"""leadline-match checker: score a ranking against the true leads in `expected.matches`.

Parts (each in [0, 1]):
- top_hit: the rank-1 match is a true lead.
- recall_at_k: share of true leads among the first `request.top_k` distinct matches (by rank, not list order).
- unknown_penalty: share of bad entries (an id not among the candidates, a repeat, the subject, or a match typed
  unlike the candidate's kind), the worse of matches and rejected. Invented candidates hurt the user, so they scale
  the whole score down.
total = (0.4 * top_hit + 0.6 * recall_at_k) * (1 - unknown_penalty).

Loaded by file path (venus.plugin), so this module imports nothing from its own folder.
"""

TOP_WEIGHT = 0.4
RECALL_WEIGHT = 0.6


TYPE_OF_KIND = {"investor": "investor", "startup": "company"}


def _bad_entries(rows, kinds, subject, seen, check_type):
    """Ids in `rows` that are the subject, not a candidate, repeated (across matches and rejected), or, for matches,
    typed unlike the candidate's kind. `seen` is shared so a repeat across lists counts."""
    bad = []
    for row in rows:
        cid = row["candidate_id"]
        if cid == subject:
            bad.append(f"{cid} (the subject)")
        elif cid not in kinds:
            bad.append(f"{cid} (not a candidate)")
        elif cid in seen:
            bad.append(f"{cid} (repeated)")
        elif check_type and row.get("candidate_type") != TYPE_OF_KIND.get(kinds[cid]):
            bad.append(f"{cid} (typed {row.get('candidate_type')}, is a {kinds[cid]})")
        seen.add(cid)
    return bad


def check(input, output, expected):
    truth = list(dict.fromkeys(m["candidate_id"] for m in expected.get("matches", [])))  # each true lead once
    top_k = input["request"]["top_k"]
    kinds = {c["id"]: c["kind"] for c in input["candidates"]}
    subject = input["subject"]["id"]
    reasons = []

    ranked = []
    for m in sorted(output.get("matches", []), key=lambda m: m["rank"]):  # stable: equal ranks keep list order
        if m["candidate_id"] not in ranked:
            ranked.append(m["candidate_id"])
    shown = ranked[:top_k]

    # the worse of the two shares, so padding `rejected` with real ids can't dilute an invented match
    matches, rejected, seen = output.get("matches", []), output.get("rejected", []), set()
    bad_m = _bad_entries(matches, kinds, subject, seen, check_type=True)
    bad_r = _bad_entries(rejected, kinds, subject, seen, check_type=False)
    unknown_penalty = max(len(bad_m) / len(matches) if matches else 0.0,
                          len(bad_r) / len(rejected) if rejected else 0.0)
    if bad_m or bad_r:
        reasons.append("unknown entries: " + ", ".join(bad_m + bad_r))

    if truth:
        top_hit = 1.0 if shown and shown[0] in truth else 0.0
        recall = sum(1 for t in truth if t in shown) / len(truth)
        missed = [t for t in truth if t not in shown]
        if missed:
            reasons.append(f"true lead(s) not in the top {top_k}: " + ", ".join(missed))
        if shown and not top_hit:
            reasons.append(f"rank 1 is {shown[0]}, not a true lead")
    else:  # no known lead: an empty ranking is right, any match is a guess
        top_hit = recall = 1.0 if not shown else 0.0

    total = (TOP_WEIGHT * top_hit + RECALL_WEIGHT * recall) * (1 - unknown_penalty)
    return {"total": max(0.0, min(1.0, total)),
            "parts": {"top_hit": top_hit, "recall_at_k": recall, "unknown_penalty": unknown_penalty},
            "reasons": reasons}
