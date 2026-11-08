# 贡献指南（Contributing）

欢迎提交 Issue、 bug 报告与 Pull Request。本项目零第三方依赖，环境要求仅
**Python 3.8+**。

## 1. 先读许可再动手

本项目采用 **GPLv3-or-later / 商业许可双许可**。向本仓库提交任何贡献，
即表示你已阅读并同意 `CLA.md`（贡献者以「可再许可」方式授权，这是双许可
成立的前提）。企业贡献请由授权代表在 PR 中确认。详见：

- `LICENSE` — 双许可主声明
- `LICENSE-GPL-3.0.txt` — 社区版全文
- `LICENSE-COMMERCIAL.md` — 商业许可说明
- `CLA.md` — 贡献者许可协议
- `README.md` 第九节 — 选择指引

## 2. 本地验证

```bash
python -m pytest -q                # 回归测试（当前 43 条）
                                   # pyproject.toml 的 testpaths=["tests"]
                                   # 已阻止收集 work/ 下的演练副本
python self_heal_demo.py            # 四幕演练，应全 PASS，rc=0
python self_heal.py --self          # 对自身目录做 H7 完整性体检
python verify_trust.py verify --target . --anchor <你的带外锚点路径>
```

`self_heal.py --self` 默认只跑 H7（完整性守护），不会让 H1–H6 格式 healer
改写合法源码；需要旧行为时加 `--with-format-healers`。

## 3. 自举铁律（本项目特有，务必遵守）

H7 以 **`baseline.json` 或 git HEAD** 为可信基线。任何未提交的改动都会被
视为「偏离基线」，而 `--self` 会按 HEAD 把它们**回退掉**。因此正确顺序永远是：

1. 改代码 / 改文档；
2. **先 `git commit`**；
3. 若新增或删除了受保护文件，重生成基线：
   `python make_baseline.py . --with-bytes`；
4. 若配有带外锚点，重封印：
   `python verify_trust.py seal --target . --anchor <锚点>`；
5. 最后才跑 `python self_heal.py --self` / 守护进程。

> 顺序颠倒 = 你的改动被自己写的安全机制还原。这不是 bug，是设计。

## 4. 提交流程

1. Fork / 新建分支，改动保持聚焦；
2. 跑完上面第 2 节的全部命令；
3. PR 描述中写清「改了什么、为什么、怎么验证」，并附
   `I have read and agree to the CLA.`；
4. 新增文件请确认不会触发 H7 误报：受保护扩展名见
   `healers/integrity_guard.py` 的 `_TEXT_EXTS`，白名单见
   `DEFAULT_NEW_FILE_WHITELIST`。

## 5. 边界

- 本项目**不修复业务逻辑错误**、不是杀毒软件、不查内存注入；
  能力与信任假设见 `THREAT_MODEL.md`。
- 文档改动同样受 H7 保护（`.md` / `.txt` 在扫描范围内），需按第 3 节处理。
- 无扩展名文件（`LICENSE`、`NOTICE`）不在 `baseline.json` 的扫描范围内，
  依赖 git 版本历史与带外信任锚点保护 —— 修改它们时请格外留意。
