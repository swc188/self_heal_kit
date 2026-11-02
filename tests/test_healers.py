"""Unit tests for the three core healers (H1/H2/H3)."""

import csv
import os
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
