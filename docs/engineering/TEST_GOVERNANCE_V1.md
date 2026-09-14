# Test Governance v1

Status: COMPLETED / HISTORICAL ENGINEERING RECORD

> 这不是当前测试数量或性能的长期事实源。
> 下面数字是 2026-09 本轮治理完成时的验收快照。

本文记录本次 Test Governance v1 的治理内容与结论。

---

## 1. 环境隔离

- Facade 不再污染真实 `LOCALAPPDATA`；
- WeChat persisted config / registry / `USERPROFILE` / `APPDATA` 隔离；
- Windows pytest temp / `.pytest_cache` ACL 问题被识别；
- IDE Safe-Delete 弹窗来源被确认。

## 2. GUI worker 假等待治理

- `_settle_workers(timeout_ms=5000)`；
- stale / destroyed relay 造成假等待；
- 不通过粗暴缩 timeout 修；
- 区分 active / stale relay 和 callback dispatch；
- Full ~64s → ~38s。

## 3. 重复覆盖治理

- AST identical body；
- literal-masked structural duplicates；
- QQ / WeChat symmetry scan；
- hotspot scan；
- 1736 collected → 1731 collected；
- 没有以减少测试数量作为 KPI；
- owning layer 测业务规则，上层守边界契约；
- 历史 regression / GUI lifecycle / Windows / packaging 等保留。

## 4. 固定等待治理

- `QTest.qWait(600)` × 9；
- production 500ms UX delay 在测试中 monkeypatch 为 0；
- 用 event drain，不改 production timeout；
- QQ `wait_ready` 的 fake monotonic + real sleep 假等待改成统一 fake clock；
- 顺便修复模块全局状态污染造成的测试顺序依赖；
- ~38s → ~30s。

## 5. Fast Suite v1

Fast：

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not slow_integration and not known_failure" -q
```

完成时：

- 1705 passed
- 约 17s
- 约覆盖 98.5% collected tests

Full：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

完成时：

- 1730 passed
- 1 existing known failure
- 约 29-30s

再次强调：这些数字只是当时 snapshot，不是未来 baseline。

## 6. 本轮治理完成时确立的测试规则

当前长期开发规则以 `AGENTS.md` 和 `DEVELOPMENT.md` 为准。

```text
focused
→ Fast
→ phase boundary Full
```

如果改到：

- packaging
- wx_key_helper / PowerShell
- CLI subprocess
- Chromium renderer
- Windows runtime integration
- slow WeChat integration

即使 Fast 绿，也必须显式跑相关 focused integration。

## 7. 唯一故意保留的 known failure

```text
tests/test_gui.py::test_generate_share_button_creates_and_opens_share_image
```

原因：

- 测试期望 share button 可见 / 可用；
- 当前产品行为明确隐藏。

这是 product contract conflict，
不是 flaky、环境问题或 test-governance 问题。

已经转入 Hardening 的 export / share 产品决策，
测试治理不顺手修改。

## 8. 最终工程经验

- 测试快不是靠少测
- 固定 sleep 是首要性能审计目标
- fake time 必须整条时间链一致
- 测试全局状态也属于共享资源
- 环境耦合应该隔离，而不是删除测试
- regression 的价值高于「suite 看起来整洁」
- Fast / Full 分层比继续从 30s 抠 2s 更高复利
- 测试数量不是质量指标