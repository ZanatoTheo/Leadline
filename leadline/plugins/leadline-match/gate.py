"""leadline-match free gate: `gate(settings, cases) -> {passed, metrics, reasons}`, called by venus.gate.

Reruns the prefilter on every case with the strategy's knobs (`rules`, `min_check_share`, `max_candidates`) and
measures filter recall: the share of true leads (expected.matches) still among the candidates the agent would see.
Passes when recall >= MIN_RECALL and the settings lose no lead the default prefilter keeps (see `gate`). Each lost lead
in a rejection names the case id, the lead and the rule. Also estimates input size per case. No model calls.

The knobs are applied to a private copy of prefilter.py (its RULES, MIN_CHECK_SHARE, MAX_CANDIDATES), so the shared
module is never changed. Loaded by file path (venus.plugin), so sibling files are loaded by path too.
"""
import importlib.util
import itertools
import json
from pathlib import Path

MIN_RECALL = 0.95
CHARS_PER_TOKEN = 4
_copies = itertools.count()


def _prefilter(settings: dict):
    path = Path(__file__).with_name("prefilter.py")
    spec = importlib.util.spec_from_file_location(f"leadline_match_gate_prefilter_{next(_copies)}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if "rules" in settings:
        module.RULES = tuple((name, rule) for name, rule in module.RULES if name in settings["rules"])
    if "min_check_share" in settings:
        module.MIN_CHECK_SHARE = settings["min_check_share"]
    if "max_candidates" in settings:
        module.MAX_CANDIDATES = settings["max_candidates"]
    return module


def _drops(prefilter, cases):
    """-> (true-lead count, kept count, [{case_id, candidate_id, reason}], input chars per case, candidates kept)."""
    dropped, kept_leads, total, chars, after = [], 0, 0, [], []
    for case in cases:
        value = case["input"]
        leads = list(dict.fromkeys(m["candidate_id"] for m in (case.get("expected") or {}).get("matches", [])))
        try:
            result = prefilter.build_input(value["subject"], value["candidates"], value["request"])
            why = {x["candidate_id"]: x["reason"] for x in result["rejected"] + result["cut"]}
        except ValueError:
            result, why = {"input": None}, dict.fromkeys(leads, "subject_too_large")
        except Exception as e:  # odd data: every lead of this case counts as lost, with the error
            result, why = {"input": None}, dict.fromkeys(leads, f"prefilter_error: {type(e).__name__}")
        kept = {c["id"] for c in (result["input"] or {}).get("candidates", [])}
        for lead in leads:
            total += 1
            if lead in kept:
                kept_leads += 1
            else:
                dropped.append({"case_id": case["id"], "candidate_id": lead, "reason": why.get(lead, "not_a_candidate")})
        chars.append(len(json.dumps(result["input"], ensure_ascii=False)) if result["input"] else 0)
        after.append(len(kept))
    return total, kept_leads, dropped, chars, after


def gate(settings, cases):
    """Rejects when (a) the cases hold no true lead, (b) recall < MIN_RECALL, or (c) the settings lose a lead that the
    default prefilter keeps: that loss is the settings' doing, so it is named (case id, lead, rule) even when overall
    recall stays above the threshold. A lead the default prefilter already loses counts only toward recall."""
    settings = settings or {}
    total, kept_leads, dropped, chars, after = _drops(_prefilter(settings), cases)
    baseline = {(d["case_id"], d["candidate_id"]) for d in _drops(_prefilter({}), cases)[2]} if settings else set()
    added = [d for d in dropped if settings and (d["case_id"], d["candidate_id"]) not in baseline]

    recall = kept_leads / total if total else 0.0
    reasons = []
    if total == 0:
        reasons.append("no true lead in the cases (expected.matches is empty everywhere): recall can't be measured")
    elif recall < MIN_RECALL:
        reasons.append(f"filter recall {recall:.2f} < {MIN_RECALL} with settings {json.dumps(settings, sort_keys=True)}")
        reasons += [f"case {d['case_id']}: true lead {d['candidate_id']} dropped ({d['reason']})" for d in dropped]
    if added and recall >= MIN_RECALL:
        reasons += [f"case {d['case_id']}: true lead {d['candidate_id']} dropped by these settings ({d['reason']}); "
                    "the default prefilter keeps it" for d in added]
    metrics = {"filter_recall": recall, "cases": len(cases), "true_leads": total, "dropped_leads": dropped,
               "dropped_by_settings": added,
               "candidates_after_mean": round(sum(after) / len(after), 2) if after else 0,
               "input_chars_per_case_max": max(chars, default=0),
               "input_tokens_per_case_est": round(sum(chars) / len(chars) / CHARS_PER_TOKEN) if chars else 0}
    return {"passed": not reasons, "metrics": metrics, "reasons": reasons}
