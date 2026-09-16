"""The site-URL derivation, executed as the file the container actually loads.

Why this file exists
--------------------
Two separate defects, both shipped, both caught only by a live deployment.

1. WP_HOME was hardcoded to localhost:8080, so the site broke completely on any
   other address: every asset URL pointed somewhere unreachable and every page
   301'd to a dead port.

2. The fix for (1) was written as PHP inside docker-compose.yml. **Docker Compose
   interpolates dollar-variables inside compose values**, so every PHP variable
   was replaced with an empty string and the container received

       = getenv_docker( 'MAARS_SITE_URL', '' );

   WordPress then died with `PHP Parse error: syntax error, unexpected token "="`
   on every single request. The site returned 500 to everyone.

   The earlier version had survived only because it contained no PHP variables
   at all. And this test did not catch it, because it loaded the compose file
   with yaml.safe_load and ran the PHP as written -- never as Compose delivers
   it. A green 21/21 against code Docker would never run.

So the logic now lives in docker/site-url.php, a real file: linted by php -l,
executed here directly, and referenced from compose by a single require_once
line with no dollar sign in it. test_static.py asserts that line stays free of
dollar signs, which is the property that actually keeps the site up.

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
    # --- the real deployment: ks0man.org, behind a TLS-terminating tunnel -----
    # ks0man.com is the 1997 site and is deliberately absent: this stack must
    # never answer for it, allowlisted or not.
    ("ks0man.org", {"MAARS_ALLOWED_HOSTS": "ks0man.org www.ks0man.org ks0man.waterburp.com"},
     "http://ks0man.org"),
    ("ks0man.waterburp.com", {"MAARS_ALLOWED_HOSTS": "ks0man.org www.ks0man.org ks0man.waterburp.com"},
     "http://ks0man.waterburp.com"),
    ("ks0man.com", {"MAARS_ALLOWED_HOSTS": "ks0man.org www.ks0man.org ks0man.waterburp.com"}, ""),
    # --- explicit override always wins --------------------------------------
    ("192.168.0.10:3039", {"MAARS_SITE_URL": "https://ks0man.org"},
     "https://ks0man.org"),
]


SITE_URL_PHP = os.path.join(ROOT, "docker", "site-url.php")


def assert_compose_requires_the_file() -> None:
    """compose must load the file, and must carry no dollar sign of its own."""
    d = yaml.safe_load(open(os.path.join(ROOT, "docker-compose.yml")))
    cfg = d["services"]["wordpress"]["environment"]["WORDPRESS_CONFIG_EXTRA"]
    assert "site-url.php" in cfg, (
        "docker-compose.yml no longer requires docker/site-url.php"
    )
    assert "$" not in cfg, (
        "WORDPRESS_CONFIG_EXTRA contains a dollar sign. Docker Compose will "
        "interpolate it away and WordPress will 500 on every request:\n  "
        + repr(cfg)
    )


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    assert_compose_requires_the_file()
    body_path = SITE_URL_PHP

    runner = """<?php
/* Stand in for the wordpress image's getenv_docker(), then call the real
   resolver out of the real file the container loads. */
function getenv_docker($k,$d){ return isset($GLOBALS['ENV'][$k]) ? $GLOBALS['ENV'][$k] : $d; }
$_SERVER = [];
require_once %s;
$cases = json_decode(file_get_contents($argv[1]), true);
$out = [];
foreach ($cases as $c) {
    $GLOBALS['ENV'] = $c['env'];
    $server = $c['host'] === '' ? [] : ['HTTP_HOST' => $c['host']];
    $out[] = maars_resolve_site_url($server);
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
