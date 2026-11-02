# self_heal_kit 与 loop-framework-skill 自愈原理对齐分析

> 分析日期：2026-11-02
> 分析方式：只读 loop-framework-skill 源码（`loop_circuit.py` / `loop_rollback.py` / `backpressure.py` / `verify_project.py` / `maintain.py` / `second_opinion.py` / `certify.py` / `upgrade.py`），未修改其任何文件。
> 结论性质：本报告是 self_heal_kit 的**外部对齐审计**，所有产出物均在本目录内。

---

## 第一部分：loop-framework-skill 自愈能力总结归纳

### 1. 总体架构：两层嵌套 Loop

loop 的自愈不是单一功能，而是一套**纵深防御体系**，分内外两层：

- **外层 Loop**：AI-Native SDLC 八阶段闭环（Intent→Design→Plan→Build→Test→Deploy→Publish→Maintain）。
- **内层 Loop**：Ralph 自纠错循环——"默认你第一次写不对，报错是最宝贵的数据"。
  - 流程：`build.py 生成 → backpressure.py quick（快层回压）→ verify_project.py（慢层验收）→ 读失败 → 修 → 重跑`，直到 verify 退出码 0。
  - **Completion Promise 硬闸门**：没到退出码 0 之前，循环不结束。

### 2. 七道确定性自愈机制（按源码逐项归纳）

| # | 机制 | 源码 | 核心逻辑 | 防的是什么 |
|---|------|------|----------|------------|
| M1 | 两层回压 | `backpressure.py` | 快层（结构+安全静态扫描，毫秒级）每轮跑；慢层（真测试）收敛时跑。没在收集回压就是失职 | 生成函数与校验函数之间没有自动反馈 |
| M2 | 内置死循环检测 | `verify_project.py detect_dead_loop` | 不依赖 git，用**源码内容哈希 + 文件 mtime + 测试结果**判定：连续 N 轮无代码进展或 N 轮相同测试结果 → 触发熔断；测试 PASS 时计数清零（防误熔断已通过项目） | 空转/重复修同一处/测试本身死循环 |
| M3 | 语义熔断器 | `loop_circuit.py` | 连续 3 轮无进展 / 连续 5 轮相同错误 / 输出持续下降 → OPEN；**冷却-半开-恢复**：OPEN 冷却期过 → HALF_OPEN → 允许一次试运行，成功 CLOSED，失败回 OPEN 重启冷却；状态文件损坏强制 HALF_OPEN（fail-loud） | 语义死循环、偶发故障误杀 |
| M4 | 快照回滚 | `loop_rollback.py` | 每轮迭代前快照；测试通过后 mark-good（已知好状态）；熔断时回滚到最近好状态。回滚**先清除再恢复**（删除快照后新增的文件，防后门/密钥残留的假回滚） | 修崩了回不去、假回滚 |
| M5 | 验收门禁组 | `verify_project.py` | ①结构门禁（src/tests/依赖声明缺失→BLOCKER）②安全静态扫描（SQL注入/TLS关闭/XXE/JWT验签关闭/硬编码密钥→BLOCKER）③**真编译+真测试**（pytest/node test/go test/cargo test/mvn test）④**测试有效性门禁**（全绿但零断言/恒真断言=空壳→阻断）⑤测试超时强制终止（默认60s） | 空壳测试骗过门禁、半成品交付 |
| M6 | 双条件退出门 | `verify_project.py` | 退出码 0 之外的第二道条件：**需求覆盖度检查**（intent.md 验收标准逐条在源码找证据，含中文术语→英文标识符映射）+ **Promise 协议硬约束**（COMPLETE/EXIT_SIGNAL/完成指标 ≥2 项且来自 ≥2 个不同文件防刷）+ **工作证明门禁**（loop_workproof 验证 Agent 真写了代码，防只说不做） | 需求写 5 个只做 3 个就交半成品、自欺式完成声明 |
| M7 | 独立视角复核 | `second_opinion.py` + 报告封印 | 用**全新上下文**重跑验收标准→源码证据核查；报告带 `REPORT_SEAL`（绑定项目路径+源码指纹+验收标准指纹），手写伪造或报告生成后改源码都会被 verify 拒绝；UNDETERMINED 如实标注，strict 下视为 FAIL | 实现者自己的假设蒙蔽判断、伪造验收报告 |

### 3. 自身防退化机制（对 skill 体系自身）

| # | 机制 | 源码 | 说明 |
|---|------|------|------|
| M8 | 外层自动收口 | `maintain.py` | 每轮外层闭环结束前检查：intent/spec/plan 是否更新、CLAUDE.md 是否有实质内容（知识沉淀）、遗留 BLOCKER/DECIDE 标签、临时文件残留、快照新鲜度 |
| M9 | 独立认证器 | `certify.py` | 对任意代码目录发合格证（CERTIFIED/VERIFIED/FALLBACK/NOT_CERTIFIED）；VERIFIED ≠ CERTIFIED（LLM 产物无豁免权）；门禁失败翻译成 LLM 可消费的修复指令（draft_feedback） |
| M10 | 依赖自动升级器 | `upgrade.py` | apply 前备份 manifest，升级后 verify 失败立即还原（fail-closed）；网络不可达优雅降级跳过（故障封闭） |
| M11 | 生成器卫生护栏 | `TestGeneratorHygieneV3160`（测试） | tokenize 扫转义泄漏 / 产物无 `{{` / Rust 无重名 fn，锁死格式类故障域 |
| M12 | 回归护栏 | 223 条 pytest | 每次改动必须全绿，防退化 |

### 4. loop 自愈能力的本质总结

> **loop 的自愈 = 把"失败当数据 + 确定性验收闸门 + 可回退/可熔断 + 独立视角防自欺"制度化，覆盖从生成物（被交付项目）到自身（skill 体系）两个层面。**

它不是 AGI 式自我改写，而是：
- **失败当数据**：报错/测试红是最宝贵的输入（Ralph 循环）。
- **确定性闸门**：verify 退出码 0 + 需求覆盖 + Promise + 工作证明，多条件才能退。
- **可回退**：快照→已知好状态→熔断回滚。
- **可熔断**：无进展/相同错误/输出下降→OPEN→冷却→半开→恢复或停。
- **防自欺**：独立复核 + 报告封印 + 多源防刷 + 测试有效性门禁。

---

## 第二部分：self_heal_kit 与 loop 的对齐情况

### 2.1 对齐矩阵（逐项）

| loop 机制 | self_heal_kit 对应 | 对齐度 | 说明 |
|-----------|-------------------|--------|------|
| M1 两层回压（quick/full） | `healers/`（检测）+ `verify_gate test_command`（可选真测试） | ⚠️ 部分 | self_heal 无 quick/full 分级；healers 检测≈快层，test_command≈慢层，但未分层 |
| M2 死循环检测（内容哈希+mtime） | `circuit_breaker.py`（故障集签名+progress） | ✅ 原理对齐 | 都用"状态签名是否变化"判进展；loop 用文件哈希，self_heal 用故障签名 |
| M3 语义熔断（3轮/5轮/输出下降） | `circuit_breaker.py`（patience 轮无进展/重复故障集） | ✅ 核心对齐 | 触发条件对齐；**但 self_heal 无 HALF_OPEN 半开恢复**（loop 有冷却-半开-恢复） |
| M4 快照回滚（先清除再恢复） | `snapshot_rollback.py`（字节快照+回归即回退） | ⚠️ 部分 | 核心思想对齐（修复前快照、无效即回退）；但 self_heal 只回滚单文件，loop 是整目录"先清除再恢复" |
| M5 验收门禁（结构/安全/真测试/有效性） | `verify_gate.py`（无故障即绿 或 test_command exit 0） | ⚠️ 部分 | 门禁概念对齐（exit 0 == healed）；但 self_heal 无安全扫描、无测试有效性门禁（防空壳） |
| M6 双条件退出门（需求覆盖/Promise/工作证明） | 无 | ❌ 未对齐 | self_heal 不检查需求覆盖，无 Promise 协议，无工作证明 |
| M7 独立视角复核（second_opinion+封印） | 无 | ❌ 未对齐 | self_heal 无独立复核、无报告防伪封印 |
| M8 外层自动收口（maintain） | 无 | ❌ 未对齐 | self_heal 无收口检查 |
| M9 独立认证（certify 档位） | 无 | ❌ 未对齐 | self_heal 只有 HEALED/FAILED_CLOSED 二态 |
| M10 依赖升级器（备份+verify+回滚） | 无 | ❌ 未对齐 | 故障域不同 |
| M11/M12 自身护栏（卫生护栏+223回归） | `tests/`（14 pytest）+ `.gitattributes` 强制 LF | ✅ 思想对齐 | 都用回归测试锁死自身防退化；self_heal 规模小但方向一致 |

### 2.2 四层模型映射

| self_heal_kit 层 | loop 对应 | 对齐结论 |
|------------------|-----------|----------|
| **L1 故障域识别**（6 healers） | 生成器卫生护栏 + 格式/字符类修复事件 | ✅ 对齐（但故障域窄：仅格式/字符） |
| **L2 闭环自愈**（detect→repair→verify） | 内层 Ralph 循环（build→verify→修→重跑） | ✅ 对齐（骨架一致） |
| **L3 防退化护栏**（快照回滚+全绿闸门） | loop_rollback + verify 退出码 0 | ✅ 对齐（核心一致，粒度更粗） |
| **L4 收敛边界**（熔断 fail-closed） | loop_circuit 语义熔断 | ✅ 对齐（缺半开恢复） |

### 2.3 关键差异（诚实清单）

1. **故障域宽度**：loop 自愈覆盖"代码正确性"（结构/安全/测试/需求/承诺），self_heal 只覆盖"格式/字符类文件病"。
2. **半开恢复**：loop 熔断后冷却→HALF_OPEN→试运行→可恢复；self_heal 熔断即终态 FAILED_CLOSED，无恢复路径。
3. **防自欺深度**：loop 有独立复核+报告封印+多源防刷+测试有效性门禁；self_heal 依赖 verify_gate（无故障或测试命令通过），无独立复核。
4. **回滚粒度**：loop 整目录"先清除再恢复"；self_heal 单文件字节回退。
5. **验证强度**：loop 跑真编译+真测试+覆盖率；self_heal 的 test_command 是可选钩子，默认自包含模式不跑任何测试。

---

## 第三部分：结论

### 3.1 对齐结论

**核心原理对齐，能力广度未对齐。**

- **对齐的部分（骨架）**：self_heal_kit 正确复刻了 loop 自愈的**四层骨架**——故障域识别（L1）、闭环自愈（L2）、快照回滚+全绿闸门（L3）、熔断收敛（L4）。这四层与 loop 的内层 Ralph 循环、loop_rollback、verify 退出码 0、loop_circuit 一一对应。设计哲学（失败当数据、确定性验收、可回退、可熔断）完全同源。
- **未对齐的部分（血肉）**：loop 的纵深防御（独立复核、需求覆盖、Promise 防刷、工作证明、测试有效性门禁、半开恢复、整目录回滚）在 self_heal_kit 中尚未实现。

### 3.2 定位差异（为什么不需要全对齐）

self_heal_kit 的定位是**"格式/字符类文件故障的确定性自愈引擎"**，而 loop 是**"全栈代码交付的正确性闭环"**。二者目标不同：
- self_heal_kit 不需要需求覆盖/Promise/工作证明——因为它不"交付需求"，只"修复文件"。
- self_heal_kit 应该补的是：**半开恢复**（偶发故障不假死）、**独立复核**（防自己骗自己）、**测试有效性门禁**（防空壳测试）、**整目录回滚**（防修复引入新文件残留）。这些是"自愈引擎"这个定位下仍然成立的能力。

### 3.3 建议的后续对齐项（按价值排序）

1. **P0 半开恢复**：熔断后冷却→允许一次试运行→成功恢复 CLOSED，失败才终态。对齐 loop_circuit HALF_OPEN。
2. **P1 独立复核**：修复完成后用"全新上下文"重扫一遍并生成带指纹的报告，防 healer 自己骗自己。
3. **P1 测试有效性门禁**：test_command 模式下，测试全绿但零断言/恒真断言→视为空壳→阻断。
4. **P2 整目录快照回滚**：从单文件字节快照升级为目录级快照（先清除再恢复）。