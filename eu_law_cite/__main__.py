import argparse
import json
import sys
from .core import CitationError, Client, bibtex
from .markdown import check


def main():
    parser = argparse.ArgumentParser(description="Resolve public EU bibliographic identifiers")
    parser.add_argument("--cache")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--language", default="en")
    sub = parser.add_subparsers(dest="command", required=True)
    cite = sub.add_parser("cite")
    cite.add_argument("identifier")
    cite.add_argument("--format", choices=["csl-json", "bibtex"], default="csl-json")
    lint = sub.add_parser("check")
    lint.add_argument("paths", nargs="+")
    args = parser.parse_args()
    client = Client(cache=args.cache, offline=args.offline)
    try:
        if args.command == "cite":
            item = client.resolve(args.identifier, args.language)
            print(bibtex(item) if args.format == "bibtex" else json.dumps([item], ensure_ascii=False, indent=2))
            return 0
        issues = []
        for path in args.paths:
            issues.extend({"path": path, **issue} for issue in check(path, client, args.language))
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        if any(x["kind"] in {"unavailable", "unchecked_link", "unsupported"} for x in issues):
            return 2
        return int(bool(issues))
    except CitationError as exc:
        print(json.dumps({"kind": exc.kind, "message": str(exc)}), file=sys.stderr)
        return 1 if exc.kind in {"malformed", "not_found"} else 2
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
