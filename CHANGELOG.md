# Changelog

All notable changes to self_heal_kit. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-11-07

首个对外发布版本。核心叙事：**AI Agent 防篡改自保护底座**——
作用域守护 → 前置闸门 → 事后自愈 → 带外信任根 → 四幕演示。

### Licensing（首次公开上传前的许可调整）

- **由「未发布的 MIT 草案」改为 GPLv3-or-later / 商业双许可**：
  SPDX `GPL-3.0-or-later OR LicenseRef-Commercial`。调整发生在**首次公开上传
  之前**，MIT 授权从未对任何第三方生效，不存在需要撤回的既得授权；首个
  对外版本即为双许可。
- 新增 `LICENSE`（双许可主声明）、`LICENSE-GPL-3.0.txt`（GPLv3 官方全文）、
  `LICENSE-COMMERCIAL.md`（商业许可说明：非合同、不承诺任何价格或条款）、
  `NOTICE`（版权与来源）、`CLA.md`（贡献者「可再许可」授权 —— 双许可成立的
  法律前提）、`CONTRIBUTING.md`（贡献流程 + H7 自举铁律）。
- README 首屏补 License 行、目录结构补齐许可文件，新增「九、许可与商业化」
  章节（二选一对照表、SaaS 与轻量 CLA 的诚实边界）。
- 保持版本号 `1.0.0` 不变：v1.0.0 尚未对外发布，本次属于发布前的许可定稿，
  不产生「1.0.0 曾是 MIT」的公开版本。

### Engineering readiness（发布前的对外可信度补齐）

- **`SECURITY.md`**：漏洞私下披露渠道、报告范围（明确区分
  `THREAT_MODEL.md` 已声明的盲区与真正的绕过）、不承诺 SLA 的响应方式 ——
  安全类工具不再没有上报入口。
- **CI**（`.github/workflows/ci.yml`）：Python 3.8 / 3.11 / 3.13 matrix，
  字节编译 + `pytest tests/ -q` + H7 幂等自检；四幕演练因依赖本地 git 身份
  与嵌套仓库，保留为发版前人工项（已在工作流中注明原因）。
- **可安装**（`pyproject.toml`）：`pip install -e .`、6 个 `console_scripts`
  入口、`testpaths = ["tests"]`（根治 `work/` 演练副本被递归收集导致的
  import 冲突）；刻意不填 `license` 字段，避免打包工具把双许可中的
  `LicenseRef-Commercial` 误判为非法 SPDX。
- **版本单一事实来源**（`version.py`）：`__version__ = "1.0.0"` 供打包动态
  读取，并与 README 的 `Version:` 声明及 H6 契约对齐。
- **发布包瘦身**：`.gitattributes` 用 `export-ignore` 排除 `analysis/`
  内部评估材料；`commercialization_report.md` 因已被 H7 基线记录，排除后
  会在解压自愈时被从嵌入字节重建，故保留（属性文件里已注明原因）。
- **H7 配套修复**（`healers/base.py` + `healers/integrity_guard.py`）：新增
  `_is_skipped_dir()`，让 `*.egg-info/` / `*.dist-info/` 这类随发行名变化的
  构建产物既不进基线、也不被严格模式判为「恶意新增文件」；白名单的目录
  匹配改用 `fnmatch`（对原有精确目录名行为完全不变）。否则用户照
  `pip install -e .` 装一次，`--self` 就会把自己的构建产物隔离掉。
- **H2 误伤 CI 工作流**（四幕演练逼出）：`.github/workflows/ci.yml` 的
  `${{ matrix.python-version }}` 是合法的 GitHub Actions 表达式，却被
  `brace_escape` 判为花括号转义泄漏，令第二幕 `FAILED_CLOSED`；现按目录
  组件跳过 `.github/`（与此前 `agent_guard.py` 的自排除同一思路）。
- README 增「环境要求与安装」段与 6 个 CLI 入口、目录结构补齐、测试命令
  统一为 `pytest -q`；`CONTRIBUTING.md` 同步。

### Added

- **H7 完整性守护**（`healers/integrity_guard.py`）：以 `baseline.json`
  （或 git HEAD）为可信基线，sha256 字节比对检测**篡改 / 删除 / 新增**三类
  偏离并修复（字节级恢复 / 重建 / 隔离到 `.quarantine/`，可逆不硬删）。
- **基线封印**（`__seal__`）：`baseline.json` 自带哈希封印，改动基线本身即暴露。
- **严格模式 + 白名单**：默认检测"新增文件"；内置 `*.log` / `dist/` /
  `node_modules/` 等安全产物白名单防误报；目录白名单按任意层级匹配。
- **Unicode 基线支持**：`git ls-tree` 用 `core.quotepath=false` + UTF-8 解码，
  非 ASCII 文件名不再被静默排除出 git 基线。
- **二进制完整性**（可选 `--scan-binaries`）：`.exe/.dll/.so` 等纳入基线。
- **元数据完整性**（可选 `--check-metadata`）：权限位（mode）与符号链接替换
  的检测与自动还原。
- **守护进程**（`self_heal_watch.py`）：`--once`（cron）/ `--interval`（长驻）
  / `--no-repair`（仅告警）/ `--verify-cmd`（修复后验收命令）。
- **Agent 工作区作用域守护**：`--agent-guard` + 可重复 `--agent-root`，只守护
  指定相对根目录，宿主项目其余部分零误报；配套 `make_baseline --scope-root`。
  未给根目录直接报错（fail-safe，不退化为守护整棵树）。
- **前置闸门**（`agent_guard.py`）：
  - `check`：作用域字节校验；`--file` 单文件写入授权（路径策略）；
  - `run`：先校验再执行，工作区偏离基线时命令**不被运行**；
  - `install-hook` / `uninstall-hook`：git pre-commit 钩子（幂等；拒绝覆盖
    或删除非本工具安装的钩子，exit 4）。
  - 退出码约定：`0` 允许/干净 · `1` 阻断/偏离 · `2` 用法错误 · `4` 拒绝。
- **带外信任根锚点**（`guards/trust_root.py` + `verify_trust.py`）：
  - `seal`：`sha256(baseline.json)` 记录到带外位置（只读挂载/远端/备份）；
  - `verify`：基线与锚点比对，失配即 `TRUST ANCHOR BROKEN`；
  - 守护进程 `--trust-anchor`：锚点失配 → `TRUST_BROKEN`，**拒绝从可疑基线
    修复**（fail-closed，防止把后门固化进基线），exit 3。
- **基线多版本快照**：`make_baseline --snapshot NAME` → `baselines/NAME.json`；
  `verify_trust list` / `promote [--anchor]` 支持历史回滚与重封印。
- **自举硬化**：`self_heal.py --self` 默认只用 H7（恢复受信基线），不再用
  H1–H6 格式修复改写自身合法代码；`--with-format-healers` 可选恢复旧行为。
- **四幕演练**（`self_heal_demo.py`，rc=0 全 PASS）：
  SELF-HEAL / H7 INTEGRITY（逻辑注入恢复）/ H7 VIRUS（篡改·删除·新增三合一）/
  AGENT GUARD（写入策略 → 闸门拦截 → 恢复 → 高级重封印攻击被锚点识破 → 恢复）。
- **威胁模型**（`THREAT_MODEL.md`）：能防/防不住/信任假设/STRIDE 攻击场景/
  部署建议——含协作式闸门与哈希级（非密钥级）信任根的诚实边界。
- **回归测试**：42 条 pytest（git 边界信任混用、嵌套白名单、信任根 fail-closed、
  闸门拒绝执行等均有锁定）。

### Fixed

- `_baseline_bytes` 收敛 bug：副本位于 git 仓库内时误用外层 HEAD 字节，
  导致修复不收敛——现在磁盘基线优先于 git HEAD。
- `_find_target_root` 上溯穿过嵌套 git 仓库边界抓到**外层项目**的
  `baseline.json`（信任混用）——遇 `.git` 边界即停；`repair` 优先用
  `detect()` 记录的目标目录。
- 严格模式白名单只在顶层匹配（`tests/.pytest_cache` 被判"新增文件"导致
  `--self` 非幂等）——目录白名单改为任意层级组件匹配。
- `self_heal_watch.py` 长驻循环引用未定义属性（首轮即 AttributeError 崩溃）。
- `self_heal_watch.py --once` 漏传 `--trust-anchor`（cron 用户反而没有信任根
  保护）。
- `agent_guard.py` argparse 子命令 `dest="cmd"` 被 `run` 位置参数覆盖。
- 注入式基线（库用法 `IntegrityGuardHealer(baseline={...})`）只能检测、不能
  修复——`repair()` 现在回退到 `detect()` 的目标目录。
- `_TEXT_EXTS` 扩展至 18 种（补 `.sh .bat .cmd .ps1 .env .xml .html .css`）。
- 演练副本不再泄漏 kit 自身 `baseline.json`（避免 bogus missing-baseline）。
- H2 花括号误伤 `agent_guard.py` 的合法 f-string `{{ }}` shell 模板（自排除）。

### Known limits (honest)

- 信任根为**哈希级**，非密钥级：攻击者同时可写锚点位置时链条可被重封
  （防护强度 = 锚点位置的可写难度）。Ed25519 密钥级签名属后续增强。
- 前置闸门是**协作式**的：管得住调用它的工作流，管不住不问它的进程
  （需要内核/EDR 级拦截）。
- 不查内存注入、无病毒库、不证明代码逻辑正确——详见 `THREAT_MODEL.md`。
- 轻量 CLA 无签署存档：贡献以「提交 PR 即同意」生效，适合早期项目；若未来
  接受企业贡献或签署正式商业合同，建议升级 ICLA / CCLA 并归档签署记录。
- 无扩展名的 `LICENSE` / `NOTICE` 不在 `baseline.json` 的 H7 扫描范围内，
  依赖 git 版本历史与带外信任锚点保护。
