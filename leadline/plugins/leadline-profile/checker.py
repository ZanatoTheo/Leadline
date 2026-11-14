"""leadline-profile checker: compare the built profile with the known (Cala) facts in `expected.profile`.

Parts (each in [0, 1]):
- field_match: mean agreement on the fields `expected.profile` knows (text: same, case aside; lists: overlap;
  lead_share: 1 - distance). A field the answer leaves null counts 0.
- sourced: share of the answer's non-null fields with a valid sources entry (fact ids that exist in profile.facts,
  or inferred: true).
total = 0.7 * field_match + 0.3 * sourced, or 0 when `update_problems` finds any (a broken update or a first build
that lists changes): such an answer must never be stored.

`update_problems(input, output)` is also used by leadline/profiles.py before anything is written to the store.
Loaded by file path (venus.plugin), so this module imports nothing from its own folder.
"""

FIELDS = ("name", "website", "description", "country", "stage", "stages", "sectors", "check_size", "lead_share",
          "last_lead_date", "regions", "raising")
SOURCED = FIELDS[1:]  # name comes from the user
TEXT = ("country", "stage", "website", "last_lead_date")
LISTS = ("stages", "sectors", "regions")
FIELD_WEIGHT, SOURCE_WEIGHT = 0.7, 0.3
MEAN_SLACK = 0.05  # rating total may differ this much from the mean of its parts (rounding)


def _norm(field, value):
    """Comparable form: case, spaces and list order don't count; empty (or all-null dict) is the same as missing."""
    if isinstance(value, dict) and all(v is None for v in value.values()):
        value = None
    if value in (None, "", [], {}):
        return None
    if field in LISTS and isinstance(value, list):
        return sorted({str(v).strip().casefold() for v in value})
    if field in TEXT and isinstance(value, str):
        return value.strip().casefold()
    return value


def _rating(rating):
    """(total, parts) of a rating, for comparison."""
    if not isinstance(rating, dict):
        return None
    return rating.get("total"), tuple(sorted((rating.get("parts") or {}).items()))


def _value(output_or_current, field):
    if field == "rating":
        return _rating(output_or_current.get("rating"))
    return _norm(field, (output_or_current.get("profile") or {}).get(field))


def _entry_fits(field, entry, old, new) -> bool:
    if field == "rating":  # the entry may give the totals or the whole ratings
        totals = (old[0] if old else None, new[0] if new else None)
        return (entry["old"], entry["new"]) == totals or (_rating(entry["old"]), _rating(entry["new"])) == (old, new)
    return (_norm(field, entry["old"]), _norm(field, entry["new"])) == (old, new)


def source_problems(profile) -> list:
    """Non-null fields without a valid source: fact ids that exist in profile.facts, or inferred: true."""
    fact_ids = {f.get("id") for f in profile.get("facts", [])}
    sources = profile.get("sources", {})
    problems = []
    for field in SOURCED:
        if _norm(field, profile.get(field)) is None:
            continue
        s = sources.get(field) or {}
        if s.get("inferred") is not True and not (s.get("facts") and all(i in fact_ids for i in s["facts"])):
            problems.append(f"{field}: no valid source (fact ids in profile.facts, or inferred: true)")
    return problems


def rating_problems(rating) -> list:
    parts = list((rating.get("parts") or {}).values())
    if parts and abs(rating["total"] - sum(parts) / len(parts)) > MEAN_SLACK:
        return [f"rating: total {rating['total']} is not the mean of its parts ({sum(parts) / len(parts):.2f})"]
    return []


def update_problems(input, output) -> list:
    """Why this output must not be stored, as plain sentences ([] when it may be)."""
    problems = []
    user, profile = input["user"], output["profile"]
    for key in ("id", "kind"):
        if profile.get(key) != user.get(key):
            problems.append(f"profile {key} {profile.get(key)!r} differs from the user's {user.get(key)!r}")
    problems += source_problems(profile) + rating_problems(output["rating"])
    changes = output.get("changes", [])
    current = input.get("current")
    if current is None:
        if changes:
            problems.append("a first build lists changes; it must list none")
        return problems

    listed = {}
    for c in changes:
        if c["field"] in listed:
            problems.append(f"changes lists {c['field']} twice")
        listed[c["field"]] = c
    for field in FIELDS + ("rating",):
        old, new = _value(current, field), _value(output, field)
        entry = listed.pop(field, None)
        if old != new:
            if entry is None:
                what = "a sourced field was dropped" if new is None else "changed"
                problems.append(f"{field}: {what} ({old!r} -> {new!r}) with no entry in changes")
            elif not _entry_fits(field, entry, old, new):
                problems.append(f"{field}: changes says {entry['old']!r} -> {entry['new']!r}, "
                                f"the profile went {old!r} -> {new!r}")
        elif entry is not None:
            problems.append(f"{field}: listed in changes but it did not change")
    for field in listed:
        problems.append(f"{field}: listed in changes but it is not a profile field")
    return problems


def _agree(field, got, want) -> float:
    if got is None:
        return 0.0
    if field in LISTS:
        got, want = set(got), set(want)
        return len(got & want) / len(got | want)
    if field == "lead_share":
        return max(0.0, 1.0 - abs(float(got) - float(want)))
    if field in TEXT:
        return 1.0 if str(got).strip().casefold() == str(want).strip().casefold() else 0.0
    return 1.0 if got == want else 0.0


def check(input, output, expected):
    reasons = []
    profile, want = output["profile"], expected["profile"]

    scores = []
    for field in FIELDS[1:]:
        if field == "description":  # prose: wording never matches exactly
            continue
        w = _norm(field, want.get(field))
        if w is None:
            continue
        a = _agree(field, _norm(field, profile.get(field)), w)
        scores.append(a)
        if a < 1:
            reasons.append(f"{field}: got {profile.get(field)!r}, known {want.get(field)!r}")
    field_match = sum(scores) / len(scores) if scores else 1.0

    filled = [f for f in SOURCED if _norm(f, profile.get(f)) is not None]
    unsourced = source_problems(profile)
    sourced = 1 - len(unsourced) / len(filled) if filled else 1.0

    problems = update_problems(input, output)  # includes the source problems
    reasons += problems
    total = 0.0 if problems else FIELD_WEIGHT * field_match + SOURCE_WEIGHT * sourced
    return {"total": max(0.0, min(1.0, total)), "parts": {"field_match": field_match, "sourced": sourced},
            "reasons": reasons}
