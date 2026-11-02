"""Create a trusted sha256 baseline for a directory.

Usage:
    python make_baseline.py <target_dir> [--out manifest.json]

Writes ``<target_dir>/baseline.json`` by default — a manifest of
{relative_path: sha256} for every in-scope text/source file. Once the baseline
exists, IntegrityGuardHealer treats ANY deviation from it as a fault and can
restore the original bytes (when the baseline store includes them).

This is the "trusted snapshot" that lets the kit self-heal against
unrecognised modifications / malicious injections.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from healers.integrity_guard import make_baseline

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
    args = parser.parse_args(argv)

    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        print(f"错误：目录不存在 {target}")
        return 2

    manifest = make_baseline(target, manifest_path=args.out)
    if args.with_bytes:
        # Embed the trusted bytes so repair does not need git.
        store = {}
        for rel in manifest:
            p = os.path.join(target, rel)
            try:
                with open(p, "rb") as fh:
                    store[rel] = fh.read().hex()
            except Exception:
                continue
        manifest_path = args.out or os.path.join(target, "baseline.json")
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"__bytes__": store, **manifest}, fh, indent=2,
                      sort_keys=True)
            fh.write("\n")

    print(f"baseline written: {len(manifest)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())