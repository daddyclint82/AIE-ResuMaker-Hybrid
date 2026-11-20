"""Production config: no API docs, and no O*NET relay anywhere.

Run: python tests/test_production_config.py   (or pytest)

APP_ENV is read when main is imported, so each check imports it in a fresh
process and drives the app with FastAPI's TestClient: no server, no network.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS = ("/docs", "/redoc", "/openapi.json", "/api/jobs/search?query=nurse", "/healthz")
PROBE = f"""
from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
print("STATUS", *(client.get(p).status_code for p in {PATHS!r}))
"""


def _statuses(app_env):
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env={**os.environ, "APP_ENV": app_env},
                         capture_output=True, text=True, check=True).stdout
    line = next(ln for ln in out.splitlines() if ln.startswith("STATUS "))
    return dict(zip(PATHS, map(int, line.split()[1:])))


def test_production_serves_no_api_docs_and_no_onet_relay():
    got = _statuses("production")
    assert got == {"/docs": 404, "/redoc": 404, "/openapi.json": 404,
                   "/api/jobs/search?query=nurse": 404, "/healthz": 200}, got


def test_development_keeps_the_api_docs():
    got = _statuses("development")
    assert got == {"/docs": 200, "/redoc": 200, "/openapi.json": 200,
                   "/api/jobs/search?query=nurse": 404, "/healthz": 200}, got


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", str(e)[:200])
    sys.exit(1 if failed else 0)
