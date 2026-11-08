# 示例：CI 构建产物防篡改

一个可在 10 秒内复现、可直接接进流水线的真实场景：

> 构建产物在「构建完成」到「发布」之间被改了、被删了、被塞了新文件 ——
> 用可信基线检出、字节级恢复，并把新增文件可逆隔离。

这是本仓库第一个面向**真实采用**的示例，不是又一个文档。目标用户是
「有 CI、有产物、担心产物在流水线中途被替换」的团队。

## 一键复现

在仓库根目录执行（Python 3.8+，仅标准库）：

```bash
python examples/ci-artifact-guard/ci_artifact_guard.py --demo
```

它会：生成三个可信产物（含二进制 `app.exe`）→ 用 `make_baseline.py --with-bytes --scan-binaries` 封印 →
注入四类偏离（篡改 `bundle.py`、篡改 `app.exe`、删除 `SHA256SUMS.txt`、投放 `evil.txt`）
→ 打印检测到的四类故障 → 调用 H7-only 引擎自愈 → 逐项验证字节一致、
删除文件重建、二进制字节级恢复、新增文件被隔离到 `.quarantine/`。

预期结尾：

```
      OK  bundle.py byte-exact restored
      OK  SHA256SUMS.txt byte-exact restored
      OK  app.exe byte-exact restored
      OK  evil.txt quarantined (reversible)
      OK  no remaining deviations
RESULT: PASS
```

退出码 `0` = 全部通过，`1` = 有环节失败（可直接作为 CI 门禁）。

## 接进真实流水线

```yaml
# 复制到你自己的 .github/workflows/ 即可，不含任何模板表达式
name: guard build artifacts
on: [push]
jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Build
        run: python build.py --out dist/
      - name: Seal trusted artifacts (trusted step, right after build)
        run: python make_baseline.py dist/ --with-bytes --scan-binaries
      - name: Verify before publish
        run: python examples/ci-artifact-guard/ci_artifact_guard.py --target dist/ --scan-binaries
```

`--target` 默认会**修复**偏离并继续；只想告警、让流水线红灯，用
`--no-repair`（有偏离即退出 1）。两种模式都要求目标目录里已有
`baseline.json`，否则退出 2 并提示生成命令。

**二进制产物**（Windows 安装器 `.exe`、Linux 共享库 `.so`、Docker layer 等）请在
`make_baseline.py` 与 `ci_artifact_guard.py` 两处**同时**加上 `--scan-binaries`，
否则二进制文件会被默认白名单跳过、不纳入完整性保护。

把 `baseline.json` 连同 `verify_trust.py seal` 的带外锚点一起存到
流水线之外的只读位置，可信度会更高 —— 只在产物目录内部留基线，
能同时改产物和基线的攻击者依然可以绕过。

## 两个容易踩的坑（示例里已经处理）

1. **把 `--target` 指向产物目录本身**（如 `dist/`），**不要**指向仓库根。
   内置白名单把 `dist/` 视为已知易变目录，从仓库根扫描时，该目录下
   新增的文件会被当成正常构建产物忽略。
2. **只挂 H7**。构建产物是不透明字节，若沿用 `self_heal.py --target`
   默认的全套 healer，H1–H6 的格式修复会去「修正」合法产物。
   本示例用 `SelfHealEngine(healers=[IntegrityGuardHealer(...)])`
   精确限定为完整性守护。二进制产物还需给 `make_baseline.py` 加
   `--scan-binaries`。

## 诚实边界

- 它验证的是**文件字节与可信基线一致**，不是杀毒、不查内存注入、
  不证明产物逻辑正确，也不覆盖基线未收录的文件类型。
- 基线必须在**可信时刻**（构建刚完成、发布之前）生成；生成之后才被
  篡改的攻击者若能重写基线，属于 `THREAT_MODEL.md` 声明的盲区。
- 完整威胁模型见仓库根目录 `THREAT_MODEL.md`，私下漏洞报告见
  `SECURITY.md`。
