"""Markdown link and explicit identifier checks; fenced code is ignored."""
from pathlib import Path
import re
from urllib.parse import unquote, urlparse, parse_qs
from markdown_it import MarkdownIt
from .core import CitationError, Identifier


def check(path, client, language="en"):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    tokens = MarkdownIt().parse(text)
    issues, identifiers, links = [], set(), set()
    for block in tokens:
        if block.type != "inline":
            continue
        line = (block.map or [0])[0] + 1
        for token in block.children or []:
            if token.type in {"link_open", "image"}:
                links.add((token.attrGet("href") or token.attrGet("src"), line))
            if token.type == "text":
                for match in re.finditer(r"\b(?:CELEX:|ECLI:)[^\s<>`\[\](),;]+|\b[0369][0-9]{4}[A-Z]{1,2}[0-9]{4}\b", token.content):
                    identifiers.add((match.group().rstrip("."), line))
    for url, line in sorted(links):
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            if parsed.hostname in {"eur-lex.europa.eu", "data.europa.eu"}:
                value = parse_qs(parsed.query).get("uri", [None])[0]
                if value:
                    identifiers.add((value, line))
                elif parsed.path.startswith("/eli/"):
                    identifiers.add((url, line))
            if client.offline:
                issues.append({"line": line, "kind": "unchecked_link", "value": url, "message": "Offline mode cannot check remote links"})
                continue
            try:
                client.transport(url)
            except CitationError as exc:
                issues.append({"line": line, "kind": "broken_link" if exc.kind == "not_found" else exc.kind, "value": url, "message": str(exc)})
        elif not parsed.scheme and parsed.path:
            target = (path.parent / unquote(parsed.path)).resolve()
            if not target.exists():
                issues.append({"line": line, "kind": "broken_link", "value": url, "message": "Local target does not exist"})
    for value, line in sorted(identifiers):
        try:
            Identifier(value)
            client.resolve(value, language)
        except CitationError as exc:
            issues.append({"line": line, "kind": exc.kind, "value": value, "message": str(exc)})
    return issues
