"""Unit tests for the three core healers (H1/H2/H3)."""

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healers.line_ending import LineEndingHealer
from healers.brace_escape import BraceEscapeHealer
from healers.yaml_format import YamlFormatHealer
from healers.quote_balance import QuoteBalanceHealer
from healers.key_map_gap import KeyMapGapHealer
from healers.decl_impl import DeclImplHealer


def _write_bytes(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def _write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(path) -> str:
    with open(path, "rb") as fh:
        return _sha_bytes(fh.read())


def test_h1_line_ending_detect_and_repair():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "f.txt")
    _write_bytes(p, b"\xef\xbb\xbf" + "a\r\nb\r\n".encode("utf-8"))

    h = LineEndingHealer()
    faults = h.detect(d)
    assert len(faults) == 1 and faults[0].healer == "line_ending"

    res = h.repair(faults[0])
    assert res.changed is True

    with open(p, "rb") as fh:
        data = fh.read()
    assert b"\r\n" not in data
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data == b"a\nb\n"


def test_h2_brace_escape_detect_and_repair():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "g.py")
    _write_text(p, 'x = "{{name}}"\n')

    h = BraceEscapeHealer()
    faults = h.detect(d)
    assert len(faults) == 1 and faults[0].healer == "brace_escape"

    res = h.repair(faults[0])
    assert res.changed is True

    with open(p, "r", encoding="utf-8") as fh:
        assert "{{" not in fh.read() and "{name}" in open(p).read()


def test_h3_yaml_format_detect_and_repair():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "c.yaml")
    _write_text(p, '{"name": "demo", "n": 2}')

    h = YamlFormatHealer()
    faults = h.detect(d)
    assert len(faults) == 1 and faults[0].healer == "yaml_format"

    res = h.repair(faults[0])
    assert res.changed is True

    with open(p, "r", encoding="utf-8") as fh:
        y = fh.read()
    assert y.lstrip().startswith("name:")
    assert "{" not in y


def test_h3_does_not_flag_real_yaml():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "real.yaml")
    _write_text(p, "name: demo\nn: 2\n")
    assert YamlFormatHealer().detect(d) == []


def test_h4_quote_balance_detect_and_repair():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "a.cfg")
    _write_text(p, '# c\napp = "x\nb = "y"\n')
    h = QuoteBalanceHealer()
    faults = h.detect(d)
    assert len(faults) == 1 and faults[0].healer == "quote_balance"
    res = h.repair(faults[0])
    assert res.changed is True
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.lstrip().startswith("#"):
                continue
            assert line.count('"') % 2 == 0


def test_h5_key_map_gap_detect_and_repair():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.csv")
    _write_text(p, "term,canonical\n区块链 / Web3,\nWeb 框架,django\n")
    h = KeyMapGapHealer()
    faults = h.detect(d)
    assert len(faults) == 1 and faults[0].healer == "key_map_gap"
    res = h.repair(faults[0])
    assert res.changed is True
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    by_term = {r["term"]: r["canonical"] for r in rows}
    assert by_term["区块链 / Web3"] == "blockchain"


def test_h6_decl_impl_detect_and_repair():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# P\nVersion: 1.0.0\n")
    p = os.path.join(d, "impl.py")
    _write_text(p, '__version__ = "0.9.0"\n')
    h = DeclImplHealer()
    faults = h.detect(d)
    assert len(faults) == 1 and faults[0].healer == "decl_impl"
    res = h.repair(faults[0])
    assert res.changed is True
    with open(p, "r", encoding="utf-8") as fh:
        assert '__version__ = "1.0.0"' in fh.read()


# ---------------------------------------------------------------------------
# H7 — integrity guard (trusted-baseline restore)
# ---------------------------------------------------------------------------
def _make_baseline_manifest(d, with_bytes=True):
    """Create a baseline.json (with embedded bytes) for a temp dir."""
    import hashlib
    import json

    files = {}
    for root, _, fns in os.walk(d):
        for fn in fns:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, d).replace("\\", "/")
            with open(p, "rb") as fh:
                data = fh.read()
            files[rel] = hashlib.sha256(data).hexdigest()
            if with_bytes:
                files.setdefault("__bytes__", {})[rel] = data.hex()
    with open(os.path.join(d, "baseline.json"), "w", encoding="utf-8") as fh:
        json.dump(files, fh, indent=2, sort_keys=True)
    return files


def test_h7_detects_any_modification():
    """Any byte deviation from baseline is detected (incl. logic injection)."""
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('def ok():\n    return 1\n')
    _make_baseline_manifest(d)

    # Malicious injection: syntactically valid backdoor appended.
    with open(os.path.join(d, "app.py"), "a", encoding="utf-8") as fh:
        fh.write('\nimport socket\ndef _steal():\n    pass\n_steal()\n')

    h = IntegrityGuardHealer()
    faults = h.detect(d)
    assert len(faults) == 1
    assert faults[0].healer == "integrity_guard"
    assert "deviation" in faults[0].description


def test_h7_repairs_to_baseline_bytes():
    """Repair restores the exact baseline bytes (removes backdoor)."""
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('def ok():\n    return 1\n')
    baseline = _make_baseline_manifest(d)
    with open(os.path.join(d, "app.py"), "a", encoding="utf-8") as fh:
        fh.write('\nimport socket\ndef _steal():\n    pass\n_steal()\n')

    h = IntegrityGuardHealer(baseline=baseline)
    faults = h.detect(d)
    assert len(faults) == 1
    res = h.repair(faults[0])
    assert res.changed is True
    with open(os.path.join(d, "app.py"), "r", encoding="utf-8") as fh:
        content = fh.read()
    assert "socket" not in content and "_steal" not in content
    assert content == 'def ok():\n    return 1\n'


def test_h7_no_baseline_means_no_faults():
    """Without a baseline, integrity guard stays silent (no false positives)."""
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('x = 1\n')
    h = IntegrityGuardHealer()
    assert h.detect(d) == []


def test_h7_repairs_with_disk_baseline_bytes():
    """Repair reads embedded bytes from baseline.json on disk (no git)."""
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('def ok():\n    return 1\n')
    make_baseline(d, with_bytes=True)  # writes baseline.json with __bytes__

    # inject a backdoor
    with open(os.path.join(d, "app.py"), "a", encoding="utf-8") as fh:
        fh.write('\nimport socket\ndef _steal():\n    pass\n_steal()\n')

    h = IntegrityGuardHealer()
    faults = h.detect(d)
    assert len(faults) == 1
    res = h.repair(faults[0])
    assert res.changed is True
    with open(os.path.join(d, "app.py"), "r", encoding="utf-8") as fh:
        assert fh.read() == 'def ok():\n    return 1\n'


def test_h7_restores_deleted_file_from_disk_baseline():
    """A virus-deleted file is recreated from the disk baseline bytes."""
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    sub = os.path.join(d, "pkg")
    os.makedirs(sub)
    with open(os.path.join(sub, "mod.py"), "w", encoding="utf-8") as fh:
        fh.write('VALUE = 42\n')
    make_baseline(d, with_bytes=True)

    victim = os.path.join(sub, "mod.py")
    os.remove(victim)  # virus deletes the file

    h = IntegrityGuardHealer()
    faults = h.detect(d)
    assert len(faults) == 1
    assert "missing" in faults[0].description

    res = h.repair(faults[0])
    assert res.changed is True
    assert os.path.exists(victim)
    with open(victim, "r", encoding="utf-8") as fh:
        assert fh.read() == 'VALUE = 42\n'


def test_h7_detect_new_files_strict_mode():
    """Strict mode reports files not in the baseline (virus-dropped files)."""
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('x = 1\n')
    make_baseline(d)

    # virus drops a new malicious file
    with open(os.path.join(d, "evil.py"), "w", encoding="utf-8") as fh:
        fh.write('import os\nos.system("calc.exe")\n')

    # Default: not reported (avoid false positives on benign new files).
    h_default = IntegrityGuardHealer()
    assert len(h_default.detect(d)) == 0

    # Strict mode: reported and quarantined (not hard-deleted).
    h_strict = IntegrityGuardHealer(detect_new_files=True)
    faults = h_strict.detect(d)
    assert len(faults) == 1
    assert "unexpected file" in faults[0].description

    res = h_strict.repair(faults[0])
    assert res.changed is True
    assert not os.path.exists(os.path.join(d, "evil.py"))
    # Quarantined (reversible), not deleted.
    q = os.path.join(d, ".quarantine", "evil.py")
    assert os.path.exists(q)


def test_h7_seal_detects_tampered_baseline():
    """Editing baseline.json to hide a tamper breaks the hash seal.

    This is the trust-anchor case: an attacker changes app.py AND rewrites the
    baseline hash to match, but cannot recompute the seal -> the tamper is
    still caught (the seal, not the per-file hash, is the anchor).
    """
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('x = 1\n')
    make_baseline(d)  # hash-sealed

    # Attacker tampers app.py AND rewrites the baseline hash to match it,
    # but does NOT recompute __seal__ (sophisticated attackers would; the
    # seal stops unsophisticated / accidental tampering of the manifest).
    with open(os.path.join(d, "app.py"), "a", encoding="utf-8") as fh:
        fh.write('x = 2\n')
    p = os.path.join(d, "baseline.json")
    with open(p, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["app.py"] = hashlib.sha256(b'x = 1\nx = 2\n').hexdigest()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    h = IntegrityGuardHealer()
    faults = h.detect(d)
    assert any("seal mismatch" in f.description for f in faults), faults


def test_h7_whitelist_allows_known_new_files():
    """Whitelisted new artefacts (logs, build dirs) are NOT flagged."""
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('x = 1\n')
    make_baseline(d)

    # Benign new artefacts that match the default whitelist.
    with open(os.path.join(d, "run.log"), "w", encoding="utf-8") as fh:
        fh.write("info\n")
    os.makedirs(os.path.join(d, "dist"))
    with open(os.path.join(d, "dist", "bundle.py"), "w", encoding="utf-8") as fh:
        fh.write("y = 9\n")

    h = IntegrityGuardHealer(detect_new_files=True)
    faults = h.detect(d)
    assert faults == [], faults


def test_h7_flaggs_unwhitelisted_new_file_despite_whitelist():
    """A dropped evil.py is still flagged even with the default whitelist."""
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as fh:
        fh.write('x = 1\n')
    make_baseline(d)
    with open(os.path.join(d, "evil.py"), "w", encoding="utf-8") as fh:
        fh.write('import os\nos.system("calc.exe")\n')

    h = IntegrityGuardHealer(detect_new_files=True)
    faults = h.detect(d)
    assert len(faults) == 1 and "unexpected file" in faults[0].description


def test_h7_covers_extended_extensions():
    """Tampered .sh / .env / .html files are detected (extended scope)."""
    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    specs = (("build.sh", "echo hi\n"),
             (".env", "KEY=1\n"),
             ("page.html", "<html></html>\n"))
    for name, content in specs:
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    make_baseline(d, with_bytes=True)

    extras = (("build.sh", "rm -rf /\n"),
              (".env", "KEY=2\n"),
              ("page.html", "<script>x</script>\n"))
    for name, extra in extras:
        with open(os.path.join(d, name), "a", encoding="utf-8") as fh:
            fh.write(extra)

    h = IntegrityGuardHealer()
    faults = h.detect(d)
    rels = {os.path.relpath(f.path, d) for f in faults}
    assert {"build.sh", ".env", "page.html"} <= rels, rels


def test_h7_disk_bytes_preferred_over_git_head():
    """Regression: when a target sits inside a git repo but carries its own
    baseline.json, repair must restore from the disk ``__bytes__`` (the
    baseline), NOT the outer repo's git HEAD.

    The bug: ``_baseline_bytes`` preferred git HEAD over the disk manifest, so
    a drill copy under ``work/`` (inside the kit's git repo) was restored to
    the out-of-sync HEAD content and never converged (1 residual fault).
    """
    import shutil

    from healers.integrity_guard import IntegrityGuardHealer, make_baseline

    d = tempfile.mkdtemp()
    # Stand up a real git repo whose HEAD version of app.py differs from the
    # version embedded in baseline.json.
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    app = os.path.join(d, "app.py")
    with open(app, "w", encoding="utf-8") as fh:
        fh.write("HEAD_VERSION\n")          # committed to git HEAD
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=d, check=True)

    # baseline.json embeds a DIFFERENT trusted version.
    with open(app, "w", encoding="utf-8") as fh:
        fh.write("BASELINE_VERSION\n")
    make_baseline(d, with_bytes=True)

    # Tamper the working file.
    with open(app, "a", encoding="utf-8") as fh:
        fh.write("TAMPER\n")

    h = IntegrityGuardHealer()
    faults = h.detect(d)
    assert len(faults) == 1, faults
    res = h.repair(faults[0])
    assert res.changed is True

    # Must be restored to BASELINE_VERSION (disk bytes), not HEAD_VERSION.
    with open(app, encoding="utf-8") as fh:
        content = fh.read()
    assert content == "BASELINE_VERSION\n", content
    # And the repair must converge — no residual integrity fault.
    assert h.detect(d) == [], "repair did not converge to baseline"


def test_h7_scan_binaries_includes_exe():
    """With scan_binaries=True, a binary (.exe) is baselined and protected."""
    from healers.integrity_guard import make_baseline, IntegrityGuardHealer

    d = tempfile.mkdtemp()
    exe = os.path.join(d, "tool.exe")
    with open(exe, "wb") as fh:
        fh.write(b"MZ\x90\x00ORIGINAL")
    make_baseline(d, scan_binaries=True, with_bytes=True)

    # Tamper the binary on disk.
    with open(exe, "wb") as fh:
        fh.write(b"MZ\x90\x00TAMPERED")
    h = IntegrityGuardHealer(scan_binaries=True)
    faults = h.detect(d)
    assert any(f.path == exe for f in faults), faults
    res = h.repair([f for f in faults if f.path == exe][0])
    assert res.changed is True
    with open(exe, "rb") as fh:
        assert fh.read() == b"MZ\x90\x00ORIGINAL"


def test_h7_check_metadata_detects_and_repairs_permission():
    """With check_metadata=True, a permission-mode change is detected+repaired."""
    from healers.integrity_guard import make_baseline, IntegrityGuardHealer

    d = tempfile.mkdtemp()
    p = os.path.join(d, "app.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")
    make_baseline(d, check_metadata=True)

    orig = os.lstat(p).st_mode & 0o777
    new_mode = 0o444 if orig != 0o444 else 0o666
    os.chmod(p, new_mode)
    if (os.lstat(p).st_mode & 0o777) == orig:
        # Platform does not honour chmod on this file — nothing to assert.
        return
    h = IntegrityGuardHealer(check_metadata=True)
    faults = h.detect(d)
    perm = [f for f in faults
            if f.description.startswith("metadata deviation: permission")]
    assert perm, faults
    res = h.repair(perm[0])
    assert res.changed is True
    assert (os.lstat(p).st_mode & 0o777) == orig


def test_h7_seal_covers_meta_tamper():
    """Tampering __meta__ without updating __seal__ trips the trust-anchor fault."""
    from healers.integrity_guard import make_baseline

    d = tempfile.mkdtemp()
    p = os.path.join(d, "app.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("x=1\n")
    make_baseline(d, check_metadata=True, with_bytes=True)

    bp = os.path.join(d, "baseline.json")
    with open(bp, encoding="utf-8") as fh:
        m = json.load(fh)
    m["__meta__"]["app.py"]["mode"] = 0  # change meta, leave seal stale
    with open(bp, "w", encoding="utf-8") as fh:
        json.dump(m, fh)

    from healers.integrity_guard import IntegrityGuardHealer
    h = IntegrityGuardHealer(check_metadata=True)
    faults = h.detect(d)
    assert any("baseline.json seal mismatch" in f.description for f in faults), \
        faults


def test_watch_once_heals_deviation():
    """The daemon's single-pass heal restores a tampered file to HEALED."""
    import self_heal_watch
    from healers.integrity_guard import make_baseline

    d = tempfile.mkdtemp()
    p = os.path.join(d, "app.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("x=1\n")
    make_baseline(d, with_bytes=True)

    with open(p, "a", encoding="utf-8") as fh:
        fh.write("TAMPER\n")

    res = self_heal_watch.heal_once(
        d, strict=True, scan_binaries=False, check_metadata=False,
        with_format=False, no_repair=False, verify_cmd=None)
    assert res["status"] == "HEALED", res
    healers = self_heal_watch._build_healers(True, False, False, False)
    assert healers[0].name == "integrity_guard"


def test_whitelist_matches_nested_dir_any_depth():
    """Regression: a directory whitelist pattern must match at any nesting level.

    Previously ``.pytest_cache/`` only matched at the top level, so
    ``tests/.pytest_cache/*`` was misjudged as an unexpected new file,
    quarantined, and made ``--self`` non-idempotent.
    """
    from healers.integrity_guard import (
        IntegrityGuardHealer, make_baseline, DEFAULT_NEW_FILE_WHITELIST,
    )

    d = tempfile.mkdtemp()
    p = os.path.join(d, "app.py")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("x=1\n")
    make_baseline(d, with_bytes=True)

    nested = os.path.join(d, "tests", ".pytest_cache")
    os.makedirs(nested, exist_ok=True)
    with open(os.path.join(nested, "CACHEDIR.TAG"), "w", encoding="utf-8") as fh:
        fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")

    h = IntegrityGuardHealer(detect_new_files=True,
                             new_file_whitelist=DEFAULT_NEW_FILE_WHITELIST)
    faults = h.detect(d)
    assert not any(".pytest_cache" in f.path for f in faults), \
        [f.path for f in faults]

    # An unrelated nested file must still be flagged (whitelist is not a no-op).
    os.makedirs(os.path.join(d, "pkg"), exist_ok=True)
    rogue = os.path.join(d, "pkg", "rogue.py")
    with open(rogue, "w", encoding="utf-8") as fh:
        fh.write("evil\n")
    faults = h.detect(d)
    assert any(f.path.endswith("rogue.py") for f in faults), \
        [f.path for f in faults]


def test_agent_guard_ignores_files_outside_scope():
    """Agent-guard: a tampered file OUTSIDE the guarded roots is not a fault.

    This is the core value of the mode: an AI agent lives inside a big host
    project, and guarding the whole tree produces noise. Only the workspace it
    writes to should be under integrity control.
    """
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    agent = os.path.join(d, ".agent")
    os.makedirs(agent, exist_ok=True)
    gen = os.path.join(agent, "gen.py")
    with open(gen, "w", encoding="utf-8") as fh:
        fh.write("print('ok')\n")
    host = os.path.join(d, "host_module.py")
    with open(host, "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")

    baseline = {
        ".agent/gen.py": _sha(gen),
        "host_module.py": _sha(host),
    }

    # Tamper the HOST file only.
    with open(host, "w", encoding="utf-8") as fh:
        fh.write("x = 2\n")

    h = IntegrityGuardHealer(baseline=baseline, agent_guard=True,
                             agent_guard_roots=[".agent"])
    faults = h.detect(d)
    assert faults == [], [f.description for f in faults]


def test_agent_guard_detects_and_repairs_inside_scope():
    """Agent-guard: tampering INSIDE the guarded root is still detected+healed."""
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    agent = os.path.join(d, ".agent")
    os.makedirs(agent, exist_ok=True)
    gen = os.path.join(agent, "gen.py")
    original = b"print('trusted')\n"
    with open(gen, "wb") as fh:
        fh.write(original)

    baseline = {
        ".agent/gen.py": _sha_bytes(original),
        "__bytes__": {".agent/gen.py": original.hex()},
    }

    with open(gen, "wb") as fh:
        fh.write(b"print('owned by attacker')\n")

    h = IntegrityGuardHealer(baseline=baseline, agent_guard=True,
                             agent_guard_roots=[".agent"])
    faults = h.detect(d)
    assert any(f.path == gen for f in faults), [f.description for f in faults]

    res = h.repair(faults[0])
    assert res.changed is True
    with open(gen, "rb") as fh:
        assert fh.read() == original
    assert h.detect(d) == []


def test_agent_guard_without_roots_guards_nothing():
    """Fail-safe: agent_guard with no roots protects nothing (no silent full tree)."""
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    p = os.path.join(d, "app.py")
    with open(p, "wb") as fh:
        fh.write(b"x = 1\n")
    baseline = {"app.py": _sha(p)}

    with open(p, "wb") as fh:
        fh.write(b"x = 2\n")

    h = IntegrityGuardHealer(baseline=baseline, agent_guard=True,
                             agent_guard_roots=[])
    assert h.detect(d) == []


def test_scope_roots_baseline_only_includes_scope():
    """make_baseline(scope_roots=...) only baselines files under those roots."""
    from healers.integrity_guard import make_baseline

    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".agent"), exist_ok=True)
    with open(os.path.join(d, ".agent", "gen.py"), "w", encoding="utf-8") as fh:
        fh.write("print('in')\n")
    with open(os.path.join(d, "host.py"), "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")

    manifest = make_baseline(d, scope_roots=[".agent"])
    tracked = {k for k in manifest if not k.startswith("__")}
    assert tracked == {".agent/gen.py"}, tracked


# ---------------------------------------------------------------------------
# Phase 2 step 2 — write_guard / agent_guard (pre-flight gate)
# ---------------------------------------------------------------------------

def _make_guarded_ws():
    """Temp workspace: git repo + .agent baseline + a host file outside scope."""
    import subprocess
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".agent"), exist_ok=True)
    _write_text(os.path.join(d, ".agent", "gen.py"), "print('v1')\n")
    _write_text(os.path.join(d, "host.py"), "x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True,
                   capture_output=True)
    from healers.integrity_guard import make_baseline
    make_baseline(d, scope_roots=[".agent"])
    return d


def test_write_guard_path_policy():
    """authorize_write: in-root ALLOW; host / .. escape / no-roots DENY."""
    from guards.write_guard import authorize_write

    d = tempfile.mkdtemp()
    ok, _ = authorize_write(os.path.join(d, ".agent", "x.py"), d, [".agent"])
    assert ok

    ok, why = authorize_write(os.path.join(d, "host.py"), d, [".agent"])
    assert not ok and "escapes" in why

    ok, _ = authorize_write(os.path.join(d, ".agent", "..", "host.py"),
                            d, [".agent"])
    assert not ok

    ok, _ = authorize_write(os.path.join(d, ".agent", "x.py"), d, [])
    assert not ok  # fail-safe: no roots => nothing allowed


def test_verify_scope_detects_deviation_in_scope_only():
    """Tampering inside the root is flagged; host files are ignored."""
    from guards.write_guard import verify_scope

    d = _make_guarded_ws()
    assert verify_scope(d, [".agent"]) == []

    # Host file outside the guarded root: changing it is not our business.
    _write_text(os.path.join(d, "host.py"), "x = 999  # rogue\n")
    assert verify_scope(d, [".agent"]) == []

    # Inside the root: must be flagged.
    _write_text(os.path.join(d, ".agent", "gen.py"), "import evil\n")
    faults = verify_scope(d, [".agent"])
    assert any("gen.py" in f.path for f in faults), [f.path for f in faults]


def test_agent_guard_run_refuses_on_deviation(tmp_path=None):
    """run executes when clean; a deviating workspace is never executed."""
    d = _make_guarded_ws()
    script = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "agent_guard.py")
    marker = os.path.join(d, "did_run.txt")

    # Clean workspace -> command executes.
    r = subprocess.run(
        [sys.executable, script, "run", "--target", d, "--root", ".agent",
         "--quiet", "--", sys.executable, "-c",
         f"open(r'{marker}','w').write('ran')"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(marker)

    # Tamper inside the root -> refuse to execute.
    os.remove(marker)
    _write_text(os.path.join(d, ".agent", "gen.py"), "import evil\n")
    r = subprocess.run(
        [sys.executable, script, "run", "--target", d, "--root", ".agent",
         "--quiet", "--", sys.executable, "-c",
         f"open(r'{marker}','w').write('ran')"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 1, r.stdout + r.stderr
    assert not os.path.isfile(marker)  # never executed


def test_agent_guard_hook_install_idempotent_and_protected():
    """install-hook idempotent; foreign hook refused (exit 4) both ways."""
    import agent_guard

    d = _make_guarded_ws()

    class A:
        pass

    a = A()
    a.target, a.roots, a.force = d, [".agent"], False

    assert agent_guard._do_install_hook(a) == 0
    hook = os.path.join(d, ".git", "hooks", "pre-commit")
    assert os.path.isfile(hook)

    # Idempotent: re-install over our own hook is fine.
    assert agent_guard._do_install_hook(a) == 0

    # Foreign hook: refuse both to install and to uninstall.
    with open(hook, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("#!/bin/sh\n# someone else's hook\n")
    assert agent_guard._do_install_hook(a) == 4

    u = A()
    u.target = d
    assert agent_guard._do_uninstall_hook(u) == 4

    # Ours again (after the foreign file is cleared): uninstall succeeds,
    # then nothing-to-do is OK.
    os.remove(hook)
    assert agent_guard._do_install_hook(a) == 0
    assert agent_guard._do_uninstall_hook(u) == 0
    assert agent_guard._do_uninstall_hook(u) == 0


# ---------------------------------------------------------------------------
# Phase 2 step 3 — trust root: out-of-band anchor + snapshots
# ---------------------------------------------------------------------------

def test_trust_anchor_seal_and_break():
    """seal records baseline hash; editing baseline breaks verify; restore fixes."""
    from guards.trust_root import seal_file, verify_file

    d = tempfile.mkdtemp()
    baseline = os.path.join(d, "baseline.json")
    _write_text(baseline, '{"a.py": "deadbeef", "__seal__": "x"}\n')
    anchor = os.path.join(d, "outside", "repo.anchor.json")

    seal_file(baseline, anchor)
    ok, _ = verify_file(baseline, anchor)
    assert ok

    _write_text(baseline, '{"a.py": "evilhash", "__seal__": "x"}\n')
    ok, detail = verify_file(baseline, anchor)
    assert not ok and "TRUST ANCHOR BROKEN" in detail

    _write_text(baseline, '{"a.py": "deadbeef", "__seal__": "x"}\n')
    ok, _ = verify_file(baseline, anchor)
    assert ok  # restore -> trust restored


def test_snapshot_promote_roundtrip():
    """--snapshot stores versioned baselines; promote rolls the anchor back."""
    import subprocess

    d = _make_guarded_ws()
    script = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "make_baseline.py")

    # v1 snapshot of the current clean state.
    r = subprocess.run([sys.executable, script, d, "--snapshot", "v1"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    v1 = os.path.join(d, "baselines", "v1.json")
    assert os.path.isfile(v1)

    # Evolve the workspace and snapshot v2.
    _write_text(os.path.join(d, ".agent", "gen.py"), "print('v2')\n")
    r = subprocess.run([sys.executable, script, d, "--snapshot", "v2"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr

    # Promote v1 back as the live baseline.
    import verify_trust
    class A:
        pass
    a = A()
    a.target, a.name, a.anchor = d, "v1", None
    assert verify_trust._do_promote(a) == 0
    with open(os.path.join(d, "baseline.json"), encoding="utf-8") as fh:
        promoted = fh.read()
    with open(v1, encoding="utf-8") as fh:
        assert promoted == fh.read()
    assert verify_trust.list_snapshots(d) == ["v1", "v2"]

    # Invalid snapshot names rejected.
    import pytest as _pt
    with _pt.raises(ValueError):
        verify_trust.snapshot_path(d, "../evil")


def test_watch_trust_anchor_fail_closed(tmp_path=None):
    """--trust-anchor broken -> TRUST_BROKEN, no repair attempted, exit 1."""
    from guards.trust_root import seal_file
    import self_heal_watch

    d = _make_guarded_ws()
    anchor = os.path.join(d, "outside", "a.json")
    seal_file(os.path.join(d, "baseline.json"), anchor)

    # Clean + intact anchor -> normal pass.
    res = self_heal_watch.heal_once(
        d, True, False, False, False, False, None, trust_anchor=anchor)
    assert res["status"] in ("CLEAN", "HEALED"), res

    # Attacker edits the baseline (recomputing the inner seal, which is
    # trivial) — the out-of-band anchor still catches it.
    bp = os.path.join(d, "baseline.json")
    data = json.loads(open(bp, encoding="utf-8").read())
    data[".agent/gen.py"] = hashlib.sha256(b"print('trojan')\n").hexdigest()
    from healers.integrity_guard import _seal_manifest
    data["__seal__"] = _seal_manifest(data)   # re-sealed: inner seal defeated
    with open(bp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh)

    res = self_heal_watch.heal_once(
        d, True, False, False, False, False, None, trust_anchor=anchor)
    assert res["status"] == "TRUST_BROKEN", res
    assert "ANCHOR" in (res.get("reason") or "").upper()


def test_repair_never_attaches_to_outer_baseline_across_git_boundary():
    """Drill-copy regression: an inner git repo living under a directory that
    has a decoy baseline.json must repair against ITS OWN git HEAD — walking
    up past a git boundary into another project's baseline is a trust mixup
    (this exact bug made the H7 INTEGRITY demo FAILED_CLOSED)."""
    from healers.integrity_guard import IntegrityGuardHealer

    d = tempfile.mkdtemp()
    inner = os.path.join(d, "copy")
    os.makedirs(inner)
    _write_text(os.path.join(inner, "app.py"), "x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=inner, check=True,
                   capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=inner, check=True,
                   capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=inner, check=True,
                   capture_output=True)

    # Decoy OUTER baseline.json claiming to govern "copy/app.py" (old code
    # walked up from the file and found it first).
    _write_text(os.path.join(d, "baseline.json"),
                json.dumps({"copy/app.py": "0" * 64}) + "\n")

    # Tamper the inner file; detect against the inner repo.
    _write_text(os.path.join(inner, "app.py"), "x = 666  # trojan\n")
    h = IntegrityGuardHealer()
    faults = h.detect(inner)          # _last_target = inner
    assert len(faults) == 1, [f.description for f in faults]
    res = h.repair(faults[0])
    assert res.changed, res.detail     # repaired from INNER git HEAD, not decoy
    assert "x = 1" in open(os.path.join(inner, "app.py"),
                           encoding="utf-8").read()
    assert not h.detect(inner)

    # Second pass with a FRESH healer and no detect(): _last_target is None,
    # so this exercises _find_target_root's git-boundary stop directly.
    _write_text(os.path.join(inner, "app.py"), "x = 999  # trojan again\n")
    from healers.base import Fault as _Fault
    h2 = IntegrityGuardHealer()
    fake = _Fault("integrity_guard",
                  os.path.join(inner, "app.py"),
                  "integrity deviation: sha256 zzz != baseline yyy")
    res2 = h2.repair(fake)
    assert res2.changed, res2.detail

