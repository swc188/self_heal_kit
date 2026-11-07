"""Self-heal daemon / watcher — unattended integrity guard.

This is the "runs forever and watches" companion to the one-shot
``self_heal.py`` entry point. It periodically scans a target directory with the
integrity guard (H7) and, when a deviation from the trusted baseline is found,
repairs it — no human in the loop.

Design choices (and why):

  * By DEFAULT it uses ONLY the integrity guard (H7), not the format healers
    (H1-H6). Reasoning: a format healer could "correct" a file that merely
    uses a different-but-valid style, which is wrong for a foreign project under
    watch. The integrity guard is the only one whose "correct" answer is a
    non-negotiable baseline snapshot. Use ``--with-format-healers`` to also run
    H1-H6 if you trust them on the target.
  * ``--once`` runs a single scan+repair pass and exits — this is what you wire
    to a cron job / Task Scheduler / systemd timer for a "pull" model instead of
    a long-lived process.
  * ``--no-repair`` switches to monitor-only: it reports and logs deviations but
    never touches the files (alerting / SIEM feed use case).
  * ``--verify-cmd`` optionally runs a test command after repair as the final
    "healed" proof (same contract as the engine: exit 0 == healed).

Usage:
    python self_heal_watch.py --self --once
    python self_heal_watch.py --target /opt/myapp --interval 300 --log watch.log
    python self_heal_watch.py --target /opt/myapp --no-repair   # alert only
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_healers(strict: bool, scan_binaries: bool, check_metadata: bool,
                   with_format: bool):
    from healers.integrity_guard import (
        IntegrityGuardHealer, DEFAULT_NEW_FILE_WHITELIST)
    from healers.line_ending import LineEndingHealer
    from healers.brace_escape import BraceEscapeHealer
    from healers.yaml_format import YamlFormatHealer
    from healers.quote_balance import QuoteBalanceHealer
    from healers.key_map_gap import KeyMapGapHealer
    from healers.decl_impl import DeclImplHealer

    healers = [
        IntegrityGuardHealer(
            detect_new_files=strict,
            new_file_whitelist=DEFAULT_NEW_FILE_WHITELIST,
            scan_binaries=scan_binaries,
            check_metadata=check_metadata),
    ]
    if with_format:
        healers += [
            LineEndingHealer(), BraceEscapeHealer(), YamlFormatHealer(),
            QuoteBalanceHealer(), KeyMapGapHealer(), DeclImplHealer(),
        ]
    return healers


def heal_once(target: str, strict: bool, scan_binaries: bool,
             check_metadata: bool, with_format: bool, no_repair: bool,
             verify_cmd) -> dict:
    from engine import SelfHealEngine

    healers = _build_healers(strict, scan_binaries, check_metadata, with_format)
    eng = SelfHealEngine(healers=healers, test_command=verify_cmd)

    if no_repair:
        faults = eng.detect_all(target)
        return {"status": "CLEAN" if not faults else "ALERT",
                "faults": faults, "rounds": 0}

    res = eng.run(target)
    return res


def _fmt_faults(faults) -> str:
    lines = []
    for f in faults:
        lines.append(f"    [{f.healer}] {f.path}\n        {f.description}")
    return "\n".join(lines)


def run_loop(target, args):
    log = args.log
    stop = False

    def emit(msg: str):
        line = f"{_ts()} {msg}"
        print(line)
        if log:
            try:
                with open(log, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except Exception:
                pass

    emit(f"WATCH START target={target} interval={args.interval}s "
         f"strict={args.strict} scan_binaries={args.scan_binaries} "
         f"check_metadata={args.check_metadata} "
         f"with_format={args.with_format} no_repair={args.no_repair}")

    while not stop:
        try:
            res = heal_once(target, args.strict, args.scan_binaries,
                           args.check_metadata, args.with_format,
                           args.no_repair, args.verify_cmd)
        except KeyboardInterrupt:
            emit("WATCH STOP (keyboard interrupt)")
            break
        except Exception as e:  # pragma: no cover - defensive
            emit(f"WATCH ERROR: {e}")
            time.sleep(args.interval)
            continue

        if res["status"] in ("CLEAN",):
            emit("CLEAN — no deviation")
        elif res["status"] == "ALERT":
            emit(f"ALERT — {len(res['faults'])} deviation(s):\n"
                 + _fmt_faults(res["faults"]))
        elif res["status"] == "HEALED":
            emit(f"HEALED — rounds={res.get('rounds')} "
                 f"verify={res.get('verify')}")
        else:
            emit(f"FAILED_CLOSED — {res.get('reason')}")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            emit("WATCH STOP (keyboard interrupt)")
            break


def main(argv=None):
    parser = argparse.ArgumentParser(description="self_heal_kit 守护进程/监控")
    parser.add_argument("--self", action="store_true",
                        help="对自身目录运行（与 --target 二选一）")
    parser.add_argument("--target", default=None, help="目标目录")
    parser.add_argument("--interval", type=int, default=60,
                        help="轮询间隔秒数（默认 60）")
    parser.add_argument("--once", action="store_true",
                        help="只跑一次扫描+修复后退出（适合 cron/计划任务）")
    parser.add_argument("--no-repair", action="store_true",
                        help="仅监控告警，不自动修复")
    parser.add_argument("--no-strict", action="store_true",
                        help="关闭严格模式（不检测'新增文件'）")
    parser.add_argument("--scan-binaries", action="store_true",
                        help="一并保护二进制文件（.exe/.dll/.so/...）")
    parser.add_argument("--check-metadata", action="store_true",
                        help="检测/还原权限位与符号链接替换")
    parser.add_argument("--with-format-healers", action="store_true",
                        help="除 H7 外也运行 H1-H6 格式修复（需信任目标项目）")
    parser.add_argument("--verify-cmd", default=None,
                        help="修复后运行的验收命令（exit 0 == 已修复）")
    parser.add_argument("--log", default=None, help="日志文件路径")
    args = parser.parse_args(argv)

    if args.self:
        target = HERE
    elif args.target:
        target = os.path.abspath(args.target)
    else:
        parser.error("必须指定 --self 或 --target")

    if not os.path.isdir(target):
        print(f"错误：目录不存在 {target}")
        return 2

    strict = not args.no_strict

    if args.once:
        res = heal_once(target, strict, args.scan_binaries,
                        args.check_metadata, args.with_format_healers,
                        args.no_repair, args.verify_cmd)
        if res["status"] == "CLEAN":
            print(f"[{_ts()}] CLEAN — no deviation")
            return 0
        if res["status"] == "ALERT":
            print(f"[{_ts()}] ALERT — {len(res['faults'])} deviation(s):")
            print(_fmt_faults(res["faults"]))
            return 1
        print(f"[{_ts()}] {res['status']} rounds={res.get('rounds')} "
              f"verify={res.get('verify')} reason={res.get('reason')}")
        return 0 if res["status"] == "HEALED" else 1

    run_loop(target, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
