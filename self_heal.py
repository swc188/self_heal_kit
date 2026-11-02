"""Self-heal entry point: the kit heals ITSELF.

Run:
    python self_heal.py --self            # 对自身目录运行引擎（默认 test_command=pytest -q）
    python self_heal.py --self --no-test  # 只修文件，不跑 pytest
    python self_heal.py --target <dir>    # 对任意目录运行引擎（可选 --test-command）

When --self is used, the engine's verify gate is wired to the kit's own pytest
suite: a repair only counts as HEALED if (a) no healer reports a remaining
fault AND (b) `pytest -q` exits 0. This is the kit healing itself with its own
completion promise (exit 0 == healed).
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _build_engine(test_command=None):
    from engine import SelfHealEngine
    return SelfHealEngine(test_command=test_command)


def self_heal(target, run_tests=True, test_command=None):
    from engine import SelfHealEngine

    if test_command is None and run_tests:
        # 用本程序自己的 pytest 作为验收（修完必须 14 全绿）。
        # 限定 tests/ 目录：根目录下 work/ 中的演练副本包含同名测试模块，
        # 若对整个根目录跑 pytest 会触发 import 冲突（exit 2），
        # 那不属于可自愈的格式故障，因此只收集主测试套件。
        test_command = [sys.executable, "-m", "pytest", "-q", "tests/"]
    eng = SelfHealEngine(test_command=test_command)
    res = eng.run(target)
    return res


def main(argv=None):
    parser = argparse.ArgumentParser(description="self_heal_kit 自愈入口")
    parser.add_argument("--self", action="store_true", help="对自身目录运行引擎")
    parser.add_argument("--target", default=None, help="目标目录（与 --self 二选一）")
    parser.add_argument("--no-test", action="store_true", help="不跑测试（只修文件）")
    parser.add_argument("--test-command", default=None, help="自定义验收命令")
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

    print("=" * 70)
    print(f"SELF-HEAL — target: {target}")
    print(f"           mode: {'--self (heal the kit itself)' if args.self else '--target (external)'}")
    print("=" * 70)

    res = self_heal(target, run_tests=not args.no_test,
                    test_command=args.test_command)
    print(f"\nRESULT: {res['status']}")
    if res["status"] == "HEALED":
        print(f"  rounds: {res['rounds']}")
        print(f"  verify: {res.get('verify', '')}")
    else:
        print(f"  reason: {res.get('reason')}")
        for line in res.get("log", [])[-5:]:
            print("   ", line)
    return 0 if res["status"] == "HEALED" else 1


if __name__ == "__main__":
    sys.exit(main())