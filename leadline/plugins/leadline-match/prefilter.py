"""Hard-rule funnel in front of leadline-match: `build_input(subject, candidates, request)`.

A wrong drop is permanent (the agent never sees that candidate), so a rule drops only when BOTH sides state the fact
and the facts clearly clash. A missing field, an empty list or a word we can't place keeps the candidate.

Rules (startup side S, investor side I; the direction says which is the subject):
- stage_mismatch: S.stage and all I.stages are known stages, and S.stage is 2+ steps from each (seed funds often
  back pre-seed and Series A too).
- out_of_region: S.country and every I.regions entry are known names (country or alias, group, "global") and none
  covers S.country. Groups are drawn wide (Europe takes in Israel and Turkey). HQ country alone never drops.
- size_mismatch: same currency spelling only; I.check_size.min > S.raising.amount, or I.check_size.max is below
  MIN_CHECK_SHARE of it. Amounts <= 0, non-numbers and a range with min > max count as unknown.
- sector_mismatch: both sides list sectors and no pair fits: same word family (fintech ~ finance ~ payments), one
  inside the other ("climate" in "Climate Tech"), or the same first 5 letters; and neither says generalist.
A rule that fails on odd data keeps the candidate.

Not rules but clean-up, listed in `cut`: repeated ids, the subject itself, a candidate of the wrong kind, and, last,
candidates past MAX_CANDIDATES or the size cap (after slimming long text and fact lists) so the input stays under
MAX_INPUT_CHARS. A subject too big to fit even alone raises ValueError.

Returns {"input": leadline-match input or None when nothing is left, "rejected": [{candidate_id, reason, detail}]
(the output's `rejected` shape, ready to merge), "cut": [{candidate_id, reason}]}. The arguments are not changed.
No model calls; stdlib only, so it ships with the agent.
"""
import copy
import json

MAX_INPUT_CHARS = 25_000
MAX_CANDIDATES = 200  # the leadline-match input schema's limit
MIN_CHECK_SHARE = 0.05  # a check under 5% of the round is no lead

STAGES = {"pre-seed": 0, "seed": 1, "series-a": 2, "series-b": 3, "series-c": 4, "series-d": 5, "growth": 5,
          "series-e": 6, "late": 6}
STAGE_WORDS = {"preseed": "pre-seed", "pre seed": "pre-seed", "series a": "series-a", "series b": "series-b",
               "series c": "series-c", "series d": "series-d", "series e": "series-e", "late stage": "late",
               "growth stage": "growth"}
ALIASES = {"usa": "united states", "us": "united states", "u.s.": "united states", "united states of america":
           "united states", "america": "united states", "uk": "united kingdom", "great britain": "united kingdom",
           "britain": "united kingdom", "england": "united kingdom", "scotland": "united kingdom",
           "czechia": "czech republic", "uae": "united arab emirates", "holland": "netherlands",
           "the netherlands": "netherlands", "korea": "south korea"}
NORDICS = {"finland", "sweden", "norway", "denmark", "iceland"}
BALTICS = {"estonia", "latvia", "lithuania"}
EUROPE = NORDICS | BALTICS | {
    "united kingdom", "ireland", "germany", "france", "netherlands", "belgium", "luxembourg", "switzerland", "austria",
    "spain", "portugal", "italy", "poland", "czech republic", "slovakia", "hungary", "romania", "bulgaria", "greece",
    "croatia", "slovenia", "serbia", "ukraine", "cyprus", "malta", "monaco", "liechtenstein", "andorra", "albania",
    "bosnia and herzegovina", "north macedonia", "montenegro", "moldova", "georgia", "armenia", "turkey", "israel"}
MIDDLE_EAST = {"israel", "turkey", "united arab emirates", "saudi arabia", "qatar", "bahrain", "kuwait", "oman",
               "jordan", "lebanon", "egypt"}
AFRICA = {"south africa", "nigeria", "kenya", "egypt", "morocco", "ghana", "tunisia", "rwanda", "ethiopia",
          "senegal", "uganda", "tanzania", "ivory coast", "algeria"}
NORTH_AMERICA = {"united states", "canada", "mexico"}
LATAM = {"mexico", "brazil", "argentina", "chile", "colombia", "peru", "uruguay"}
ASIA = {"india", "china", "japan", "south korea", "singapore", "indonesia", "vietnam", "thailand", "malaysia",
        "philippines", "hong kong", "taiwan", "pakistan", "bangladesh"}
OCEANIA = {"australia", "new zealand"}
REGION_GROUPS = {"nordics": NORDICS, "nordic": NORDICS, "scandinavia": NORDICS, "baltics": BALTICS,
                 "europe": EUROPE, "eu": EUROPE, "emea": EUROPE | MIDDLE_EAST | AFRICA,
                 "dach": {"germany", "austria", "switzerland"}, "benelux": {"belgium", "netherlands", "luxembourg"},
                 "cee": EUROPE - NORDICS - {"united kingdom", "ireland", "france", "spain", "portugal", "italy"},
                 "middle east": MIDDLE_EAST, "mena": MIDDLE_EAST | AFRICA, "africa": AFRICA,
                 "north america": NORTH_AMERICA, "americas": NORTH_AMERICA | LATAM, "latam": LATAM,
                 "latin america": LATAM, "asia": ASIA, "apac": ASIA | OCEANIA, "oceania": OCEANIA}
COUNTRIES = EUROPE | MIDDLE_EAST | AFRICA | NORTH_AMERICA | LATAM | ASIA | OCEANIA
GLOBAL = {"global", "worldwide", "international", "any", "anywhere"}
GENERALIST = {"generalist", "sector agnostic", "agnostic", "all", "any", "all sectors"}
SECTOR_FAMILIES = (
    {"fintech", "finance", "financial", "financial services", "banking", "payments", "insurtech", "insurance",
     "lending", "wealthtech", "crypto", "blockchain", "remittances", "regtech"},
    {"health", "healthtech", "healthcare", "medtech", "medical", "digital health", "biotech", "life sciences",
     "pharma", "therapeutics", "diagnostics"},
    {"climate", "climatetech", "cleantech", "energy", "renewables", "sustainability", "greentech", "fusion",
     "fusion energy", "mobility", "circular economy", "carbon", "ocean cleanup"},
    {"ai", "artificial intelligence", "machine learning", "ml", "llms", "llm", "genai", "deep tech", "deeptech",
     "data", "ai chips", "semiconductors", "computing"},
    {"software", "saas", "enterprise", "enterprise software", "b2b", "developer tools", "devtools", "e commerce",
     "ecommerce"},
)


def _word(value) -> str:
    return " ".join(str(value).replace("_", " ").replace("-", " ").casefold().split())


def _num(value):
    """A positive finite number, or None (unknown): numeric strings count, 0 and below don't."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 and n != float("inf") else None


def _stage(value):
    w = _word(value)
    w = STAGE_WORDS.get(w, w.replace(" ", "-"))
    return w if w in STAGES else None


def _stage_clash(s, i):
    mine = _stage(s.get("stage")) if s.get("stage") else None
    theirs = [_stage(x) for x in i.get("stages") or []]
    if mine is None or not theirs or None in theirs:
        return None
    if min(abs(STAGES[mine] - STAGES[t]) for t in theirs) < 2:
        return None
    return f"stage {s.get('stage')} is 2+ steps from {i.get('stages')}"


def _place(value) -> str:
    w = _word(value)
    return ALIASES.get(w, w)


def _region_clash(s, i):
    country = _place(s["country"]) if s.get("country") else None
    regions = [_place(r) for r in i.get("regions") or []]
    if country not in COUNTRIES or not regions:
        return None
    for r in regions:
        if r in GLOBAL or r == country or country in REGION_GROUPS.get(r, ()):
            return None
        if r not in REGION_GROUPS and r not in COUNTRIES:
            return None  # a name we can't place
    return f"{s['country']} is outside {i.get('regions')}"


def _size_clash(s, i):
    raising, check = s.get("raising") or {}, i.get("check_size") or {}
    amount, low, high = _num(raising.get("amount")), _num(check.get("min")), _num(check.get("max"))
    cur_a, cur_c = raising.get("currency"), check.get("currency")
    if amount is None or not cur_a or not cur_c or _word(cur_a) != _word(cur_c):
        return None
    if low is not None and high is not None and low > high:
        return None
    if low is not None and low > amount:
        return f"smallest check {low:,.0f} {cur_c} is above the round of {amount:,.0f} {cur_a}"
    if high is not None and high < amount * MIN_CHECK_SHARE:
        return f"largest check {high:,.0f} {cur_c} is under {MIN_CHECK_SHARE:.0%} of the round of {amount:,.0f}"
    return None


def _sector_terms(values) -> set:
    """Each sector, and each part of "A / B" or "A, B", as plain words."""
    terms = set()
    for v in values or []:
        for part in str(v).replace("&", "/").replace(",", "/").split("/"):
            w = _word(part)
            if w:
                terms.add(w)
    return terms


def _sectors_fit(a, b) -> bool:
    if a in b or b in a or a[:5] == b[:5] and min(len(a), len(b)) >= 5:
        return True
    return any((a in fam or any(a == f or a.startswith(f + " ") for f in fam)) and
               (b in fam or any(b == f or b.startswith(f + " ") for f in fam)) for fam in SECTOR_FAMILIES)


def _sector_clash(s, i):
    mine, theirs = _sector_terms(s.get("sectors")), _sector_terms(i.get("sectors"))
    if not mine or not theirs or GENERALIST & (mine | theirs):
        return None
    if any(_sectors_fit(a, b) for a in mine for b in theirs):
        return None
    return f"no shared sector: {s.get('sectors')} vs {i.get('sectors')}"


RULES = (("stage_mismatch", _stage_clash), ("out_of_region", _region_clash), ("size_mismatch", _size_clash),
         ("sector_mismatch", _sector_clash))


def _slim(profile, desc, facts, quote):
    p = dict(profile)
    if isinstance(p.get("description"), str):
        p["description"] = p["description"][:desc]
    if isinstance(p.get("facts"), list):
        p["facts"] = [{**f, "quote": f["quote"][:quote]} if isinstance(f.get("quote"), str) else f
                      for f in p["facts"][:facts]]
    return p


def _first_clash(s, i):
    for reason, rule in RULES:
        try:
            detail = rule(s, i)
        except Exception:  # odd data: keep the candidate, never drop on a rule that could not decide
            continue
        if detail:
            return reason, detail
    return None


def build_input(subject: dict, candidates: list, request: dict) -> dict:
    subject, candidates, request = copy.deepcopy(subject), copy.deepcopy(candidates), copy.deepcopy(request)
    to_investors = request["direction"] == "startup_to_investors"
    want_kind = "investor" if to_investors else "startup"
    rejected, cut, kept, seen = [], [], [], set()

    for c in candidates:
        cid = c.get("id")
        if cid == subject.get("id"):
            cut.append({"candidate_id": cid, "reason": "subject"})
            continue
        if cid in seen:
            cut.append({"candidate_id": cid, "reason": "duplicate"})
            continue
        seen.add(cid)
        if c.get("kind") != want_kind:
            cut.append({"candidate_id": cid, "reason": "wrong_kind"})
            continue
        clash = _first_clash(subject, c) if to_investors else _first_clash(c, subject)
        if clash:
            rejected.append({"candidate_id": cid, "reason": clash[0], "detail": clash[1]})
        else:
            kept.append(c)

    for c in kept[MAX_CANDIDATES:]:
        cut.append({"candidate_id": c["id"], "reason": "size_cap"})
    kept = kept[:MAX_CANDIDATES]

    alone = {"subject": _slim(subject, 80, 1, 0), "candidates": [], "request": request}
    if len(json.dumps(alone)) >= MAX_INPUT_CHARS:
        raise ValueError(f"subject profile {subject.get('id')!r} is too large to fit in {MAX_INPUT_CHARS} characters")
    value = None
    for desc, facts, quote in ((600, 8, 300), (200, 3, 120), (80, 1, 0)):
        value = {"subject": _slim(subject, desc, facts, quote), "candidates": [_slim(c, desc, facts, quote)
                                                                            for c in kept], "request": request}
        if len(json.dumps(value)) < MAX_INPUT_CHARS:
            break
    cut_tail = []
    while value["candidates"] and len(json.dumps(value)) >= MAX_INPUT_CHARS:
        cut_tail.append({"candidate_id": value["candidates"].pop()["id"], "reason": "size_cap"})
    cut += reversed(cut_tail)
    return {"input": value if value["candidates"] else None, "rejected": rejected, "cut": cut}
