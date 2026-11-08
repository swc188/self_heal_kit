# 企业落地清单：CI 构建产物完整性守护

> 面向想把 `ci_artifact_guard.py` 接入生产流水线的团队。
> **核心原则**：基线必须在「可信时刻」生成，锚点必须存放在「攻击者够不着的地方」。

---

## 1. 基线生成时机 —— 可信窗口

| 阶段 | 动作 | 可信度要求 | 备注 |
|------|------|------------|------|
| **构建完成** | `python make_baseline.py dist/ --with-bytes --scan-binaries` | **最高** — 构建器刚产出产物，未经任何第三方处理 | 必须在同一 CI job / stage 内完成，中间不可落盘到共享存储 |
| **发布前** | `python ci_artifact_guard.py --target dist/ --scan-binaries` | 高 — 产物已在流水线中流转，需再次核验 | 可选 `--no-repair` 仅作门禁；默认自愈并继续 |

> ⚠️ **禁忌**：不要在「构建完成」后把产物拷贝到别处、再回来生成基线。
> 中间落盘的瞬间就是攻击窗口。一定要 **build → seal 原地原子完成**。

---

## 2. 带外锚点存储位置

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **只读 NFS / 只读 SMB 挂载** | 简单、低成本、现成基建 | 需网络隔离、防止挂载点被重挂 | 内网私有 CI、已有只读存储 |
| **HashiCorp Vault KV v2** | 审计日志、版本、ACL、动态凭证 | 需运维 Vault 集群 | 已用 Vault 管理密钥的团队 |
| **AWS S3 Object Lock / Azure Immutable Blob / GCS Object Versioning + Retention** | 云厂商合规背书、WORM 法律效力 | 跨云成本、需配置策略 | 云原生团队、合规要求强 |
| **离线介质（USB / 光盘 / 纸质 QR）** | 物理气隙、绝对不可篡改 | 人工操作、不适合高频 | 核心发布、金融/军工级 |

**最小可行**：私有 Git 仓库的 `protected branch` + `signed commit` 存锚点 JSON，
再配合 `verify_trust.py verify --anchor` 校验。比「全在流水线里」强得多。

---

## 3. 轮换策略

| 频率 | 动作 | 命令 | 说明 |
|------|------|------|------|
| **每次发布** | 重新生成基线 + 重新 seal | `make_baseline.py dist/ --with-bytes --scan-binaries && verify_trust.py seal --target dist/ --anchor $ANCHOR` | 发布流水线自动完成，无人工 |
| **每周/每日** | 定期自我维护（看门狗模式） | `self_heal_watch.py --target /opt/app --maintain-interval 86400 --maintain-first --trust-anchor $ANCHOR` | 长期运行的服务端、边缘设备 |
| **密钥/证书轮换时** | 同步更新锚点 | 同上 | 配合证书生命周期 |

> `self_heal_watch.py --maintain-interval` 会自动：重新生成 baseline（含 `__bytes__`）→ 重新 seal anchor。
> 这让**合规的配置变更**（如修改 `config.yaml`）自动纳入基线，不再触发告警。

---

## 4. 事件响应 SOP

| 事件 | 现象 | 响应步骤 | 责任人 |
|------|------|----------|--------|
| **TRUST_BROKEN** | `verify_trust.py verify` 退出 1 / watch 日志出现 `TRUST_BROKEN` | 1. 立即隔离该构建/发布环境<br>2. 对比 `baseline.json` 与 anchor 记录的 sha256，确认被篡改文件<br>3. 从可信源（Git HEAD / 归档制品库）恢复干净文件<br>4. `make_baseline.py --with-bytes --scan-binaries` 重新生成基线<br>5. `verify_trust.py seal` 重新 seal anchor<br>6. 事后复盘：入口在哪？（CI 凭证泄露？构建节点被控？） | 安全/运维 |
| **HEALED（自愈）** | watch 日志 `HEALED rounds=1` | 1. 记录告警但不阻断<br>2. 定期审计：同一文件反复自愈 = 持久化攻击或配置漂移<br>3. 若是配置漂移 → 加入轮换策略或白名单 | 运维 |
| **ALERT（--no-repair 门禁）** | CI 阶段退出 1，`DEVIATIONS: N` | 1. 阻断发布<br>2. 人工排查：是恶意篡改、还是合规变更未走轮换流程？<br>3. 走「事件响应」或「轮换策略」 | 发布经理 |

---

## 5. 部署清单（上线前逐项勾）

- [ ] **可信窗口**：`build → seal` 在同一 CI job/stage，中间无落盘、无人工干预
- [ ] **锚点离线**：anchor 存放位置与构建网络、存储、权限域**完全隔离**
- [ ] **二进制覆盖**：产物含 `.exe/.so/.dll/.bin` → 两处都加 `--scan-binaries`
- [ ] **白名单最小化**：`DEFAULT_NEW_FILE_WHITELIST` 仅保留真正易变目录（`dist/`、`build/`、`*.log`）
- [ ] **轮换自动化**：发布流水线自动重新 seal；长期服务跑 `self_heal_watch --maintain-interval`
- [ ] **告警接入**：`TRUST_BROKEN` / `HEALED` / `ALERT` 接入监控（Prometheus/Grafana/钉钉/企微）
- [ ] **演练过**：刻意篡改产物 + 基线 + anchor，验证 `TRUST_BROKEN` → 恢复 → `TRUST OK` 全流程
- [ ] **文档归档**：本清单 + 流水线 YAML + SOP 存入团队知识库，版本化管理

---

## 6. 常见误区（避坑指南）

| 误区 | 后果 | 正确做法 |
|------|------|----------|
| 把 `baseline.json` 只存在产物目录，不做带外 anchor | 攻击者同时改产物和基线，完整性失效 | **必须** `verify_trust.py seal` 到离线位置 |
| `--target` 指向仓库根而非 `dist/` | `dist/` 下新文件被白名单吞掉，漏报投放 | **必须**指向产物目录本身 |
| 产物含二进制却没加 `--scan-binaries` | 二进制被默认跳过，篡改不可见 | 两处命令**同时**加 `--scan-binaries` |
| 用 `self_heal.py --target` 而不是 `ci_artifact_guard.py` | H1-H6 格式修复会「修正」合法产物 | 仅挂 H7（IntegrityGuardHealer） |
| 基线生成后把产物拷贝到别处再 seal | 拷贝瞬间可被替换 | 原地 seal，artifact 传递用 CI 内置机制 |

---

## 7. 版本兼容性矩阵

| 组件 | 最低版本 | 推荐版本 | 说明 |
|------|----------|----------|------|
| Python | 3.8 | 3.11+ | 标准库仅依赖，无第三方包 |
| Git | 2.30+ | 2.40+ | `core.quotepath=false` 需较新版本 |
| CI 系统 | 任意 | 见示例 | 只要能跑 Python + 传 artifact 即可 |

---

## 8. 联系与支持

- **私下漏洞报告**：见 `SECURITY.md`
- **商业许可咨询**：见 `LICENSE-COMMERCIAL.md`
- **贡献指南**：见 `CONTRIBUTING.md`（含 H7 自举铁律：先 commit、再 baseline、再 seal、再 `--self`）

---

> **一句话总结**：build 即 seal，seal 即 anchor，anchor 离线，anchor 轮换，告警必查。
