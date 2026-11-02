"""Integration harness: a sample target project's boot sequence.

On startup it (1) runs the self-heal engine over its own directory, and
(2) only proceeds to run the real application if the engine reports HEALED.
If the engine cannot reach green, boot ABORTS and escalates (fail-closed) — it
never silently pretends the project is healthy.

Run standalone:  python boot.py
(The engine must be importable; boot.py adds the kit root to sys.path.)
"""

import os
import sys

try:
    from engine import SelfHealEngine
    from guards.verify_gate import VerifyGate
    from healers.line_ending import LineEndingHealer
    from healers.brace_escape import BraceEscapeHealer
    from healers.yaml_format import YamlFormatHealer
    from healers.quote_balance import QuoteBalanceHealer
    from healers.key_map_gap import KeyMapGapHealer
    from healers.decl_impl import DeclImplHealer
except ImportError:
    _KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _KIT not in sys.path:
        sys.path.insert(0, _KIT)
    from engine import SelfHealEngine
    from guards.verify_gate import VerifyGate
    from healers.line_ending import LineEndingHealer
    from healers.brace_escape import BraceEscapeHealer
    from healers.yaml_format import YamlFormatHealer
    from healers.quote_balance import QuoteBalanceHealer
    from healers.key_map_gap import KeyMapGapHealer
    from healers.decl_impl import DeclImplHealer

try:
    from demo_project.app import run_app
except ImportError:  # standalone from inside demo_project/
    from app import run_app


DEFAULT_HEALERS = [
    LineEndingHealer(),
    BraceEscapeHealer(),
    YamlFormatHealer(),
    QuoteBalanceHealer(),
    KeyMapGapHealer(),
    DeclImplHealer(),
]


def boot(app_dir=None, extra_healers=None, test_command=None):
    """Boot the sample project with self-heal.

    Returns a dict. On success: {"boot": "OK", "heal": ..., "app": ...}.
    On failure: {"boot": "ABORTED", "status": "FAILED_CLOSED", "reason": ...}.
    """
    app_dir = app_dir or os.path.dirname(os.path.abspath(__file__))
    healers = list(DEFAULT_HEALERS)
    if extra_healers:
        healers.extend(extra_healers)
    engine = SelfHealEngine(healers=healers, test_command=test_command)
    res = engine.run(app_dir)
    if res["status"] != "HEALED":
        return {
            "boot": "ABORTED",
            "status": res["status"],
            "reason": res.get("reason", "engine did not reach green"),
            "log": res["log"],
        }
    app_out = run_app(app_dir)
    return {
        "boot": "OK",
        "heal": {"rounds": res["rounds"], "verify": res["verify"]},
        "app": app_out,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(boot(), indent=2, ensure_ascii=False))
