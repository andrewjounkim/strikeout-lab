"""Repo-hygiene tests: things that would fail silently if they broke (fonts) or that must never happen (secrets).

The project uses a keyless API, so there should be no credentials anywhere. These tests keep it that way.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKIP_DIRS = {".venv", "__pycache__", ".git", ".pytest_cache", "scratch"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".ini", ".json", ".html", ".css", ".yml", ".yaml", ".cfg"}


def repo_text_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES and not (set(path.relative_to(ROOT).parts) & SKIP_DIRS):
            yield path


def test_every_font_the_theme_asks_for_exists_and_static_serving_is_on():
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["enableStaticServing"] is True
    faces = config["theme"]["fontFaces"]
    assert faces, "the theme should declare its fonts"
    for face in faces:
        assert face["url"].startswith("app/static/")
        assert (ROOT / "static" / face["url"].removeprefix("app/static/")).is_file(), f"missing font file for {face['url']}"


def test_font_licenses_ship_with_the_fonts():
    for name in ("Inter-OFL.txt", "BarlowCondensed-OFL.txt"):
        assert "SIL Open Font License" in (ROOT / "static" / "fonts" / name).read_text(encoding="utf-8")


def test_gitignore_keeps_secrets_and_the_virtual_environment_out():
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for required in (".env", "config.local", "secrets.toml", ".streamlit/secrets.toml", ".venv/"):
        assert required in lines, f".gitignore should list {required}"


def test_no_credentials_are_committed_anywhere():
    key_assignment = re.compile(r"""(?i)\b(api[_-]?key|apikey|secret|token|passw(or)?d|client[_-]?secret)\b\s*[=:]\s*["']?[A-Za-z0-9_\-]{12,}""")
    private_key = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    key_in_url = re.compile(r"(?i)[?&](api_?key|apikey|token|access_token|auth)=[^&\s\"']+")
    this_file = Path(__file__).resolve()
    offenders = []
    for path in repo_text_files():
        if path.resolve() == this_file:
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in (key_assignment, private_key, key_in_url):
            match = pattern.search(body)
            if match:
                offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)[:40]}")
    assert not offenders, offenders


def test_the_app_only_ever_contacts_the_mlb_stats_api():
    """One API, no key: the only network host in the source is statsapi.mlb.com (w3.org is just an SVG namespace)."""
    hosts = set()
    for path in ROOT.glob("*.py"):
        hosts |= set(re.findall(r"https?://([A-Za-z0-9.-]+)", path.read_text(encoding="utf-8")))
    for path in (ROOT / "views").glob("*.py"):
        hosts |= set(re.findall(r"https?://([A-Za-z0-9.-]+)", path.read_text(encoding="utf-8")))
    assert hosts <= {"statsapi.mlb.com", "www.w3.org"}, hosts
