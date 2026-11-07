"""verify_trust — manage the out-of-band trust anchor and baseline snapshots.

Closes the last trust-root gap: ``baseline.json`` seals itself (``__seal__``),
so an attacker who can edit the baseline can recompute the seal. The anchor
recorded here lives somewhere ELSE (read-only mount / remote / backup) and
stores ``sha256(baseline)`` — compromising the chain now takes two independent
writes instead of one.

Subcommands:
  seal     baseline.json -> anchor file          (same as make_baseline --seal-to)
  verify   compare baseline.json against the anchor (exit 1 on break)
  list     show baselines/<name>.json snapshots
  promote  copy baselines/<name>.json over baseline.json (rollback anchor)

Exit codes: 0 ok · 1 anchor broken / verification failed · 2 usage error.

Usage:
    python verify_trust.py seal    --target /repo --anchor /mnt/ro/repo.anchor.json
    python verify_trust.py verify  --target /repo --anchor /mnt/ro/repo.anchor.json
    python verify_trust.py list    --target /repo
    python verify_trust.py promote --target /repo --name v1

Honest limit: hash-level, not key-level. If the attacker can also write the
anchor location, the chain is defeated — keep the anchor out of reach.
"""

from __future__ import annotations

import argparse
import os
import sys

from guards.trust_root import (list_snapshots, promote_snapshot, seal_file,
                               snapshot_path, verify_file)

HERE = os.path.dirname(os.path.abspath(__file__))

EXIT_OK, EXIT_BROKEN, EXIT_USAGE = 0, 1, 2


def _do_seal(args) -> int:
    baseline = os.path.join(os.path.abspath(args.target), "baseline.json")
    rec = seal_file(baseline, os.path.abspath(args.anchor))
    print(f"anchor sealed: {rec['baseline']} -> {os.path.abspath(args.anchor)}")
    print(f"sha256={rec['sha256']} at={rec['sealed_at']}")
    return EXIT_OK


def _do_verify(args) -> int:
    baseline = os.path.join(os.path.abspath(args.target), "baseline.json")
    ok, detail = verify_file(baseline, os.path.abspath(args.anchor))
    print(("TRUST OK — " if ok else "FAIL — ") + detail)
    return EXIT_OK if ok else EXIT_BROKEN


def _do_list(args) -> int:
    target = os.path.abspath(args.target)
    names = list_snapshots(target)
    if not names:
        print("(no snapshots — create with make_baseline.py --snapshot NAME)")
        return EXIT_OK
    for n in names:
        print(n)
    return EXIT_OK


def _do_promote(args) -> int:
    if not args.name:
        print("error: promote requires --name", file=sys.stderr)
        return EXIT_USAGE
    target = os.path.abspath(args.target)
    try:
        dst = promote_snapshot(target, args.name)
    except FileNotFoundError as e:
        print(f"error: snapshot not found: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(f"promoted snapshot '{args.name}' -> {dst}")
    if args.anchor:
        rec = seal_file(dst, os.path.abspath(args.anchor))
        print(f"anchor re-sealed: {os.path.abspath(args.anchor)} "
              f"(sha256={rec['sha256'][:12]}…)")
    else:
        print("提示：promote 改变了 baseline.json——若配有锚点，请重新 seal，"
              "否则 verify 会（正确地）报锚点失配")
    return EXIT_OK


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_trust", description="带外信任根与基线快照管理")
    sub = parser.add_subparsers(dest="action", required=True)

    def add_common(p, anchor_required=False):
        p.add_argument("--target", default=HERE, help="项目根目录")
        p.add_argument("--anchor", required=anchor_required,
                       help="带外锚点文件路径（只读介质/远端/备份）")

    add_common(sub.add_parser("seal", help="为 baseline.json 写带外锚点"), True)
    add_common(sub.add_parser("verify", help="校验 baseline.json 与锚点一致"), True)
    add_common(sub.add_parser("list", help="列出 baselines/ 快照"))
    p_promote = sub.add_parser("promote", help="快照回滚为当前 baseline.json")
    add_common(p_promote)
    p_promote.add_argument("--name", required=True, help="快照名")

    args = parser.parse_args(argv)
    if args.action == "seal":
        return _do_seal(args)
    if args.action == "verify":
        return _do_verify(args)
    if args.action == "list":
        return _do_list(args)
    if args.action == "promote":
        return _do_promote(args)
    parser.error("unknown action")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
