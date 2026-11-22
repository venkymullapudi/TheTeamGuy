"""The live smoke script must skip cleanly without credentials. Never runs live."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "live_smoke.sh"


def _run(extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_") and k != "TEAMGUY_SMOKE_FORCE"}
    env.update(extra or {})
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)


def _fake_bin(tmp_path, with_sdk):
    """A fake teamguy next to a fake python, so nothing real ever runs."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "ran"
    tg = bindir / "teamguy"
    tg.write_text(f"#!/usr/bin/env bash\ntouch {marker}\n")
    py = bindir / "python"
    py.write_text("#!/usr/bin/env bash\nexit %d\n" % (0 if with_sdk else 1))
    for f in (tg, py):
        f.chmod(0o755)
    return tg, marker


def test_skips_without_credentials(tmp_path):
    tg, marker = _fake_bin(tmp_path, with_sdk=True)
    r = _run({"TEAMGUY_BIN": str(tg)})
    assert r.returncode == 0
    assert "skipped" in r.stdout and "credentials" in r.stdout
    assert not marker.exists()


def test_oauth_token_does_not_count(tmp_path):
    tg, marker = _fake_bin(tmp_path, with_sdk=True)
    r = _run({"TEAMGUY_BIN": str(tg), "ANTHROPIC_API_KEY": "sk-ant-oat-not-real"})
    assert r.returncode == 0 and "skipped" in r.stdout
    assert not marker.exists()


def test_skips_without_sdk(tmp_path):
    tg, marker = _fake_bin(tmp_path, with_sdk=False)
    r = _run({"TEAMGUY_BIN": str(tg), "ANTHROPIC_API_KEY": "sk-ant-api-not-real"})
    assert r.returncode == 0 and "SDK" in r.stdout
    assert not marker.exists()


def test_runs_all_steps_with_forced_creds(tmp_path):
    tg, marker = _fake_bin(tmp_path, with_sdk=True)
    r = _run({"TEAMGUY_BIN": str(tg), "TEAMGUY_SMOKE_FORCE": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    for step in ("onboard", "work", "standup"):
        assert f"✅ {step}" in r.stdout
    assert marker.exists()
