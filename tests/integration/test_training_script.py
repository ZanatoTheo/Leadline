"""scripts/train_leadline.py end to end, no keys and no network: stub Cala and Context.dev (httpx.MockTransport,
counting requests), a scripted FakeModel. Checks the Cala rules (cache only without --refresh, --refresh capped),
that a second run makes 0 Cala and 0 web HTTP calls, the dry run, and the stop when no row names a lead.

    cd tests/integration && ../../venus/.venv/bin/python -m pytest -q test_training_script.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "venus"))

from venus import FakeModel, fake_text, fake_tool_call  # noqa: E402
from venus.training import RESEARCH_MARK  # noqa: E402

spec = importlib.util.spec_from_file_location("train_leadline", ROOT / "scripts" / "train_leadline.py")
train_leadline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train_leadline)

ROWS = [
    {"amount": "130", "company": "Proxima Fusion", "country": "Germany", "currency": "€",
     "investors": "redalpine (lead)", "round_date": "Jun 2025", "sector": "Fusion energy", "stage": "Series A"},
    {"amount": "46", "company": "VSORA", "country": "France", "currency": "$", "investors": "Otium (lead)",
     "round_date": "2025", "sector": "AI chips", "stage": "Series A"},
    {"amount": "28", "company": "Arlequin AI", "country": "France", "currency": "€",
     "investors": "redalpine, OTB Ventures", "round_date": "Sep 2026", "sector": "AI / Defence", "stage": "Series A"},
    {"amount": "15", "company": "Fractile", "country": "UK", "currency": "$", "investors": "Not disclosed",
     "round_date": "2025", "sector": "AI chips", "stage": "seed"},
]


class Stub:
    def __init__(self, reply):
        self.reply, self.count = reply, 0

    def __call__(self, request):
        self.count += 1
        return httpx.Response(200, json=self.reply(request))


def cala_reply(rows):
    return lambda request: {"results": rows, "entities": []}


def web_reply(request):
    body = json.loads(request.content or b"{}")
    return {"results": [{"url": "https://news.example/a", "title": f"About {body.get('query')}",
                         "description": "funding news"}]}


def model_script(messages, tools, tool_choice):
    """Search once, then answer: research gives one tendency; a case ranks the first two candidates."""
    if tools and tool_choice != "none" and not any(m["role"] == "tool" for m in messages):
        return fake_tool_call("web_search", {"query": "seed lead investors"})
    if RESEARCH_MARK in messages[0]["content"]:
        out = {"tendencies": [{"text": "Prefer investors who led rounds in the same sector.",
                               "sources": ["https://news.example/a"]}]}
        return fake_text(json.dumps({"output": out, "sources": ["https://news.example/a"]}), 10, 5)
    value = json.loads(next(m["content"] for m in messages if m["content"].startswith("Input:\n"))[len("Input:\n"):])
    if "user" in value:  # leadline-profile: the country of the first fact, sourced to it
        fact = (value.get("cala_facts") or [{}])[0]
        profile = {"id": value["user"]["id"], "kind": "startup", "name": value["user"]["name"],
                   "country": fact.get("country"), "facts": [{"id": "f1", "kind": "dataset", "ref": "cala:row"}],
                   "sources": {"country": {"facts": ["f1"]}}}
        out = {"profile": profile, "rating": {"total": 0.5, "parts": {"completeness": 0.5}, "sources": ["f1"]},
               "changes": []}
        return fake_text(json.dumps({"output": out, "sources": []}), 10, 5)
    matches = [{"candidate_id": c["id"], "candidate_type": "investor", "rank": n, "score": 0.5, "score_parts": {},
                "role": "unknown", "active": {"status": "unknown"}, "confidence": "low",
                "reasons": [{"text": "listed", "evidence": ["web-1"]}]}
               for n, c in enumerate(value["candidates"][:2], 1)]
    out = {"matches": matches, "rejected": [], "evidence": [{"id": "web-1", "kind": "web",
                                                            "url": "https://news.example/a"}], "warnings": []}
    return fake_text(json.dumps({"output": out, "sources": ["https://news.example/a"]}), 10, 5)


@pytest.fixture
def env(tmp_path):
    return {"CALA_API_KEY": "test", "CONTEXT_DEV_API_KEY": "test", "VENUS_CACHE_DIR": str(tmp_path / "cache"),
            "VENUS_TRAIN_PROVIDER": "anthropic"}


def run(tmp_path, env, *flags, rows=ROWS, models=None, script=None):
    cala, web = Stub(cala_reply(rows)), Stub(web_reply)
    models = [] if models is None else models

    def factory(base_model):
        models.append(FakeModel(script or model_script))
        return models[-1]
    argv = ["--cala-cache", str(tmp_path / "cala"), "--strategies", str(tmp_path / "strategies"),
            "--runs", str(tmp_path / "runs"), *flags]
    code = train_leadline.main(argv, cala_transport=httpx.MockTransport(cala),
                               web_transport=httpx.MockTransport(web), model_factory=factory, environ=env)
    return code, cala, web, models


def ledger(capsys):
    out = capsys.readouterr().out
    return json.loads(out[out.index("{"):]), out


def test_without_refresh_cala_gets_no_request(tmp_path, env, capsys):
    code, cala, web, models = run(tmp_path, env)
    assert code == 2 and cala.count == 0 and web.count == 0 and models == []
    assert "--refresh" in capsys.readouterr().out


def test_refresh_past_the_cap_stops_before_calling(tmp_path, env, capsys):
    code, cala, _, _ = run(tmp_path, env, "--refresh", "--max-cala-calls", "0")
    assert code == 2 and cala.count == 0
    assert "--max-cala-calls" in capsys.readouterr().out


def test_dry_run_estimates_and_calls_no_model(tmp_path, env, capsys):
    code, cala, web, models = run(tmp_path, env, "--refresh", "--dry-run", "--max-web-calls", "2")
    assert code == 0 and cala.count == 1 and web.count == 0 and models == []
    data, _ = ledger(capsys)
    assert data["dry_run"] is True and data["cases"] == 2
    assert data["estimate"]["model_calls_max"] > 0 and data["estimate"]["web_calls_max"] >= 2 * 2
    assert data["cala_calls"] == 1


def test_train_then_rerun_spends_no_cala_or_web(tmp_path, env, capsys):
    code, cala, web, models = run(tmp_path, env, "--refresh")
    first, _ = ledger(capsys)
    assert code == 0 and cala.count == 1 and first["cala_calls"] == 1
    assert first["status"] in ("ok", "partial") and first["cases"] == 2
    assert first["model_calls"] > 0 and first["web_http_calls"] == web.count > 0
    assert first["draft_strategy"] and (tmp_path / "strategies").is_dir()
    assert first["scores"] and all(0 <= s["total"] <= 1 for s in first["scores"])

    code, cala2, web2, _ = run(tmp_path, env)  # no --refresh: the Cala pull and the web pages come from disk
    second, _ = ledger(capsys)
    assert code == 0 and cala2.count == 0 and second["cala_calls"] == 0 and second["cala_cache_hits"] == 1
    assert web2.count == 0 and second["web_http_calls"] == 0


def test_no_named_lead_stops_with_a_reason(tmp_path, env, capsys):
    rows = [r for r in ROWS if "(lead)" not in r["investors"]]
    code, _, _, models = run(tmp_path, env, "--refresh", rows=rows)
    assert code == 3 and models == []
    assert "names no lead" in capsys.readouterr().out


def test_case_cap_and_model_budget_are_passed(tmp_path, env, capsys):
    code, _, _, models = run(tmp_path, env, "--refresh", "--cases", "1", "--max-turns", "2", "--max-web-calls", "1")
    data, _ = ledger(capsys)
    assert code == 0 and data["cases"] == 1
    assert data["limits"] == {"max_turns": 2, "max_web_calls": 1}


def test_a_broken_model_config_stops_before_any_model_call(tmp_path, env, capsys):
    env = {**env, "VENUS_TRAIN_PROVIDER": "anthropic."}  # the trailing-dot typo seen in a real .env
    code, _, web, models = run(tmp_path, env, "--refresh")
    assert code == 4 and models == [] and web.count == 0
    assert "VENUS_TRAIN_PROVIDER" in capsys.readouterr().out


def test_dry_run_with_a_broken_model_config_exits_4(tmp_path, env, capsys):
    env = {**env, "VENUS_TRAIN_PROVIDER": "anthropic."}
    code, _, _, models = run(tmp_path, env, "--refresh", "--dry-run")
    assert code == 4 and models == []


def test_leak_guard_blocks_web_queries_naming_a_training_subject():
    from venus.tools import Tool
    seen = []
    tools = [Tool("web_search", "s", {"type": "object"}, lambda a: seen.append(a) or {"results": []}, web=True),
             Tool("web_scrape", "s", {"type": "object"}, lambda a: seen.append(a) or {"markdown": ""}, web=True)]
    guarded = {t.name: t for t in train_leadline.guard_tools(tools, ["Proxima Fusion", "VSORA"])}
    assert "error" in guarded["web_search"].fn({"query": "proxima fusion series A lead"})
    assert "error" in guarded["web_search"].fn({"query": "Who backed VSORA?"})
    assert "error" in guarded["web_scrape"].fn({"url": "https://news.example/proxima-fusion-raises-130m"})
    assert seen == []
    assert guarded["web_search"].fn({"query": "European fusion energy investors"}) == {"results": []}
    assert len(seen) == 1 and all(t.web for t in guarded.values())


def test_training_never_offers_cala_tools_even_though_both_plugins_opt_in(tmp_path, env, capsys):
    """Cala holds the held-out leads: a training agent must never see a cala_* tool (phase 8)."""
    from venus import load_plugin
    for name in ("leadline-match", "leadline-profile"):
        assert load_plugin(ROOT / "leadline" / "plugins" / name).cala_enabled is True
    models = []
    code, _, _, _ = run(tmp_path, env, "--refresh", models=models)
    assert code == 0 and models
    offered = {t["function"]["name"] for m in models for call in m.calls for t in call["tools"] or []}
    assert offered and not any(n.startswith("cala_") for n in offered)


# --- phase 9: leadline-profile training, promotion -----------------------------------------------------------------

def strategy_file(tmp_path, plugin):
    return tmp_path / "strategies" / f"{plugin}-default.json"


def test_profile_plugin_trains_on_company_cases(tmp_path, env, capsys):
    code, _, _, _ = run(tmp_path, env, "--refresh", "--plugin", "leadline-profile")
    data, _ = ledger(capsys)
    assert code == 0 and data["plugin"] == "leadline-profile" and data["cases"] == 4
    assert data["scores"] and data["status"] in ("ok", "partial")


def test_promote_both_writes_validated_defaults_that_venus_can_run(tmp_path, env, capsys):
    from venus.strategy import StrategyStore
    code, _, _, _ = run(tmp_path, env, "--refresh", "--plugin", "both", "--promote", "--min-score", "0")
    data, _ = ledger(capsys)
    assert code == 0, data
    assert set(data["runs"]) == {"leadline-profile", "leadline-match"}
    store = StrategyStore(tmp_path / "strategies")
    for plugin in ("leadline-profile", "leadline-match"):
        assert data["promoted"][plugin]["promoted"] is True, data["promoted"][plugin]
        saved = json.loads(strategy_file(tmp_path, plugin).read_text())
        assert saved["status"] == "validated" and saved["id"] == f"{plugin}-default"
        notes = json.loads(saved["notes"])
        assert notes["trace_id"] == data["runs"][plugin]["trace_id"] and notes["gate"]["passed"] is True
        assert "mean_score" in notes and notes["cases"]
        assert store.get(f"{plugin}-default").is_validated
    assert data["runs"]["leadline-match"]["cases"] == 2


def test_promotion_refused_below_the_score_floor(tmp_path, env, capsys):
    code, _, _, _ = run(tmp_path, env, "--refresh", "--promote", "--min-score", "1")
    data, _ = ledger(capsys)
    assert code == 5 and data["promoted"]["leadline-match"]["promoted"] is False
    assert any("score" in r for r in data["promoted"]["leadline-match"]["reasons"])
    assert not strategy_file(tmp_path, "leadline-match").exists()


def leaky_script(messages, tools, tool_choice):
    if RESEARCH_MARK in messages[0]["content"] and any(m["role"] == "tool" for m in messages):
        out = {"tendencies": [{"text": "Back Proxima Fusion style rounds the way redalpine does.",
                               "sources": ["https://news.example/a"]}]}
        return fake_text(json.dumps({"output": out, "sources": ["https://news.example/a"]}), 10, 5)
    return model_script(messages, tools, tool_choice)


def test_promotion_refused_when_a_tendency_names_a_training_answer(tmp_path, env, capsys):
    code, _, _, _ = run(tmp_path, env, "--refresh", "--promote", "--min-score", "0", script=leaky_script)
    data, _ = ledger(capsys)
    assert code == 5
    reasons = data["promoted"]["leadline-match"]["reasons"]
    assert any("leak" in r and "Proxima Fusion" in r for r in reasons)
    assert not strategy_file(tmp_path, "leadline-match").exists()


def test_profile_db_builds_match_subject_profiles_into_the_database(tmp_path, env, capsys):
    import sqlite3
    db_path = tmp_path / "leadline.db"
    code, _, _, models = run(tmp_path, env, "--refresh", "--plugin", "both", "--profile-db", str(db_path))
    data, _ = ledger(capsys)
    assert code == 0, data
    con = sqlite3.connect(db_path)
    keys = {r[0].split("#")[0] for r in con.execute("SELECT key FROM agent_profiles")}
    assert keys == {"c_proxima-fusion@2025-05-31", "c_vsora@2024-12-31"}
    assert data["profiles_built"] == 2
    code, _, _, _ = run(tmp_path, env, "--plugin", "both", "--profile-db", str(db_path))
    again, _ = ledger(capsys)
    assert code == 0 and again["profiles_built"] == 0  # stored profiles are reused, not rebuilt


# --- phase 9 live-run finding: a tendency named "Mistral" (subject "Mistral AI") passed the leak check -------------

def test_leak_check_catches_a_distinctive_word_of_a_name_but_not_generic_words():
    leaks = train_leadline.leaking_names
    names = ["Mistral AI", "Green Voltis", "Lightspeed Venture Partners"]
    assert leaks("For example, a 2023-06-01 Mistral fact cannot be used", names) == ["Mistral AI"]
    assert leaks("Back lightspeed-style leads", names) == ["Lightspeed Venture Partners"]
    assert leaks("Prefer green energy funds and venture partners", names) == []
    assert leaks("Voltis raised in 2026", names) == ["Green Voltis"]


def leaky_word_script(messages, tools, tool_choice):
    if RESEARCH_MARK in messages[0]["content"] and any(m["role"] == "tool" for m in messages):
        out = {"tendencies": [{"text": "Ignore facts after as_of, e.g. a Proxima fact from the round month.",
                               "sources": ["https://news.example/a"]},
                              {"text": "Prefer investors who led rounds in the same sector.",
                               "sources": ["https://news.example/b"]}]}
        return fake_text(json.dumps({"output": out, "sources": ["https://news.example/a"]}), 10, 5)
    return model_script(messages, tools, tool_choice)


def test_a_single_name_word_blocks_promotion(tmp_path, env, capsys):
    code, _, _, _ = run(tmp_path, env, "--refresh", "--promote", "--min-score", "0", script=leaky_word_script)
    data, _ = ledger(capsys)
    assert code == 5 and any("Proxima Fusion" in r for r in data["promoted"]["leadline-match"]["reasons"])


def test_drop_leaking_removes_the_tendency_and_records_it(tmp_path, env, capsys):
    code, _, _, _ = run(tmp_path, env, "--refresh", "--promote", "--min-score", "0", "--drop-leaking",
                        script=leaky_word_script)
    data, _ = ledger(capsys)
    assert code == 0, data["promoted"]
    saved = json.loads(strategy_file(tmp_path, "leadline-match").read_text())
    texts = [t["text"] for t in saved["tendencies"]]
    assert not any("Proxima" in t for t in texts) and any("same sector" in t for t in texts)
    notes = json.loads(saved["notes"])
    assert notes["dropped_for_leak"] and "Proxima Fusion" in notes["dropped_for_leak"][0]["names"]


# --- phase 9 review: the leak guard is for the match run only (C); profiles keyed by profile strategy (G) ----------

def _input_value(messages):
    return json.loads(next(m["content"] for m in messages if m["content"].startswith("Input:\n"))[len("Input:\n"):])


def self_search_script(seen):
    """Each case searches its own company once; records whether the guard blocked it."""
    def script(messages, tools, tool_choice):
        if RESEARCH_MARK in messages[0]["content"]:
            return model_script(messages, tools, tool_choice)
        value = _input_value(messages)
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if tools and tool_choice != "none" and not tool_msgs:
            name = value["user"]["name"] if "user" in value else value["subject"]["name"]
            return fake_tool_call("web_search", {"query": f"{name} funding round"})
        if tool_msgs:
            seen.append(("profile" if "user" in value else "match", "blocked" in tool_msgs[-1]["content"]))
        return model_script(messages, [], tool_choice)
    return script


def test_the_profile_run_may_search_its_own_company_but_the_match_run_may_not(tmp_path, env, capsys):
    seen = []
    code, _, _, _ = run(tmp_path, env, "--refresh", "--plugin", "both", script=self_search_script(seen))
    data, _ = ledger(capsys)
    assert code == 0, data
    profile = [blocked for kind, blocked in seen if kind == "profile"]
    match = [blocked for kind, blocked in seen if kind == "match"]
    assert profile and not any(profile)
    assert match and all(match)


def test_stored_profiles_are_rebuilt_when_the_profile_strategy_changes(tmp_path, env, capsys):
    db = str(tmp_path / "leadline.db")
    code, _, _, _ = run(tmp_path, env, "--refresh", "--plugin", "both", "--profile-db", db)
    first, _ = ledger(capsys)
    assert code == 0 and first["profiles_built"] == 2
    # --promote: the profile strategy promoted in this run builds the match subjects, so nothing stored is reused
    code, _, _, _ = run(tmp_path, env, "--plugin", "both", "--profile-db", db, "--promote", "--min-score", "0")
    second, _ = ledger(capsys)
    assert code == 0, second
    assert second["profiles_built"] == 2
    code, _, _, _ = run(tmp_path, env, "--plugin", "both", "--profile-db", db, "--promote", "--min-score", "0")
    third, _ = ledger(capsys)
    assert code == 0 and third["profiles_built"] == 0  # same strategy: reused
