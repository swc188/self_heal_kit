# self_heal_kit — 软件自愈引擎

一个**独立、零依赖**的软件自愈引擎：对目标目录里的文件做「检测 → 修复 → 验收」闭环，
靠确定性护栏防止越修越坏、防止假绿、防止无限自旋。

> 本程序完全自包含，不依赖任何其他项目或技能，也不需要任何第三方包。

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
│   └── verify_gate.py     # L3 全绿闸门（+ test_command 钩子）
├── fixtures/              # 故意损坏样本（由 make_fixtures.py 生成）
├── make_fixtures.py       # 生成损坏样本
├── make_baseline.py       # 生成 H7 可信基线（sha256 清单，支持 --with-bytes/--scan-binaries/--check-metadata/--scope-root）
├── self_heal.py           # 自愈入口（--self 自举 / --target 外部）
├── self_heal_watch.py     # 守护进程（--once / --interval / --no-repair / --agent-guard Agent 工作区）
├── self_heal_demo.py      # 三个演练：SELF-HEAL / H7 INTEGRITY / H7 VIRUS
├── THREAT_MODEL.md        # 威胁模型（能力边界与安全假设）
├── tests/                 # pytest 回归（34 条）
├── .gitignore
└── .gitattributes         # 强制仓库 LF（避免 Windows 把源码 checkout 成 CRLF）
```

---

## 六、环境要求

- **Python 3.8+**（仅用标准库：`os / io / csv / tempfile / subprocess / re` 等）
- **零第三方依赖**，无需 `pip install`
- 已自带 `.venv/` 隔离环境（可选）：在本目录内 `python3 -m venv .venv` 创建，运行用 `.venv/Scripts/python`

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
python3 -m pytest tests/ -q     # 期望：34 passed
```

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

### 5. 当作库，对任意目录体检
```python
from engine import SelfHealEngine

res = SelfHealEngine().run("/某个/目标/目录")
print(res["status"])   # "HEALED" 或 "FAILED_CLOSED"
print(res["rounds"])   # 自愈用了几轮
print(res["log"])      # 逐轮 detect→repair→verify 日志
```
默认内置 6 个 healer，自动跑闭环 + 4 道护栏。

### 5. 接入真实测试套件（按需开启，默认关闭）
```python
from engine import SelfHealEngine
from guards.verify_gate import VerifyGate

# 让「全绿」以真实测试命令为准（命令 exit 0 才算 healed）
eng = SelfHealEngine(verifier=VerifyGate(test_command=["pytest", "-q"]))
res = eng.run("/目标/目录")
```
不传 `test_command` 即**自包含模式**（无 healer 故障即绿）。

### 6. 扩展：写自己的 healer
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
