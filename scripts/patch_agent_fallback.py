"""Re-apply Leadline's fallback patch to an exported agent copy: FALLBACK_CODES in leadline_agent/core.py gains
"model_bad_reply" and "output_invalid", so a cut-off or unusable primary reply also falls back once (about half
the Verda rank runs failed that way). Venus itself keeps the shorter list; scripts/inject_agent.sh runs this
after every export. Idempotent; fails loudly when the line it patches is not there.

    python scripts/patch_agent_fallback.py [agent-root]   # default leadline/agent
"""
import sys
from pathlib import Path

UNPATCHED = '{"model_unavailable", "model_auth_failed", "model_config_missing", "request_timeout"}'


def main(root) -> int:
    core = Path(root) / "leadline_agent" / "core.py"
    text = core.read_text()
    assignment = text.split("FALLBACK_CODES", 1)[1][:400]
    if '"model_bad_reply"' in assignment and '"output_invalid"' in assignment:
        print(f"{core}: patch already there")
        return 0
    if UNPATCHED not in text:
        raise SystemExit(f"{core}: no FALLBACK_CODES line matching {UNPATCHED}; patch it by hand")
    core.write_text(text.replace(UNPATCHED, UNPATCHED[:-1] + ', "model_bad_reply", "output_invalid"}', 1))
    print(f"{core}: FALLBACK_CODES += model_bad_reply, output_invalid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "leadline/agent"))
