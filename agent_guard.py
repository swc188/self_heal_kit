"""agent_guard — pre-flight gate for an AI agent's workspace.

"Fix it before it happens" companion to the post-hoc healers: instead of
detecting a deviation and restoring it afterwards, the workflow asks this gate
*before* it writes, commits, or runs anything.

Subcommands:

  check           Verify the guarded roots against the trusted baseline.
                  With ``--file PATH`` it degenerates to a cheap path-policy
                  check ("is this write allowed at all?").
  run             Verify first, then exec the given command. A deviating
                  workspace is never executed.
  install-hook    Install a git ``pre-commit`` hook that runs ``check`` on the
                  guarded roots (idempotent; refuses to clobber a foreign hook
                  unless ``--force``).
  uninstall-hook  Remove the hook this tool installed (marker-checked).

Exit codes: 0 = allowed / clean, 1 = blocked / deviation, 2 = usage or
environment error, 4 = refused (a hook this tool does not own).

Usage:
    python agent_guard.py check  --target /repo --root .agent
    python agent_guard.py check  --target /repo --root .agent --file .agent/x.py
    python agent_guard.py run    --target /repo --root .agent -- pytest -q
    python agent_guard.py install-hook --target /repo --root .agent

Honest limit: a cooperative gate. It constrains workflows that call it (agent
shell wrapper, git commit, CI). It is not a kernel sandbox — see
THREAT_MODEL.md.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

HOOK_MARKER = "# managed-by: self_heal_kit agent_guard v1"

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 4


def _git(repo: str, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args],
                           capture_output=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", "replace").strip()


def _repo_root(target: str):
    return _git(target, "rev-parse", "--show-toplevel") or None


def _hooks_dir(repo: str):
    p = _git(repo, "rev-parse", "--git-path", "hooks")
    if not p:
        return None
    if not os.path.isabs(p):
        p = os.path.join(repo, p)
    return os.path.abspath(p)


def _repo_relative_roots(target: str, repo: str, roots) -> list:
    """Translate target-relative roots into repo-relative ones (hook case)."""
    out = []
    for r in roots:
        abs_root = os.path.abspath(os.path.join(target, r))
        out.append(os.path.relpath(abs_root, repo).replace("\\", "/"))
    return out


def _render_hook(python_exe: str, script: str, target: str, roots) -> str:
    root_args = " ".join('--root "%s"' % r.replace('"', '\\"') for r in roots)
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARKER}\n"
        "# Blocks a commit when the guarded workspace deviates from baseline.\n"
        f'"{python_exe}" "{script}" check --target "{target}" '
        f"{root_args} --quiet || {{\n"
        '  echo "[agent_guard] commit blocked: guarded workspace deviates '
        'from baseline" >&2\n'
        "  exit 1\n"
        "}\n"
    )


def _do_check(args) -> int:
    from guards.write_guard import authorize_write, verify_scope

    target = os.path.abspath(args.target)
    roots = list(getattr(args, "roots", None) or [])
    if not roots:
        print("error: at least one --root is required", file=sys.stderr)
        return EXIT_USAGE

    path = getattr(args, "file", None)
    if path:
        # Relative paths are interpreted relative to --target.
        if not os.path.isabs(path):
            path = os.path.join(target, path)
        ok, why = authorize_write(path, target, roots)
        if not ok:
            if not args.quiet:
                print(f"DENY — {why}")
            return EXIT_BLOCKED
        if not args.quiet:
            print("ALLOW — in scope")
        return EXIT_OK

    faults = verify_scope(target, roots, strict=not args.no_strict,
                          scan_binaries=args.scan_binaries,
                          check_metadata=args.check_metadata)
    if faults:
        if not args.quiet:
            print(f"DEVIATION — {len(faults)} fault(s):")
            for f in faults:
                print(f"  [{f.healer}] {f.path}")
                print(f"      {f.description}")
        return EXIT_BLOCKED
    if not args.quiet:
        print("CLEAN — guarded workspace matches baseline")
    return EXIT_OK


def _do_run(args) -> int:
    cmd = list(getattr(args, "cmd", None) or [])
    while cmd and cmd[0] == "--":
        cmd.pop(0)
    if not cmd:
        print("error: no command given after --", file=sys.stderr)
        return EXIT_USAGE

    rc = _do_check(args)
    if rc != EXIT_OK:
        print("[agent_guard] refusing to run: guarded workspace deviates "
              "from baseline", file=sys.stderr)
        return EXIT_BLOCKED

    try:
        return subprocess.call(cmd, cwd=os.path.abspath(args.target))
    except FileNotFoundError as e:
        print(f"error: command not found ({e})", file=sys.stderr)
        return EXIT_USAGE


def _do_install_hook(args) -> int:
    target = os.path.abspath(args.target)
    roots = list(getattr(args, "roots", None) or [])
    if not roots:
        print("error: at least one --root is required", file=sys.stderr)
        return EXIT_USAGE

    repo = _repo_root(target)
    if not repo:
        print("error: target is not inside a git worktree", file=sys.stderr)
        return EXIT_USAGE
    hooks = _hooks_dir(repo)
    if not hooks:
        print("error: cannot resolve the git hooks directory",
              file=sys.stderr)
        return EXIT_USAGE

    os.makedirs(hooks, exist_ok=True)
    hook = os.path.join(hooks, "pre-commit")
    if os.path.isfile(hook):
        try:
            with open(hook, "r", encoding="utf-8", errors="replace") as fh:
                current = fh.read()
        except Exception:
            current = ""
        if HOOK_MARKER not in current and not args.force:
            print("refusing to overwrite a pre-commit hook that agent_guard "
                  "did not install (use --force)", file=sys.stderr)
            return EXIT_REFUSED

    content = _render_hook(sys.executable, os.path.abspath(__file__),
                           repo, _repo_relative_roots(target, repo, roots))
    with open(hook, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    try:
        os.chmod(hook, 0o755)
    except Exception:
        pass
    print(f"pre-commit hook installed: {hook}")
    return EXIT_OK


def _do_uninstall_hook(args) -> int:
    repo = _repo_root(os.path.abspath(args.target))
    if not repo:
        print("error: target is not inside a git worktree", file=sys.stderr)
        return EXIT_USAGE
    hooks = _hooks_dir(repo)
    hook = os.path.join(hooks, "pre-commit") if hooks else None
    if not hook or not os.path.isfile(hook):
        print("no pre-commit hook found (nothing to do)")
        return EXIT_OK
    try:
        with open(hook, "r", encoding="utf-8", errors="replace") as fh:
            current = fh.read()
    except Exception:
        current = ""
    if HOOK_MARKER not in current:
        print("refusing to remove a pre-commit hook that agent_guard did not "
              "install", file=sys.stderr)
        return EXIT_REFUSED
    os.remove(hook)
    print(f"pre-commit hook removed: {hook}")
    return EXIT_OK


def _add_common(p):
    p.add_argument("--target", required=True, help="项目根目录")
    p.add_argument("--root", action="append", default=None, dest="roots",
                   metavar="REL",
                   help="守护的相对根目录（可重复，如 .agent）")
    p.add_argument("--no-strict", action="store_true",
                   help="关闭严格模式（不检测新增文件）")
    p.add_argument("--scan-binaries", action="store_true",
                   help="一并校验二进制文件")
    p.add_argument("--check-metadata", action="store_true",
                   help="一并校验权限位/符号链接")
    p.add_argument("--quiet", action="store_true", help="静默（仅用退出码）")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent_guard", description="Agent 工作区前置拦截（H7 前置闸门）")
    # NB: dest must not be "cmd" — the `run` subparser's positional cmd list
    # would overwrite it (REMAINDER shares the namespace).
    sub = parser.add_subparsers(dest="gate", required=True)

    p_check = sub.add_parser("check", help="校验守护区（或单文件写入授权）")
    _add_common(p_check)
    p_check.add_argument("--file", default=None,
                         help="只判断该文件是否允许写入（路径策略；"
                              "相对路径按 --target 解析）")

    p_run = sub.add_parser("run", help="先校验再执行命令（校验失败不执行）")
    _add_common(p_run)
    p_run.add_argument("cmd", nargs=argparse.REMAINDER,
                       help="-- 之后是要执行的命令")

    p_install = sub.add_parser("install-hook",
                               help="安装 git pre-commit 钩子")
    _add_common(p_install)
    p_install.add_argument("--force", action="store_true",
                           help="覆盖非本工具安装的钩子")

    p_uninstall = sub.add_parser("uninstall-hook",
                                 help="移除本工具安装的钩子")
    p_uninstall.add_argument("--target", required=True)

    args = parser.parse_args(argv)

    if args.gate == "check":
        return _do_check(args)
    if args.gate == "run":
        return _do_run(args)
    if args.gate == "install-hook":
        return _do_install_hook(args)
    if args.gate == "uninstall-hook":
        return _do_uninstall_hook(args)
    parser.error("unknown subcommand")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
