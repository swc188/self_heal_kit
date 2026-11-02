"""Unit tests for the three core healers (H1/H2/H3)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healers.line_ending import LineEndingHealer
from healers.brace_escape import BraceEscapeHealer
from healers.yaml_format import YamlFormatHealer


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
