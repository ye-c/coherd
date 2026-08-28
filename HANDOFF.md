# HANDOFF.md — coherd 现状 + 待办

> **定位**：软方案（消息自描述标记）落地后的清晰起点 + 待办清单。
> **分支**：`feat/push-watch-brokenlink`，领先 origin **8 commit 未 push**。
> **⚠️ 关键**：软方案实现（8 文件改动）**尚在工作树、未 commit**。见 §3-A。

## §1 当前状态（软方案已落地，全链路 approve）

| 项 | 状态 |
| --- | --- |
| 架构转型 | 废弃 watch 运行时兜底 + events.log 待回执登记，转**消息自描述软方案** |
| 审查 | `spec-soft-mark` 已 reviewer approve（正确性/安全/可维护性三查通过，DoD 6 条全验） |
| 工作树 | **8 文件改动未 commit**（+66/−1198） |
| commit | 软方案实现尚未 commit；最近 commit `9f6da7d`（旧 watch 方案时代） |

## §2 软方案核心（当前生效架构）

- **消息两分**：`coherd feedback`（期待回执）/ `coherd notify`（单向知会）。
- **标记程序化注入**：CLI 注入 `[<role>|<type>]:` 前缀（`type=feedback/notify`），agent 只写 body，不手写前缀。
- **命令名 = 标记名 = 单一事实源**：`feedback` 命令 → `[<role>|feedback]:` 标记 → `events.log` `type=feedback`，一条线到底，无双源。
- **events.log 精简审计**：字段 `ws,from,to,type,msg_id,ts`（删 `op`、`expect_reply`→`type`）。仅审计，**无后台待回执登记/判定**。
- **无 watch**：`watch.py`/`test_watch.py` 已删，`cli.py` watch 子命令、`bin/coherd` watch 拉起已移除。
- **回执义务**：接收方据消息标记自觉履行；靠"沉默即故障、人自察觉"兜底（trade-off 已确认接受）。

## §3 待办清单

### A. 紧急（软方案未 commit，丢失即全功尽弃）

1. **commit 软方案 8 文件改动**（工作树 M/D，见下）。
2. **push 远程**：分支领先 origin 8 commit。

```text
 M bin/coherd            # 去 watch 拉起 + _brief standby 按角色分支
 M roles/CONTRACT.md     # 契约改写（消息两分 + 去 watch 登记）
 M src/coherd/cli.py     # 删 watch 子命令
 M src/coherd/client.py
 M src/coherd/push.py    # 标记注入 + event 精简
 D src/coherd/watch.py   # 删除（470 行）
 M tests/test_push.py
 D tests/test_watch.py   # 删除（616 行）
```

### B. 清理（reviewer approve 时 2 条非阻塞备注，已 TaskCreate #3/#4）

1. **per-role 文档措辞漂移**：`roles/executor.md`(19/31/54/55)、`roles/reviewer.md`(29/35/83) 仍含
   「登记待回执/清除待回执/watch 兜底提醒/watcher 系统唤醒」等已废弃机制措辞，与软方案矛盾。
   改 repo 源后 `./install.sh` 同步镜像五文档一致。
2. **test_push 用例 body 前缀**：`test_delivery_success_passes_peer_msg`(L210) 以 `"[reviewer]: ok"` 为 body，
   断言双重前缀，与 DoD2「body 不手写前缀」相悖。改为纯正文 body，断言 `[coordinator|feedback]: ok`。

### C. 验证（下次新集群启动必做）

1. 标记注入端到端：`coherd feedback` 投递消息以 `[<role>|feedback]:` 开头，notify 以 `[<role>|notify]:` 开头。
2. agent 只写 body、不手写 `[role]:` 前缀（无双重前缀）。
3. `./install.sh` 后五文档（CONTRACT/coordinator/executor/reviewer/libero）`diff roles/ vs ~/.config` 空。

## §4 已知未决 / 观察项

1. **events.log 新旧格式混存**：历史行旧 schema（`op`/`expect_reply`），新行 `type` 字段。审计读日志需容两种格式，未做迁移。
2. **agent 手写前缀 lag**：reviewer 的 approve 消息曾出现 `[reviewer|notify]: [reviewer]: ...` 双重前缀——
   契约与代码已对（CLI 注入），但 agent "只写 body" 的旧习惯切换有时间差，新集群启动验证才能确认干净。
3. **弃 watch 的固有成本**：agent 收到 `[feedback]` 却 idle/崩溃不回，无自动报警，唯一兜底是"沉默即故障"人工察觉。
