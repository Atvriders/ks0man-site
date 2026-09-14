#!/usr/bin/env python3
"""Static gate for the ks0man-site demo image.

This file is the reason the GHCR image can be public: it refuses to let a
personal e-mail address, a phone number, a home / observer-post street address,
a LAN IP or a developer host path reach a tracked file.

Runs two ways:
    pytest tests/test_static.py            (if pytest happens to be installed)
    python3 tests/test_static.py           (always; prints PASS/FAIL, exit != 0 on failure)

The PHP binary used for `php -l` comes from $MAARS_PHP, else "php".
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "CONTRACT.md"
PHP = os.environ.get("MAARS_PHP") or "php"

# --------------------------------------------------------------------------
# repo walking
# --------------------------------------------------------------------------

SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", "vendor", ".idea", ".vscode"}
SKIP_REL_DIRS = {Path("tests/out")}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".svgz",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".pdf", ".mp4", ".webm", ".mp3", ".wav",
    ".sqlite", ".db", ".pyc",
}
MAX_BYTES = 2_000_000


def repo_files() -> list[Path]:
    """Every tracked-ish text file in the repo (no VCS junk, no build output)."""
    found: list[Path] = []
    for root, dirs, files in os.walk(REPO):
        rootp = Path(root)
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIR_NAMES
            and (rootp / d).relative_to(REPO) not in SKIP_REL_DIRS
        ]
        dirs.sort()
        for name in sorted(files):
            found.append(rootp / name)
    return found


def text_files() -> list[Path]:
    out = []
    for p in repo_files():
        if p.suffix.lower() in BINARY_EXT:
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        out.append(p)
    return out


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------
# the contract's own file map is the source of truth
# --------------------------------------------------------------------------

PATH_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_./-]*$")


def contract_file_map() -> list[str]:
    assert CONTRACT.is_file(), "CONTRACT.md is missing — nothing to check against"
    lines = read(CONTRACT).splitlines()
    paths: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            inside = line.strip().lower().startswith("## file map")
            continue
        if not inside:
            continue
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        if PATH_RE.match(entry):
            paths.append(entry)
    return paths


# --------------------------------------------------------------------------
# 1. file map
# --------------------------------------------------------------------------

def test_contract_file_map_is_parseable():
    paths = contract_file_map()
    assert len(paths) >= 25, f"only parsed {len(paths)} paths out of CONTRACT.md's file map: {paths}"
    for required in ("docker-compose.yml", "Dockerfile", "content/seed.json",
                     "wp/themes/maars/assets/js/skywave.js",
                     "wp/plugins/maars-core/maars-core.php"):
        assert required in paths, f"CONTRACT.md file map no longer names {required}"


def test_every_contract_path_exists_and_is_non_empty():
    missing, empty = [], []
    for entry in contract_file_map():
        p = REPO / entry
        if not p.is_file():
            missing.append(entry)
        elif p.stat().st_size == 0:
            empty.append(entry)
    assert not missing, "missing files from the contract file map:\n  " + "\n  ".join(missing)
    assert not empty, "empty files (contract requires content):\n  " + "\n  ".join(empty)


# --------------------------------------------------------------------------
# 2. php -l on everything
# --------------------------------------------------------------------------

def test_php_binary_is_available():
    try:
        r = subprocess.run([PHP, "-v"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        raise AssertionError(f"cannot run PHP ({PHP!r}); set $MAARS_PHP: {exc}") from None
    assert r.returncode == 0, f"{PHP} -v failed: {r.stderr.strip()}"


def test_every_php_file_lints():
    php_files = [p for p in repo_files() if p.suffix == ".php"]
    assert php_files, "no .php files found at all — the plugin/theme did not land"
    failures = []
    for p in php_files:
        r = subprocess.run([PHP, "-l", str(p)], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            failures.append(f"{rel(p)}: {(r.stdout + r.stderr).strip()}")
    assert not failures, "php -l failures:\n  " + "\n  ".join(failures)


def test_php_files_have_no_closing_tag_or_bom():
    """A stray ?> or a BOM in a WordPress plugin file emits output before headers."""
    problems = []
    for p in repo_files():
        if p.suffix != ".php":
            continue
        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{rel(p)}: UTF-8 BOM")
        if raw.rstrip().endswith(b"?>"):
            problems.append(f"{rel(p)}: file ends with a closing ?> tag")
    assert not problems, "PHP output-before-headers hazards:\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------
# 3. JSON + YAML
# --------------------------------------------------------------------------

def test_all_json_parses():
    jsons = [p for p in repo_files() if p.suffix == ".json"]
    for required in ("wp/themes/maars/theme.json", "content/seed.json"):
        assert (REPO / required).is_file(), f"{required} is missing"
    bad = []
    for p in jsons:
        try:
            data = json.loads(read(p))
        except Exception as exc:
            bad.append(f"{rel(p)}: {exc}")
            continue
        if not data:
            bad.append(f"{rel(p)}: parses but is empty")
    assert not bad, "JSON problems:\n  " + "\n  ".join(bad)


def test_theme_json_carries_the_measured_palette():
    """The palette was measured from the club's own 1997 stylesheet. It is not negotiable."""
    theme = REPO / "wp/themes/maars/theme.json"
    data = json.loads(read(theme))
    assert int(data.get("version", 0)) >= 2, "theme.json must be version 2 or later"
    # every hex the theme layer mentions, wherever it mentions it
    pool = read(theme)
    for extra in ("wp/themes/maars/style.css", "wp/themes/maars/assets/css/maars.css"):
        p = REPO / extra
        if p.is_file():
            pool += read(p)
    pool = pool.upper()
    light = ["00008C", "990066", "DBDBFB", "14142B", "FFFFFF", "FBFBFD", "A5171B"]
    dark = ["9FA0F2", "F09FD0", "0C0C18", "14142A", "EDEDF7"]
    missing = [h for h in light + dark if h not in pool]
    assert not missing, (
        "contract palette colours missing from theme.json/style.css/maars.css: "
        + ", ".join("#" + h for h in missing)
    )
    # theme.json's own palette must at least contain the three brand colours
    palette_blob = json.dumps(data.get("settings", {}).get("color", {})).upper()
    for h in ("00008C", "990066", "DBDBFB"):
        assert h in palette_blob, f"#{h} is not in theme.json settings.color"


def test_no_webfont_downloads_in_theme_json():
    data = json.loads(read(REPO / "wp/themes/maars/theme.json"))
    blob = json.dumps(data)
    assert "fonts.googleapis.com" not in blob and "fonts.gstatic.com" not in blob, \
        "theme.json must not pull a webfont (system stacks only)"


def _load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover
        raise AssertionError("PyYAML is required for the compose checks (pip install pyyaml)") from None
    return yaml.safe_load(read(path))


def test_docker_compose_parses_and_names_the_contract_services():
    compose = REPO / "docker-compose.yml"
    assert compose.is_file(), "docker-compose.yml is missing"
    data = _load_yaml(compose)
    assert isinstance(data, dict), "docker-compose.yml did not parse to a mapping"
    services = data.get("services")
    assert isinstance(services, dict) and services, "docker-compose.yml declares no services"
    assert len(services) == 2, (
        "the contract names exactly two services (the site and the database); found "
        f"{len(services)}: {sorted(services)}"
    )
    images = {name: str((svc or {}).get("image", "")) for name, svc in services.items()}
    site = [n for n, img in images.items() if img.startswith("ghcr.io/atvriders/ks0man-site")]
    db = [n for n, img in images.items() if img.startswith("mariadb:11.4")]
    assert len(site) == 1, f"expected exactly one service on ghcr.io/atvriders/ks0man-site, got {images}"
    assert len(db) == 1, f"expected exactly one service on mariadb:11.4, got {images}"
    assert site[0] != db[0]


def test_dockerfile_pins_the_contract_base_image():
    df = read(REPO / "Dockerfile")
    assert "wordpress:6.7-php8.3-apache" in df, \
        "Dockerfile must build FROM wordpress:6.7-php8.3-apache (pinned by the contract)"
    assert not re.search(r"^\s*FROM\s+\S+:latest", df, re.M | re.I), "no :latest base images"


def test_workflow_yaml_parses_and_pushes_the_public_image():
    wf = REPO / ".github/workflows/build.yml"
    assert wf.is_file(), ".github/workflows/build.yml is missing"
    data = _load_yaml(wf)
    assert isinstance(data, dict) and data.get("jobs"), "build.yml has no jobs"
    assert "ghcr.io/atvriders/ks0man-site" in read(wf), \
        "build.yml must publish ghcr.io/atvriders/ks0man-site"


def test_no_build_step_dependencies():
    """The contract forbids Composer, npm and any build step."""
    banned = ["composer.json", "composer.lock", "package.json", "package-lock.json",
              "yarn.lock", "pnpm-lock.yaml", "webpack.config.js", "vite.config.js"]
    present = [b for b in banned if (REPO / b).is_file()]
    assert not present, f"contract forbids a build step; found {present}"


# --------------------------------------------------------------------------
# 4. THE PII GATE
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
PHONE_RE = re.compile(r"(?<!\d)\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)")
STREET_RE = re.compile(
    r"\b\d{3,5} [NSEW]?\.? ?\w+ (St|Ave|Rd|Hwy|Street|Avenue|Road)\b")
STREET2_RE = re.compile(
    r"\b\d{2,5} [NSEW]?\.? ?\w+ "
    r"(Ln|Lane|Dr|Drive|Ct|Court|Blvd|Boulevard|Ter|Terrace|Cir|Circle|Pl|Place|Trl|Trail|Way)\b")
POBOX_RE = re.compile(r"\bP\.? ?O\.? ?Box\s+\d+", re.I)
ZIP4_RE = re.compile(r"(?<!\d)\d{5}-\d{4}(?!\d)")
HOSTPATH_RE = re.compile(r"(/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\)")
LANIP_RE = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")

# The ONLY street address allowed: the club's public meeting venue
# (Manhattan/Riley County Senior Center), which the constitution SOP publishes.
VENUE_OK = re.compile(r"^301\s*n\.?\s*4th\s*st\.?$", re.I)
# Placeholder mail domains only. A real domain here is a bug, not a convenience.
OK_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "example.edu",
                    "example.test", "localhost", "invalid", "test.invalid")

HEX_TOKEN_RE = re.compile(r"[0-9A-Za-z]+")


def _token_around(text: str, start: int, end: int) -> str:
    a, b = start, end
    while a > 0 and (text[a - 1].isalnum()):
        a -= 1
    while b < len(text) and text[b].isalnum():
        b += 1
    return text[a:b]


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _scan(pattern: re.Pattern, allow=None) -> list[str]:
    hits = []
    for p in text_files():
        body = read(p)
        for m in pattern.finditer(body):
            if allow and allow(m, body, p):
                continue
            hits.append(f"{rel(p)}:{_line_of(body, m.start())}: {m.group(0)!r}")
    return hits


def _email_ok(m, body, p) -> bool:
    domain = m.group(0).rsplit("@", 1)[1].lower().rstrip(".")
    return any(domain == d or domain.endswith("." + d) for d in OK_EMAIL_DOMAINS)


def _phone_ok(m, body, p) -> bool:
    # A 10-digit run inside a long hex blob (an action SHA, a hash) is not a phone number.
    token = _token_around(body, m.start(), m.end())
    if len(token) >= 16 and re.fullmatch(r"[0-9a-fA-F]+", token):
        return True
    return False


def _street_ok(m, body, p) -> bool:
    norm = re.sub(r"\s+", " ", m.group(0)).strip()
    return bool(VENUE_OK.match(norm))


def test_pii_gate_no_email_addresses():
    hits = _scan(EMAIL_RE, _email_ok)
    assert not hits, (
        "E-MAIL ADDRESSES IN A PUBLIC IMAGE. The archive holds 28 of them and none may ship.\n  "
        + "\n  ".join(hits))


def test_pii_gate_no_phone_numbers():
    hits = _scan(PHONE_RE, _phone_ok)
    assert not hits, "PHONE-NUMBER PATTERNS found:\n  " + "\n  ".join(hits)


def test_pii_gate_no_street_addresses():
    hits = _scan(STREET_RE, _street_ok) + _scan(STREET2_RE, _street_ok)
    assert not hits, (
        "STREET ADDRESSES found. Only the club's public meeting venue is allowed.\n  "
        + "\n  ".join(sorted(set(hits))))


def test_pii_gate_no_po_boxes_or_zip_plus_four():
    hits = _scan(POBOX_RE) + _scan(ZIP4_RE)
    assert not hits, "MAILING-ADDRESS PATTERNS found:\n  " + "\n  ".join(hits)


# tests/test_site_url.py exists to prove that PRIVATE addresses are accepted by
# the site-URL derivation and public ones refused, so it must contain RFC1918
# literals. They are textbook fixture addresses, never a real host. This is the
# only exempt file, it is exempt by path, and the meta-check below keeps the
# exemption from widening or from sheltering a real address.
LANIP_EXEMPT = {"tests/test_site_url.py"}


def test_no_lan_ip_addresses():
    hits = _scan(LANIP_RE, allow=lambda m, body, p: rel(p) in LANIP_EXEMPT)
    assert not hits, "REAL LAN IPs found (RFC1918):\n  " + "\n  ".join(hits)


def test_the_lan_ip_exemption_is_not_a_blanket_hole():
    """The exemption must cover exactly one file, and that file must not be
    able to smuggle in a real-looking home address under its cover."""
    assert LANIP_EXEMPT == {"tests/test_site_url.py"}, (
        "the LAN-IP exemption grew; every added path is a place a real address "
        "can hide in a public repository"
    )
    body = read(REPO / "tests" / "test_site_url.py")
    # 192.168.0.x and 10.0.0.x and 172.16.x are textbook example addresses;
    # anything else in the fixture list deserves a second look.
    found = set(LANIP_RE.findall(body)) if LANIP_RE.groups == 0 else {
        m.group(0) for m in LANIP_RE.finditer(body)
    }
    allowed_prefixes = tuple(
        p + "." for p in ("192" + ".168.0", "10" + ".0.0", "172" + ".16")
    )
    stray = [ip for ip in found if not ip.startswith(allowed_prefixes)]
    assert not stray, f"non-textbook private IPs in the exempt fixture file: {stray}"


# CONTRACT.md is the build-time working document handed to the agents; its first
# lines name the developer's checkout root. It is not part of the image and not
# part of the site. Everything else in the repo is strict.
HOSTPATH_EXEMPT = {"CONTRACT.md"}


def test_no_developer_host_paths():
    hits = _scan(HOSTPATH_RE, allow=lambda m, body, p: rel(p) in HOSTPATH_EXEMPT)
    assert not hits, "DEVELOPER HOST PATHS found (use ~ or a relative path):\n  " + "\n  ".join(hits)


def test_venue_allowlist_actually_matches_the_venue():
    """Guard the guard: if the allowlist stops matching, the gate starts lying."""
    assert VENUE_OK.match("301 N. 4th St")
    assert VENUE_OK.match("301 N 4th St.")
    assert not VENUE_OK.match("1234 " + "Poyntz Ave")


def test_pii_regexes_actually_catch_synthetic_pii():
    """A gate that never fires is not a gate. Prove every pattern bites.

    The fixtures are assembled from halves at runtime so that this file does not
    itself contain the patterns it hunts for — the gate scans the whole repo,
    tests included, and must not need an exemption for its own test data.
    """
    email = "ko0aa@" + "nowhere-example.net"
    ok_email = "admin@" + "example.com"
    phone_a = "(785) " + "555-0142"
    phone_b = "785-" + "555-0142"
    phone_c = "78555" + "50142"
    street_a = "2100 N " + "Poyntz Ave"
    street_b = "1804 " + "Hillcrest Dr"
    pobox = "P.O. " + "Box 1234"
    zip4 = "66502-" + "1234"
    lan_a = "192." + "168.7.7"
    lan_b = "10." + "0.0.7"
    lan_c = "172." + "20.4.9"
    hostpath = "/home/" + "someone/ks0man-site"

    assert EMAIL_RE.search(email), "e-mail pattern is broken"
    assert not _email_ok(EMAIL_RE.search(email), "", None), "a real domain must NOT be allowlisted"
    assert _email_ok(EMAIL_RE.search(ok_email), "", None), "example.com must stay allowlisted"
    assert PHONE_RE.search(phone_a) and PHONE_RE.search(phone_b) and PHONE_RE.search(phone_c)
    assert STREET_RE.search(street_a), "street pattern is broken"
    assert STREET2_RE.search(street_b), "second street pattern is broken"
    assert POBOX_RE.search(pobox) and ZIP4_RE.search(zip4)
    assert LANIP_RE.search(lan_a) and LANIP_RE.search(lan_b) and LANIP_RE.search(lan_c)
    assert not LANIP_RE.search("127.0.0.1"), "loopback is not a LAN leak"
    assert not LANIP_RE.search("mariadb 11.4.0 / wordpress 6.7"), "version strings are not IPs"
    assert HOSTPATH_RE.search(hostpath), "host-path pattern is broken"
    assert not HOSTPATH_RE.search("/var/www/html/wp-content"), "container paths are fine"
    # and the phone guard must still ignore a 10-digit run inside a pinned action SHA
    sha = "abcdef" + "01234" + "56789" + "abcdef"
    m = PHONE_RE.search(sha)
    assert m is not None, "phone pattern should see the digit run"
    assert _phone_ok(m, sha, None), "hex-blob guard is broken"
    assert not _phone_ok(PHONE_RE.search(phone_b), phone_b, None), "guard must not swallow real numbers"


def test_no_member_roster_shaped_lists():
    """Cheap smell test: three or more callsign+name pairs in one file is a roster.

    One or two is club history (the founder, an officer role) and is allowed;
    a table of them is the 41-name membership list and is not.
    """
    roster = re.compile(r"\b(?:K|W|N|A)[A-Z]?\d[A-Z]{1,3}\b\s*[,|]\s*[A-Z][a-z]+ [A-Z][a-z]+")
    hits = []
    for p in text_files():
        body = read(p)
        found = roster.findall(body)
        if len(found) >= 3:
            hits.append(f"{rel(p)}: {len(found)} callsign/name pairs — that is a roster")
    assert not hits, "ROSTER-SHAPED LISTS found:\n  " + "\n  ".join(hits)


# --------------------------------------------------------------------------
# 5. skywave.js is self-contained
# --------------------------------------------------------------------------

SKYWAVE = "wp/themes/maars/assets/js/skywave.js"


def test_skywave_exists_and_exports_the_contract_entry_point():
    p = REPO / SKYWAVE
    assert p.is_file(), f"{SKYWAVE} is missing"
    body = read(p)
    assert "MAARSSkywave" in body, "skywave.js must expose window.MAARSSkywave"
    assert re.search(r"\bmount\b", body), "skywave.js must expose mount(canvasEl, opts)"
    assert "maarsReady" in body, "skywave.js must set canvas.dataset.maarsReady = '1'"
    assert "maars-skywave--fallback" in body, \
        "skywave.js must add maars-skywave--fallback when webgl2 is unavailable"
    assert "webgl2" in body, "skywave.js must request a raw WebGL2 context"


def test_skywave_has_no_network_calls_and_no_three_js():
    body = read(REPO / SKYWAVE)
    problems = []
    # quoted URL literals of any kind
    for m in re.finditer(r"""["'`][^"'`\n]*https?://""", body):
        problems.append(f"URL string literal at line {_line_of(body, m.start())}: {m.group(0)!r}")
    for api in ("fetch(", "XMLHttpRequest", "importScripts", "sendBeacon",
                "new WebSocket", "EventSource", "import(", "require("):
        idx = body.find(api)
        if idx != -1:
            problems.append(f"network/loader API {api!r} at line {_line_of(body, idx)}")
    for m in re.finditer(r"""(?:from|import|require)\s*\(?\s*["'][^"']*\bthree\b[^"']*["']""", body):
        problems.append(f"three.js import at line {_line_of(body, m.start())}")
    if re.search(r"^\s*import\s", body, re.M) or re.search(r"^\s*export\s", body, re.M):
        problems.append("skywave.js must be a classic script (no ES module import/export): "
                        "the block enqueues it plainly and the test harness loads it over file://")
    assert not problems, "skywave.js is not self-contained:\n  " + "\n  ".join(problems)


def test_no_cdn_references_anywhere_in_the_theme_or_plugin():
    cdn = re.compile(r"(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|unpkg\.com|code\.jquery\.com|three\.min\.js)")
    hits = []
    for p in text_files():
        r = rel(p)
        if not (r.startswith("wp/") or r.startswith("docker/")):
            continue
        body = read(p)
        for m in cdn.finditer(body):
            hits.append(f"{r}:{_line_of(body, m.start())}: {m.group(0)}")
    assert not hits, "CDN references in the shipped image:\n  " + "\n  ".join(hits)


# --------------------------------------------------------------------------
# 6. staleness is the whole point — make sure the words are there
# --------------------------------------------------------------------------

def test_seed_content_marks_the_repeater_facts_unverified():
    seed = REPO / "content/seed.json"
    body = read(seed).lower()
    assert "unverified" in body, \
        "content/seed.json must carry the 'unverified' grade — the repeater facts are unconfirmed"


def test_freshness_and_meeting_functions_are_named_per_contract():
    inc = REPO / "wp/plugins/maars-core/inc/freshness.php"
    body = read(inc)
    for fn in ("maars_freshness_state", "maars_next_meeting", "maars_days_since_last_publication"):
        assert re.search(r"function\s+" + fn + r"\s*\(", body), \
            f"{fn}() is not defined in inc/freshness.php (contract names it exactly)"


# --------------------------------------------------------------------------
# standalone runner
# --------------------------------------------------------------------------

def test_font_sources_point_into_the_parent_theme():
    """The three faces are self-hosted by Twenty Twenty-Five. If a src path is
    wrong the browser silently falls back to Times and the whole typographic
    direction evaporates with no error anywhere, so the shape is asserted here."""
    import json as _json

    d = _json.load(open(REPO / "wp/themes/maars/theme.json"))
    fams = d["settings"]["typography"]["fontFamilies"]
    slugs = {f["slug"] for f in fams}
    assert {"display", "body", "data"} <= slugs, f"missing font slugs: {slugs}"
    prefix = "/wp-content/themes/twentytwentyfive/assets/fonts/"
    seen = 0
    for fam in fams:
        for face in fam.get("fontFace") or []:
            src = face.get("src")
            for one in src if isinstance(src, list) else [src]:
                assert one.startswith(prefix), (
                    f"{fam['slug']} font src does not point into the parent theme: {one}"
                )
                assert one.endswith(".woff2"), f"not woff2: {one}"
                seen += 1
    assert seen >= 3, f"expected at least three @font-face srcs, found {seen}"


def _all_checks():
    g = globals()
    return [(name, g[name]) for name in list(g) if name.startswith("test_") and callable(g[name])]


def main() -> int:
    print(f"ks0man-site static gate — repo {REPO}")
    print(f"php binary: {PHP}\n")
    failures = []
    for name, fn in _all_checks():
        try:
            fn()
        except AssertionError as exc:
            failures.append((name, str(exc) or "assertion failed"))
            print(f"FAIL  {name}")
            for line in str(exc).splitlines():
                print(f"      {line}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS  {name}")
    total = len(_all_checks())
    print(f"\n{total - len(failures)}/{total} checks passed")
    if failures:
        print("\nFAILED:")
        for name, msg in failures:
            print(f"  - {name}: {msg.splitlines()[0]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

