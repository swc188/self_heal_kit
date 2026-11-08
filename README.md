# self_heal_kit — AI Agent 防篡改自保护底座

[![CI](https://github.com/swc188/self_heal_kit/actions/workflows/ci.yml/badge.svg)](https://github.com/swc188/self_heal_kit/actions/workflows/ci.yml)

Version: 1.0.0
License: GPL-3.0-or-later OR LicenseRef-Commercial（双许可，见第九节）

一个**独立、零依赖**的文件完整性自愈与防篡改底座：给目标目录拍一张可信基线快照，
之后任何文件只要跟快照不一样——**事前拦得住、事后修得回、连基线被改也识破**。

四层防线，从入口到信任根逐层收紧：

| 层 | 能力 | 入口 |
|---|------|------|
| ① 前置闸门 | 写入/提交/执行**前**拦截越权与篡改 | `agent_guard.py` |
| ② 作用域守护 | 只守 `--agent-root` 指定的工作区，宿主零误报 | `self_heal_watch.py --agent-guard` |
| ③ 事后自愈 | 偏离基线 → 字节级恢复 / 重建 / 隔离（H7） | `self_heal.py` / 守护进程 |
| ④ 带外信任根 | 基线本身被改也能识破，且拒绝用可疑基线修复 | `verify_trust.py` |

> 本程序完全自包含，只用 Python 标准库（3.8+），不依赖任何其他项目或技能，也不需要任何第三方包。

---

## 30 秒看效果

```bash
python3 self_heal_demo.py     # 四幕完整演练，当前全 PASS（rc=0）
```

```
SELF-HEAL DRILL : PASS          # 自愈闭环：检测 → 修复 → pytest 验收
H7 INTEGRITY DRILL : PASS        # 语法合法的后门注入 → 字节级识别 → 恢复 → pytest 全绿
H7 VIRUS DRILL : PASS            # 篡改恢复 / 删除重建 / 新增隔离，三类感染全检出
AGENT GUARD DRILL : PASS         # 下面这条链路 ↓
```

AGENT GUARD 第四幕（主打场景）真实输出节选：

```
[2] WRITE POLICY     .agent/new.py -> ALLOW    host/app.py -> DENY（路径逃逸）
[3] GATE BLOCKS      篡改被拒：check exit 1、run 拒绝执行命令
[4] H7 REPAIR        gen.py 字节级恢复，工作区重新干净
[5] ADVANCED ATTACK  篡改+重写基线+重算内部封印 → on-disk 0 故障（封印被攻破）
                     → 带外锚点照样识破 TRUST ANCHOR BROKEN
[6] RECOVERY         恢复干净文件+重封印 → TRUST OK
AGENT GUARD DRILL : PASS
```

**适用场景**：AI Agent 工作区加固（主打）· 部署目录防篡改 FIM · CI/CD 防供应链投毒 · 完整性合规证据 · 误删误改急救。

**不是什么（诚实边界）**：不是杀毒软件（无病毒库、不扫系统）· 不查内存注入 · 不证明代码逻辑正确 · 前置闸门是协作式的（管得住问它的流程，管不住不问它的进程）。详见 `THREAT_MODEL.md`。

---

## 一、它解决什么问题

工程里高频复发的一类故障是**格式 / 字符类**问题（不是业务逻辑错误），例如：

- 行尾 CRLF 与 LF 混用、UTF-8 BOM 残留
- 模板/格式化字符串里的 `{` `}` 转义泄漏（本应输出单个 `{`，却原样落进产物）
- 文件后缀是 `.yaml` 但内容是 JSON（"假 YAML"）
- 配置/数据文件里双引号不平衡
- 别名表"已知别名但标准键为空"（展示名 ↔ 标准键 脱节）
- 文档声明的版本号与代码里的版本号漂移

这类问题**可识别、可自动化修复、可用确定性规则验收**——正是"自愈"的天然对象。

---

## 二、自愈能力模型（4 层）

| 层 | 能力 | 本程序实现 |
|---|------|-----------|
| **L1 故障域识别** | 识别高频故障形态 | 7 个 `healer`，每个负责一类确定性故障（含完整性守护） |
| **L2 闭环自愈** | detect → repair → verify，未绿则重试 | `engine.py` 的闭环循环 |
| **L3 防退化护栏** | 防假绿 / 防越修越坏 | `snapshot_rollback`（修复前快照，回归即回退）+ `verify_gate`（全绿硬闸门） |
| **L4 收敛边界** | 不无限自旋、fail-closed 升级人工 | `circuit_breaker`（无进展 / 重复故障集 → 熔断） |

**核心定理**：自愈 ≠ AGI 自我改写，而是把"失败当数据 + 确定性验收闸门 + 可回退 / 可熔断"制度化。

---

## 三、内置 7 个 Healer（L1 故障域）

| # | 名称 | 文件 | 故障域 | 修复动作 |
|---|------|------|--------|----------|
| H1 | 行尾归一 | `healers/line_ending.py` | CRLF / BOM | CRLF → LF，去除 UTF-8 BOM |
| H2 | 花括号转义 | `healers/brace_escape.py` | `{{ }}` 泄漏、未配对 `{ }` | 折叠多余转义、补配对 |
| H3 | 假 YAML | `healers/yaml_format.py` | `.yaml` 里藏 JSON | 重写为真 YAML |
| H4 | 引号配对 | `healers/quote_balance.py` | 双引号不平衡 | 补 `"` 配对 |
| H5 | 键映射缺口 | `healers/key_map_gap.py` | 别名表标准键为空 | 按内置别名表补标准键 |
| H6 | 声明↔实现 | `healers/decl_impl.py` | README 版本 ≠ 代码版本 | 以 README 为准对齐 `__version__` |
| H7 | 完整性守护 | `healers/integrity_guard.py` | 文件字节偏离可信基线（含逻辑注入） | 从基线恢复原始字节；严格模式默认开+白名单防误报；基线哈希封印防自身被篡改 |

---

## 四、4 道护栏

| 护栏 | 文件 | 作用 |
|------|------|------|
| 快照回滚 | `guards/snapshot_rollback.py` | 每个修复前快照；修复后若故障仍在，则回退到快照（防"越修越坏"） |
| 全绿闸门 | `guards/verify_gate.py` | 验收硬闸门；可选 `test_command` 委托真实测试套件（exit 0 == healed） |
| 语义熔断 | `guards/circuit_breaker.py` | 连续无进展 / 重复故障集 → 熔断，fail-closed 升级人工（防无限自旋、防假绿） |
| 收敛边界 | `engine.py` 的 `max_rounds` | 超过最大轮次仍未绿 → 升级人工 |

---

## 五、目录结构

```
self_heal_kit/
├── engine.py              # 编排器：detect→repair→verify 闭环 + 4 道护栏
├── healers/
│   ├── base.py            # Healer 接口（detect / repair / Fault / RepairResult）
│   ├── line_ending.py     # H1
│   ├── brace_escape.py    # H2
│   ├── yaml_format.py     # H3
│   ├── quote_balance.py   # H4
│   ├── key_map_gap.py     # H5
│   ├── decl_impl.py       # H6
│   └── integrity_guard.py # H7 完整性守护（字节基线+封印+严格模式）
├── guards/
│   ├── circuit_breaker.py # L4 熔断
│   ├── snapshot_rollback.py # L3 快照回滚
│   ├── verify_gate.py     # L3 全绿闸门（+ test_command 钩子）
│   ├── write_guard.py     # 前置策略：写入授权 + 作用域字节校验（供 agent_guard 调用）
│   └── trust_root.py      # 带外信任根锚点 + 基线快照（seal/verify/promote 底层）
├── fixtures/              # 故意损坏样本（由 make_fixtures.py 生成）
├── make_fixtures.py       # 生成损坏样本
├── make_baseline.py       # 生成 H7 可信基线（sha256 清单，支持 --with-bytes/--scan-binaries/--check-metadata/--scope-root）
├── self_heal.py           # 自愈入口（--self 自举 / --target 外部）
├── self_heal_watch.py     # 守护进程（--once / --interval / --no-repair / --agent-guard Agent 工作区）
├── agent_guard.py         # 前置闸门（check 写入授权/校验 · run 先校验再执行 · install-hook git 钩子）
├── self_heal_demo.py      # 四幕演练：SELF-HEAL / H7 INTEGRITY / H7 VIRUS / AGENT GUARD
├── verify_trust.py        # 带外信任根锚点 + 基线快照管理（seal / verify / list / promote）
├── THREAT_MODEL.md        # 威胁模型（能力边界与安全假设）
├── LICENSE                # 双许可主声明（GPLv3+ / 商业，二选一）
├── LICENSE-GPL-3.0.txt    # GPLv3 官方全文（社区版）
├── LICENSE-COMMERCIAL.md  # 商业许可说明（非合同）
├── NOTICE                 # 版权与来源归属声明
├── CLA.md                 # 贡献者许可协议（双许可的法律前提）
├── CONTRIBUTING.md        # 贡献指南 + 自举铁律
├── CHANGELOG.md           # 版本变更记录
├── SECURITY.md            # 漏洞私下披露政策与响应方式
├── pyproject.toml         # 可安装元数据 + 6 个 CLI 入口 + pytest 收集范围
├── version.py             # __version__ 单一事实来源（H6 契约 / 打包共用）
├── .github/workflows/ci.yml  # CI：3 个 Python 版本 × 42 条回归 + H7 自检
├── tests/                 # pytest 回归（42 条）
├── .gitignore
└── .gitattributes         # 强制仓库 LF + 发布包排除内部评估材料
```

---

## 六、环境要求与安装

- **Python 3.8+**（仅用标准库：`os / io / csv / tempfile / subprocess / re` 等）
- **运行时零第三方依赖**：clone 仓库或解压发布包后直接跑脚本即可，无需安装
- 已自带 `.venv/` 隔离环境（可选）：在本目录内 `python3 -m venv .venv` 创建，运行用 `.venv/Scripts/python`

**可选安装**（要把本工具当库 `import`，或使用命令行入口时）：

```bash
python -m pip install -e .        # 开发模式安装；不引入任何运行时依赖
python -m pytest -q               # 期望：42 passed
python self_heal_demo.py          # 期望：四幕全 PASS，rc=0
```

安装后可用 6 个入口：`self-heal`、`self-heal-watch`、`self-heal-guard`、
`self-heal-baseline`、`self-heal-trust`、`self-heal-demo`（等价于直接
`python <脚本>.py`）。不安装也不影响本文档里的任何示例。

> 版本以 `README.md` 的 `Version:` 声明为准；`version.py` 的 `__version__`
> 是打包时的动态版本来源，H6 会负责把它对齐到 README 声明。

---

## 七、使用方法

### 1. 生成「故意损坏」样本（仅用于演示/测试）
```bash
cd self_heal_kit
python3 make_fixtures.py
```

### 2. 跑自愈演示（最直观）
```bash
python3 self_test.py
```
输出三段式：**修复前 → 逐轮日志 → 修复后**，含三个场景：
- **场景 A**：H1–H6 六类损坏样本 → `HEALED`（1 轮干净自愈）
- **场景 B**：不可修故障 → `FAILED_CLOSED`（熔断升级，不无限自旋、不假绿）
- **场景 C**：演示 `verify_gate` 的 `test_command` 钩子可用性（用合成命令，不接任何项目）

### 3. 跑回归测试
```bash
python3 -m pytest -q            # 期望：42 passed
```
`pyproject.toml` 已设 `testpaths = ["tests"]`，不会误收 `work/` 演练副本。

### 4. 守护进程 / 无人值守监控（阶段1 新增）

`self_heal_watch.py` 是 `self_heal.py` 的"常驻版"：周期性对目标目录做完整性体检，发现偏离基线就自动修复。

```bash
# 对自身目录单次体检+修复（适合接 cron / 计划任务 / systemd timer）
python3 self_heal_watch.py --self --once

# 常驻轮询：每 300 秒体检一次，日志写入 watch.log
python3 self_heal_watch.py --target /opt/myapp --interval 300 --log watch.log

# 仅监控告警、不自动修复（先观察有无误报）
python3 self_heal_watch.py --target /opt/myapp --no-repair

# 更严：一并保护二进制、检查权限/符号链接
python3 self_heal_watch.py --target /opt/myapp --scan-binaries --check-metadata

# Agent 工作区守护：只保护 .agent/ 与 generated/，宿主项目其余部分不参与检测
python3 self_heal_watch.py --target /repo --agent-guard \
    --agent-root .agent --agent-root generated --once
```

> 设计要点：守护进程**默认只用 H7 完整性守护**（不用 H1–H6 格式修复），避免把外部项目的"合法不同风格"误改。需信任目标项目时可加 `--with-format-healers`。修复后可用 `--verify-cmd` 指定验收命令（exit 0 == 已修复）。
>
> **Agent 工作区守护（`--agent-guard`）**：给 AI Agent 用时，只守护它真正写入的目录（`--agent-root`，可重复），宿主项目其余部分完全不参与检测——这是把误报压到接近零的关键。配套基线要用同一套相对根：`python3 make_baseline.py /repo --with-bytes --scope-root .agent`（空基线会告警，避免"以为保护了其实什么都没纳入"）。**fail-safe 语义**：开了 `--agent-guard` 却没给任何 `--agent-root` 会直接报错退出，绝不退化成"静默守护整棵树"。

### 5. 前置闸门 agent_guard（阶段2 新增：从"事后修复"到"事前拒绝"）
守护进程是**事后**把偏离的字节修回来；`agent_guard.py` 把校验挪到动作**前面**——写入、提交、执行之前先问一句：

```bash
# 路径策略：这个文件允许写吗？（守护区外 / .. 逃逸 / 宿主项目 → DENY exit 1）
python3 agent_guard.py check --target /repo --root .agent --file .agent/x.py

# 字节策略：守护区与基线一致吗？（偏离 exit 1）
python3 agent_guard.py check --target /repo --root .agent

# 先校验再执行：守护区偏离基线时，命令根本不会被运行
python3 agent_guard.py run --target /repo --root .agent -- pytest -q

# 装 git pre-commit 钩子：偏离基线的提交直接被拒（幂等；
# 非本工具安装的钩子拒绝覆盖/删除，exit 4）
python3 agent_guard.py install-hook --target /repo --root .agent
python3 agent_guard.py uninstall-hook --target /repo
```

退出码：`0` 允许/干净 · `1` 阻断/偏离 · `2` 用法或环境错误 · `4` 拒绝（钩子非本工具所有）。

> **诚实边界**：这是**协作式闸门**——管得住调用它的工作流（Agent shell 包装、`git commit`、CI），管不住完全不问它的进程（那需要内核/EDR 级拦截，见 `THREAT_MODEL.md`）。

### 6. 带外信任根 + 基线快照（阶段2 第3项：解决"基线本身被改"）
`baseline.json` 自带的 `__seal__` 是**内部**封印——攻击者改了基线后重算封印即可骗过它（同一块盘、同一算法）。信任链的最后一环需要攻击者必须**同时碰第二处**：

```bash
# 生成基线时顺便把 sha256(baseline) 记到带外锚点（只读挂载 / 远端 / 备份）
python3 make_baseline.py /repo --with-bytes --seal-to /mnt/ro/repo.anchor.json

# 随时校验：磁盘上的 baseline 还是锚点记录的那个吗？
python3 verify_trust.py verify --target /repo --anchor /mnt/ro/repo.anchor.json

# 多版本快照：历史信任锚不被覆盖，可回滚
python3 make_baseline.py /repo --snapshot v1
python3 make_baseline.py /repo --snapshot v2
python3 verify_trust.py list --target /repo        # -> v1 v2
python3 verify_trust.py promote --target /repo --name v1   # 回滚为当前基线
python3 verify_trust.py promote --target /repo --name v1 --anchor /mnt/ro/repo.anchor.json  # 回滚+重封印

# 守护进程挂上信任根：每轮开工先验锚，失配则拒绝修复（fail-closed）
python3 self_heal_watch.py --target /repo --trust-anchor /mnt/ro/repo.anchor.json --once
```

> **为什么锚点比内部封印强**：内部封印失配只需要攻击者改两处（文件+基线重算）；带外锚点要求攻击者在**另一个独立可写位置**再改一次。只改磁盘基线（哪怕把内部封印也重算对）→ `verify` 照样报 `TRUST ANCHOR BROKEN`，守护进程报 `TRUST_BROKEN` 并**拒绝从可疑基线修复**（用被污染的基线自愈 = 把后门固化）。
>
> **诚实边界**：这是**哈希级、非密钥级**信任根。若攻击者对锚点位置也可写，链条照样能被重封——防护强度取决于你把锚点放得多难碰（只读挂载、异地备份、另一台机器）。真正的密钥级信任根（签名验证）需要引入密钥体系，属运维决策，不在此吹。

### 7. 当作库，对任意目录体检
```python
from engine import SelfHealEngine

res = SelfHealEngine().run("/某个/目标/目录")
print(res["status"])   # "HEALED" 或 "FAILED_CLOSED"
print(res["rounds"])   # 自愈用了几轮
print(res["log"])      # 逐轮 detect→repair→verify 日志
```
默认内置 6 个 healer，自动跑闭环 + 4 道护栏。

### 8. 接入真实测试套件（按需开启，默认关闭）
```python
from engine import SelfHealEngine
from guards.verify_gate import VerifyGate

# 让「全绿」以真实测试命令为准（命令 exit 0 才算 healed）
eng = SelfHealEngine(verifier=VerifyGate(test_command=["pytest", "-q"]))
res = eng.run("/目标/目录")
```
不传 `test_command` 即**自包含模式**（无 healer 故障即绿）。

### 9. 扩展：写自己的 healer
继承 `healers/base.py` 的 `Healer`，实现三个方法：
- `detect(target) -> list[Fault]`：扫描并返回故障
- `repair(fault) -> RepairResult`：执行修复（`changed=True/False`）
- `Fault.signature()`：去重 / 回退判据（同一故障必须稳定产出同一签名）

然后 `SelfHealEngine(healers=[你的Healer()])` 即可纳入闭环。

---

## 八、设计原则与已知边界

- **确定性优先**：所有修复都靠规则 + 验收断言，不靠"猜"。
- **不伪造修复**：修不了就熔断升级人工，绝不说"全绿"。
- **可回退**：任何修复若没能消除故障，立刻回滚到修复前快照。
- **完整性守护（H7）**：以 git HEAD（或 `baseline.json`）为可信基线，任何文件字节偏离都会被检测并从基线恢复——包括**语法正确的恶意逻辑注入**（格式 healer 认不出的修改）。H7 支持四类故障的检测与修复：
  - **篡改现有文件** → 从基线字节级恢复（后门被清除）
  - **删除现有文件** → 从基线重建（自动创建父目录）
  - **新增恶意文件**（严格模式，默认开启）→ 检测并**隔离**到 `.quarantine/`（可逆，不硬删）
  - **基线自身被篡改**（哈希封印 `SEAL`）→ 报"信任锚被攻破"，并尽量从 git HEAD 恢复 `baseline.json`
- **扩展保护范围**：H7 扫描的扩展名已从 10 种扩展到 18 种，新增脚本/配置类文件 `.sh .bat .cmd .ps1 .env .xml .html .css`（二进制默认不扫，见下）。
- **二进制完整性（可选 `--scan-binaries`）**：开启后 `.exe .dll .so .bin` 等二进制也会被纳入基线并受保护——可检测并字节级恢复被替换的二进制（默认关闭，避免清单膨胀）。
- **元数据完整性（可选 `--check-metadata`）**：基线额外记录每个文件的**权限位（mode）**与**是否为符号链接**；运行时检测权限变更与"符号链接替换"，并自动还原权限（链接替换则重写原文件）。详见 `THREAT_MODEL.md`。
- **严格模式默认开 + 白名单**：默认即检测"新增文件"，但内置白名单（`*.log`、`dist/`、`node_modules/`、`.venv/` 等已知安全产物）避免把正常新增文件当病毒误报；可用 `SelfHealEngine(integrity_strict=False)` 或 `self_heal.py --no-strict` 关闭。
- **基线哈希封印（自保护）**：`make_baseline.py` 生成的 `baseline.json` 带 `__seal__` 哈希封印。若攻击者只改了目标文件又改了基线哈希来"藏"篡改，封印会失配并暴露篡改——这是防"基线被悄悄改写"的关键护栏（诚实边界见下）。
- **生成可修复基线**：`python make_baseline.py <dir> --with-bytes` 会把每个文件的**原始字节**嵌入 `baseline.json`，非 git 目录也能字节级恢复（注意：带 `--with-bytes` 会嵌入文件内容，请勿对含密钥的目录使用该选项，或把 `baseline.json` 一并纳入版本控制/隔离存储）。
- **已知边界（诚实）**：
  - 没有基线时 H7 静默（不误报）；H1–H6 只处理**格式 / 字符类**确定性故障。
  - 严格模式的"新增文件"检测依赖白名单质量，无法枚举所有合法新增文件；白名单之外的合法新增文件仍会被报（这是预期的安全偏向）。
  - **哈希封印不是根信任**：真正狡猾的攻击者若能同时改写目标文件、基线哈希和封印，仍可绕过——真正的根信任需要外部密钥/带外存储。封印防范的是"意外损坏"和"非专业篡改"。
  - 范围外：`_TEXT_EXTS`/`_SKIP_DIRS` 之外的文件（除非开 `--scan-binaries`）、运行时内存注入、**引擎本体/解释器被替换导致 H7 不运行**。文件权限/symlink 替换现已可由 `--check-metadata` 覆盖。本程序不修复业务逻辑错误、不证明算法正确性、不联网安装工具链、不是杀毒软件。
  - **Agent 工作区守护只覆盖 `--agent-root` 下的文件**：宿主项目其余部分不在本工具职责内（由宿主自己或另一次全量守护负责）；`--agent-guard` 未给任何 `--agent-root` 会直接报错退出，不会退化成"静默守护整棵树"。

---

## 九、许可与商业化（双许可）

**SPDX**：`GPL-3.0-or-later OR LicenseRef-Commercial` · 主声明见 `LICENSE`

本软件采用**二选一**的双许可：

| | 选项 A：社区版 GPLv3+ | 选项 B：商业许可 |
|---|---|---|
| 费用 | 免费 | 与版权持有人另行约定 |
| 生效方式 | 自动适用，无需申请 | **必须签署书面协议** |
| 典型场景 | 内部自用、整体按 GPLv3+ 开源的项目、研究 / 教学 | 嵌入闭源 / 专有产品分发、OEM、需要担保 / 赔偿 / SLA |
| 核心义务 | 分发衍生作品时按 GPLv3 提供对应源码、同许可证 | 按协议约定（可免除 GPLv3 源码公开义务） |
| 依据文件 | `LICENSE-GPL-3.0.txt` | `LICENSE-COMMERCIAL.md`（说明，**不是合同**） |

> **没有签商业协议 = 自动适用 GPLv3+**。社区版已获得的权利不因商业授权而收回。

**为什么做双许可**：GPLv3+ 让个人、开源项目与研究者零门槛使用，用来建立可信度
和生态；闭源集成方为「不想承担 GPLv3 义务」和「担保 / 赔偿 / SLA」付费 ——
卖的是**合规确定性与嵌入能力**，不是卖软件拷贝。这与 `commercialization_report.md`
里「不要卖软件，卖能力嵌入」的判断一致。

**授权链条（为什么可以单方再授权）**：项目没有引入任何第三方源码（仅依赖
Python 标准库），版权链条单一；外部贡献通过 `CLA.md` 授予**可再许可权**，见
`CONTRIBUTING.md`。因此未来新增许可选项不需要找回历史贡献者重新签字。

**首次发布即双许可**：本仓库此前**从未公开上传**，也从未以 MIT 或任何宽松许可
对外分发；上传前的 MIT 草案已在首次发布前替换，不存在需要撤回的既得授权。

**诚实边界**：

- GPLv3 **不**把纯网络使用（SaaS）视为分发；不向用户交付程序副本的 SaaS
  通常不触发源码提供义务。上表是一般说明，不是法律意见；拿不准请按
  「需要商业许可」处理。
- 当前 `CLA.md` 是「贡献即同意」的轻量协议，**无签署存档**；若将来接受企业
  大额贡献或签署正式商业合同，建议升级 ICLA / CCLA 并归档签署记录。
- 无扩展名的 `LICENSE` / `NOTICE` 不在 `baseline.json` 的 H7 扫描范围内，
  依赖 git 版本历史与带外信任锚点保护（见 `CONTRIBUTING.md` 第 5 节）。

**需要商业许可**：通过 GitHub 仓库所有者的私有联系渠道发起，说明主体、场景、
分发方式与所需条款；具体权利以双方签署的书面协议为准。

> `analysis/` 与 `commercialization_report.md` 是内部评估与商业化推演材料，
> 记录的是判断过程和不确定性，**不构成产品能力或商业条款的承诺**；
> `analysis/` 已从发布压缩包中排除。

