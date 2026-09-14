"""The site URL derivation in docker-compose.yml, executed rather than eyeballed.

Why this file exists
--------------------
A hardcoded WP_HOME is the classic WordPress deployment failure, and it shipped
here. The stack was built and tested on localhost:8080; run on a LAN address it
broke completely, and in a way that pointed at the wrong culprit:

    Host: localhost:8080   on /about/  ->  200, no redirect
    Host: 192.168.0.10:3039 on /about/ ->  301 to 192.168.0.10:8080  (dead port)
    every asset URL, any Host          ->  http://localhost:8080/... (refused)

So the homepage rendered stripped, skywave.js never loaded, and the page told
the reader their browser had no WebGL2 -- which was false.

Deriving the URL from the Host header fixes that, but the Host header is
attacker-controlled: believed blindly it lets someone bake their own domain into
every absolute URL the site emits. Stock WordPress already reflects an arbitrary
Host into its canonical 301; we must not make WP_HOME itself follow.

So the derivation accepts the request host only where this stack could
plausibly live -- loopback, RFC1918/ULA, .local/.lan/.internal, or an explicit
MAARS_ALLOWED_HOSTS entry -- and otherwise sets nothing, leaving WordPress on
its stored option.

This test extracts the real PHP out of docker-compose.yml and runs it, so the
shipped logic is what gets checked.

Run:  python3 tests/test_site_url.py     (needs php on PATH or $MAARS_PHP)
"""

import json
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PHP = os.environ.get("MAARS_PHP", "php")
OUT = os.path.join(HERE, "out")

# (Host header, extra env, expected derived URL or "" for "leave unset")
CASES = [
    # --- must work: the addresses a club member would actually use -----------
    ("192.168.0.10:3039", {}, "http://192.168.0.10:3039"),
    ("localhost:8080", {}, "http://localhost:8080"),
    ("127.0.0.1:3039", {}, "http://127.0.0.1:3039"),
    ("10.0.0.5", {}, "http://10.0.0.5"),
    ("172.16.4.9:8080", {}, "http://172.16.4.9:8080"),
    ("192.168.0.2", {}, "http://192.168.0.2"),
    ("shack.local", {}, "http://shack.local"),
    ("pi.lan:3039", {}, "http://pi.lan:3039"),
    ("nas.internal", {}, "http://nas.internal"),
    # --- must be refused: attacker-chosen hosts -----------------------------
    ("evil.example.com", {}, ""),
    ("ks0man.org", {}, ""),
    ("203.0.113.7", {}, ""),
    ("8.8.8.8:80", {}, ""),
    # --- must be refused: malformed / smuggling attempts --------------------
    ("evil.com/\r\nX-Injected: 1", {}, ""),
    ("evil.com:80@localhost", {}, ""),
    ("evil.com path", {}, ""),
    ("", {}, ""),
    # --- opt-in allowlist ---------------------------------------------------
    ("ks0man.org", {"MAARS_ALLOWED_HOSTS": "ks0man.org www.ks0man.org"},
     "http://ks0man.org"),
    ("www.ks0man.org", {"MAARS_ALLOWED_HOSTS": "ks0man.org,www.ks0man.org"},
     "http://www.ks0man.org"),
    ("evil.example.com", {"MAARS_ALLOWED_HOSTS": "ks0man.org"}, ""),
    # --- explicit override always wins --------------------------------------
    ("192.168.0.10:3039", {"MAARS_SITE_URL": "https://ks0man.org"},
     "https://ks0man.org"),
]


def extract_php() -> str:
    """Pull the derivation out of the shipped compose file, minus the defines."""
    d = yaml.safe_load(open(os.path.join(ROOT, "docker-compose.yml")))
    cfg = d["services"]["wordpress"]["environment"]["WORDPRESS_CONFIG_EXTRA"]
    if "if ( '' !== $maars_url ) {" not in cfg:
        raise AssertionError(
            "compose no longer has the expected derivation shape; this test is stale"
        )
    return cfg.split("if ( '' !== $maars_url ) {")[0]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    body = extract_php()
    body_path = os.path.join(OUT, "site_url_body.php")
    open(body_path, "w").write("<?php\n" + body)

    runner = """<?php
function getenv_docker($k,$d){ return isset($GLOBALS['ENV'][$k]) ? $GLOBALS['ENV'][$k] : $d; }
$cases = json_decode(file_get_contents($argv[1]), true);
$out = [];
foreach ($cases as $c) {
    $GLOBALS['ENV'] = $c['env'];
    $_SERVER = $c['host'] === '' ? [] : ['HTTP_HOST' => $c['host']];
    $maars_url = '';
    include %s;
    $out[] = $maars_url;
}
echo json_encode($out);
""" % json.dumps(body_path)
    runner_path = os.path.join(OUT, "site_url_runner.php")
    open(runner_path, "w").write(runner)

    cases_path = os.path.join(OUT, "site_url_cases.json")
    open(cases_path, "w").write(
        json.dumps([{"host": h, "env": e} for h, e, _ in CASES])
    )

    r = subprocess.run(
        [PHP, runner_path, cases_path], capture_output=True, text=True
    )
    if r.returncode != 0:
        print("PHP runner failed:\n" + r.stdout + r.stderr)
        return 1
    got = json.loads(r.stdout)

    print("ks0man-site site-URL gate — the real PHP from docker-compose.yml\n")
    failed = 0
    for (host, env, want), actual in zip(CASES, got):
        ok = actual == want
        if not ok:
            failed += 1
        shown = repr(host) if host else "(no Host header)"
        envs = json.dumps(env) if env else "-"
        res = actual if actual else "(unset: WP keeps its stored option)"
        print(f"{'PASS' if ok else 'FAIL'}  {shown:<34} {envs:<40} -> {res}")
        if not ok:
            print(f"      expected: {want or '(unset)'}")

    print(f"\n{len(CASES) - failed}/{len(CASES)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
