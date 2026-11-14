"""Command line.

    python -m venus serve [--host 127.0.0.1] [--port 8000] [--plugins plugins] [--strategies strategies] [--runs runs]
    python -m venus handle request.json      # one request, response printed as JSON
    python -m venus export --plugins a,b --strategies strategies --out dist/agent [--plugins-dir plugins]
                           [--strategy ID ...] [--package leadline_agent] [--keep-base-model]
        # standalone run-only agent folder; exit 2 when a check refuses it (e.g. a draft strategy)
"""
import argparse
import json
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="venus")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "handle"):
        p = sub.add_parser(name)
        p.add_argument("--plugins", default="plugins")
        p.add_argument("--strategies", default="strategies")
        p.add_argument("--runs", default="runs")
        if name == "serve":
            p.add_argument("--host", default="127.0.0.1")
            p.add_argument("--port", type=int, default=8000)
        else:
            p.add_argument("request", help="path to a request JSON file, or - for stdin")
    p = sub.add_parser("export", help="write a standalone run-only agent folder")
    p.add_argument("--plugins", required=True, help="comma-separated plugin ids")
    p.add_argument("--strategies", required=True, help="strategies folder")
    p.add_argument("--out", required=True, help="target folder (empty, or an earlier export)")
    p.add_argument("--plugins-dir", default=None, help="default: plugins/ next to the strategies folder")
    p.add_argument("--strategy", action="append", default=None, help="strategy id (repeatable); "
                                                                      "default: <plugin>-default for each plugin")
    p.add_argument("--package", default="leadline_agent")
    p.add_argument("--keep-base-model", action="store_true", help="keep each strategy's trained base model "
                                                                  "instead of Verda Nemotron")
    p.add_argument("--fallback-provider", default=None, help="ship this provider's client for the fallback "
                                                             "(e.g. anthropic)")
    args = parser.parse_args(argv)

    if args.command == "export":
        from .export import VERDA_NEMOTRON, ExportError, export  # no serve / FastAPI import for exports
        try:
            manifest = export([p.strip() for p in args.plugins.split(",") if p.strip()], args.strategies, args.out,
                              plugins_dir=args.plugins_dir, strategy_ids=args.strategy, package=args.package,
                              base_model=None if args.keep_base_model else VERDA_NEMOTRON,
                              fallback_provider=args.fallback_provider)
        except ExportError as e:
            print(f"export refused: {e.code}: {e.message}", file=sys.stderr)
            return 2
        print(json.dumps(manifest, indent=2))
        return 0

    from .serve import Venus, create_app
    venus = Venus(plugins_dir=args.plugins, strategies_dir=args.strategies, runs_dir=args.runs)
    if args.command == "serve":
        import uvicorn
        uvicorn.run(create_app(venus), host=args.host, port=args.port)
        return 0
    raw = json.load(sys.stdin if args.request == "-" else open(args.request))
    resp = venus.handle(raw)
    print(json.dumps(resp, indent=2, ensure_ascii=False))
    return 0 if resp["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
