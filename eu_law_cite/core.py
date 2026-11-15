import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
LANGUAGES = {"en": "ENG", "it": "ITA", "fr": "FRA", "de": "DEU", "es": "SPA",
             "pt": "POR", "nl": "NLD", "pl": "POL", "el": "ELL", "bg": "BUL",
             "cs": "CES", "da": "DAN", "et": "EST", "fi": "FIN", "ga": "GLE",
             "hr": "HRV", "hu": "HUN", "lt": "LIT", "lv": "LAV", "mt": "MLT",
             "ro": "RON", "sk": "SLK", "sl": "SLV", "sv": "SWE"}
CELEX = re.compile(r"[0-9CE][0-9]{4}[A-Z]{1,2}[0-9]{3,4}(?:\([0-9]{2}\))?(?:-[0-9]{8})?(?:_RES|_[0-9]+)?|[1256][0-9]{4}[A-Z]{1,2}/[A-Z0-9_]+")
ECLI = re.compile(r"ECLI:[A-Z]{2}:[A-Z0-9.]{1,7}:[0-9]{4}:[A-Z0-9.]{1,25}")
ELI = re.compile(r"https?://(?:data\.europa\.eu|eur-lex\.europa\.eu)/eli/[A-Za-z0-9_./-]+")


class CitationError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


class Identifier:
    def __init__(self, value):
        value = value.strip()
        if value.upper().startswith("CELEX:"):
            value = value[6:]
        if CELEX.fullmatch(value.upper()):
            self.kind, self.value = "celex", value.upper()
        elif ECLI.fullmatch(value.upper()):
            self.kind, self.value = "ecli", value.upper()
            if self.value.split(":")[1] != "EU":
                raise CitationError("unsupported", "Only EU court ECLI metadata is available")
        elif ELI.fullmatch(value):
            path = urlparse(value).path.rstrip("/")
            suffixes = "|".join(code.lower() for code in LANGUAGES.values())
            path = re.sub(r"/(?:" + suffixes + r")(?:/(?:html|pdf))?$", "", path)
            if not path.endswith("/oj"):
                raise CitationError("unsupported", "ELI must identify an EU Official Journal work ending /oj")
            if ".." in path or "//" in path:
                raise CitationError("malformed", "Invalid ELI path")
            act = r"/eli/(?:reg|dir|dec|reco|opin)(?:_del|_impl)?/[0-9]{4}/[0-9]+/oj"
            treaty = r"/eli/treaty/[a-z]+_[0-9]{4}(?:/art_[0-9]+)?/oj"
            if not re.fullmatch(act + "|" + treaty, path):
                raise CitationError("malformed", "Unsupported or malformed EU ELI work path")
            self.kind, self.value = "eli", "http://data.europa.eu" + path
        else:
            raise CitationError("malformed", f"Malformed or unsupported identifier: {value}")

    @property
    def official_url(self):
        if self.kind == "eli":
            return self.value.replace("http:", "https:", 1)
        return "https://eur-lex.europa.eu/legal-content/EN/TXT/?" + urlencode({"uri": self.kind.upper() + ":" + self.value if self.kind == "celex" else self.value})


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise CitationError("unsafe_link", "Only public HTTP(S) URLs without credentials are allowed")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise CitationError("unavailable", "DNS resolution failed") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise CitationError("unsafe_link", "Private and non-global network destinations are blocked")


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    validate_url(url)
    request = Request(url, headers={"User-Agent": "eu-law-cite/0.1 (bibliographic metadata)",
                                   "Accept": "application/sparql-results+json, application/json, text/html"})
    try:
        with build_opener(PublicRedirect()).open(request, timeout=30) as response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise CitationError("unavailable", "Response exceeds 2 MB limit")
            return data
    except HTTPError as exc:
        kind = "not_found" if exc.code in {404, 410} else "unavailable"
        raise CitationError(kind, f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CitationError("unavailable", str(exc)) from exc


def query(identifier, language):
    predicate = {"celex": "resource_legal_id_celex", "ecli": "case-law_ecli", "eli": "resource_legal_eli"}[identifier.kind]
    literal = json.dumps(identifier.value)
    return f'''PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title ?date ?language WHERE {{
?w cdm:{predicate} ?identifier . FILTER(STR(?identifier)={literal})
OPTIONAL {{ ?w cdm:resource_legal_id_celex ?celex }}
OPTIONAL {{ ?w cdm:work_date_document ?date }}
OPTIONAL {{ ?e cdm:expression_belongs_to_work ?w ; cdm:expression_title ?title ; cdm:expression_uses_language ?language .
FILTER(?language=<http://publications.europa.eu/resource/authority/language/{LANGUAGES[language]}>) }}
}} ORDER BY STRLEN(STR(?celex)) ?celex ?title LIMIT 20'''


class Client:
    def __init__(self, cache=None, ttl=86400, offline=False, transport=fetch):
        self.cache = Path(cache or Path.home() / ".cache/eu-law-cite")
        self.ttl, self.offline, self.transport = ttl, offline, transport

    def resolve(self, value, language="en"):
        identifier = Identifier(value)
        if language not in LANGUAGES:
            raise CitationError("unsupported", "Use an EU official two-letter language code")
        key = hashlib.sha256((identifier.value + ":" + language).encode()).hexdigest()
        path = self.cache / (key + ".json")
        try:
            saved = json.loads(path.read_text())
            if saved["schema"] == 1 and (self.offline or time.time() - saved["saved_at"] < self.ttl):
                return saved["citation"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if self.offline:
            raise CitationError("unavailable", "No valid cached metadata; offline mode never uses the network")
        url = ENDPOINT + "?" + urlencode({"query": query(identifier, language), "format": "application/sparql-results+json"})
        try:
            rows = json.loads(self.transport(url))["results"]["bindings"]
        except (ValueError, KeyError, TypeError) as exc:
            raise CitationError("unavailable", "Unexpected CELLAR response") from exc
        if not rows:
            raise CitationError("not_found", "Identifier is not present in the CELLAR catalogue")
        candidates = [r for r in rows if all(k in r for k in ("title", "date", "language"))]
        if not candidates:
            raise CitationError("unavailable", "Record exists but requested language, title or date is unavailable")
        row = candidates[0]
        try:
            date = [int(x) for x in row["date"]["value"][:10].split("-")]
            if len(date) != 3:
                raise ValueError("Invalid date")
            import datetime
            datetime.date(*date)
            title = " ".join(row["title"]["value"].split())
            if not title:
                raise ValueError("Missing title")
        except (ValueError, KeyError, TypeError) as exc:
            raise CitationError("unavailable", "Invalid metadata fields") from exc
        citation = {"id": identifier.value, "type": "legal_case" if identifier.kind == "ecli" or row.get("celex", {}).get("value", "").startswith("6") else "legislation",
                    "title": title, "issued": {"date-parts": [date]}, "language": language,
                    "URL": identifier.official_url}
        self.cache.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self.cache, delete=False) as output:
            json.dump({"schema": 1, "saved_at": time.time(), "citation": citation}, output)
            temporary = output.name
        os.replace(temporary, path)
        return citation


def bibtex(citation):
    replacements = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "&": r"\&", "_": r"\_", "#": r"\#", "$": r"\$", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}"}
    def escape(text):
        return "".join(replacements.get(c, c) for c in str(text))
    key = re.sub(r"[^A-Za-z0-9:-]", "-", citation["id"])
    date = "-".join(f"{p:02d}" for p in citation["issued"]["date-parts"][0])
    fields = {"title": citation["title"], "date": date, "year": date[:4], "language": citation["language"], "url": citation["URL"], "note": citation["id"]}
    return "@misc{" + key + ",\n" + ",\n".join(f"  {k} = {{{escape(v)}}}" for k, v in fields.items()) + "\n}\n"
