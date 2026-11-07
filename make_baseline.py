"""Create a trusted sha256 baseline for a directory.

Usage:
    python make_baseline.py <target_dir> [--out manifest.json] [--with-bytes]
                            [--scan-binaries] [--check-metadata]
                            [--scope-root .agent ...]
                            [--snapshot NAME] [--seal-to ANCHOR]

Writes ``<target_dir>/baseline.json`` by default — a manifest of
{relative_path: sha256} for every in-scope text/source file. Once the baseline
exists, IntegrityGuardHealer treats ANY deviation from it as a fault and can
restore the original bytes (when the baseline store includes them).

``--with-bytes`` embeds the trusted bytes of every file under ``__bytes__``
in the manifest, enabling byte-exact restore WITHOUT git — this is how a
non-git directory gets full virus-style protection (tamper/delete/add).

``--scope-root`` (repeatable) restricts the baseline to the given relative
roots, so agent-guard mode can baseline ONLY the agent workspace instead of the
whole host project. The same relative roots are then passed to the daemon via
``--agent-root``.

``--snapshot NAME`` stores the manifest as ``<target>/baselines/NAME.json``
(multiple historical anchors; promote one with ``verify_trust.py promote``)
instead of overwriting the single baseline.json.

``--seal-to ANCHOR`` writes an **out-of-band trust anchor** — a tiny file
recording sha256(baseline) that must live somewhere the baseline writer
cannot casually reach (read-only mount / remote / backup). Verify it with
``verify_trust.py verify --anchor ANCHOR``.

This is the "trusted snapshot" that lets the kit self-heal against
unrecognised modifications / malicious injections.
"""

from __future__ import annotations

import argparse
import os
import sys

from healers.integrity_guard import make_baseline
from guards.trust_root import seal_file, snapshot_path

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    parser = argparse.ArgumentParser(description="create sha256 baseline")
    parser.add_argument("target", nargs="?", default=HERE,
                        help="directory to baseline (default: this kit)")
    parser.add_argument("--out", default=None,
                        help="manifest path (default <target>/baseline.json)")
    parser.add_argument("--with-bytes", action="store_true",
                        help="also embed trusted file bytes in the manifest "
                             "(enables byte-exact restore without git)")
    parser.add_argument("--scan-binaries", action="store_true",
                        help="also baseline binary artefacts (.exe/.dll/.so/...)")
    parser.add_argument("--check-metadata", action="store_true",
                        help="also record+protect file permission mode and "
                             "symlink status")
    parser.add_argument("--scope-root", action="append", default=None,
                        metavar="REL",
                        help="only baseline files under this relative root "
                             "(repeatable, e.g. --scope-root .agent)")
    parser.add_argument("--snapshot", default=None, metavar="NAME",
                        help="store as <target>/baselines/NAME.json instead of "
                             "overwriting baseline.json (historical anchors)")
    parser.add_argument("--seal-to", default=None, metavar="ANCHOR",
                        help="write an out-of-band trust anchor (sha256 of the "
                             "baseline) to ANCHOR — keep it on read-only/remote "
                             "storage; verify with verify_trust.py verify")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        print(f"错误：目录不存在 {target}")
        return 2

    scope_roots = list(args.scope_root or [])
    for rel in scope_roots:
        if not os.path.isdir(os.path.join(target, rel.strip().strip("/"))):
            print(f"警告：scope root 不是目录（可能为空基线）：{rel}")

    out_path = args.out
    if args.snapshot and not out_path:
        out_path = snapshot_path(target, args.snapshot)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

    manifest = make_baseline(target, manifest_path=out_path,
                             with_bytes=args.with_bytes,
                             scan_binaries=args.scan_binaries,
                             check_metadata=args.check_metadata,
                             scope_roots=scope_roots or None)
    n_files = sum(1 for k in manifest if not k.startswith("__"))
    flags = []
    if args.with_bytes:
        flags.append("embedded bytes")
    if args.scan_binaries:
        flags.append("+binaries")
    if args.check_metadata:
        flags.append("+metadata")
    if scope_roots:
        flags.append("scope=" + ",".join(scope_roots))
    if args.snapshot:
        flags.append("snapshot=" + args.snapshot)
    flags_str = (" (" + ", ".join(flags) + ", hash-sealed)"
                 if flags else " (hash-sealed)")
    print(f"baseline written: {n_files} files" + flags_str)
    if n_files == 0:
        print("警告：基线为空——检查 --scope-root 是否指向真实目录")

    if args.seal_to:
        anchor = os.path.abspath(args.seal_to)
        rec = seal_file(out_path or os.path.join(target, "baseline.json"),
                        anchor)
        print(f"trust anchor written: {anchor} "
              f"(sha256={rec['sha256'][:12]}…)")
        print("提示：把锚点文件放到只读介质/远端/备份——它的价值就在于"
              "与 baseline 不在同一处可写位置")
    return 0


if __name__ == "__main__":
    sys.exit(main())
