# HANDOFF.md — coherd 现状 + 断链兜底排查手册

> **定位**：当前及后续集群的**清晰起点** + **出问题好查**的排查入口。本文件是 issue #8（断链修复）+ 本次 session
> 三项巩固修复落地后的最新状态快照。
> **分支**：`feat/push-watch-brokenlink`。issue #8 5 commits + 本轮 4 commits（watch 起 死 / push 自派生 /
> 契约源同步 / 诊断补档），**push 远程见 §5 收尾待办**。

---

## §1 当前状态（2026-08-27 · issue #8 + 本轮巩固三任务落地）

### 已实现（全链路 approve + 吃狗粮）

| 能力 | 说明 | 状态 |
| --- | --- | --- |
| `coherd task` CLI | `new / list / show / archive / status` | ✅ |
| `coherd push` | peer 发消息记账 wrapper（append `push-events.log` + `herdr agent prompt` 送达），role 自派生 | ✅ T-A |
| `coherd watch` | 单例断链兜底（订阅 idle → 查 pending → 提醒/escalate），`expect_reply` 语义 | ✅ T-B |
| 入口三合一 | `bin/coherd` switch `task\|push\|watch` → re-exec venv python | ✅ T-C |
| launcher 起 watch | 起集群末尾 `nohup coherd watch --ws $WS_SLUG & disown`（逃逸 SIGHUP + pid 锁幂等） | ✅ T-C |
| 契约记账边界 | CONTRACT §0/§2/§7 + per-role：任务交互 `coherd push`，standby/watcher 提醒裸 prompt（D10） | ✅ T-D |

### 本轮巩固三项（本集群吃狗粮发现并修复）

1. **watch-nohup-survive（§3.1）**：launcher 裸 `&` 起 watch 无 nohup → bash 退出杀 watch，兜底永久失效。
   改 `nohup ... & disown` + `sleep 1` 短探测 pid 存活再报 WARN/INFO。
2. **push-cli-self-derive**：launcher 刻意不注入 env → push 派生链（--role→COHERD_ROLE→HERDR_AGENT_NAME）
   全空报「无法派生 role」→ 被迫手动 `COHERD_ROLE=x` env 前缀 + msg 双写 role。改 `agent.list` 末级 fallback
   自派生（复用 watch 已验证链路，抽共享 `herdr_client` helper），**`coherd push <peer> "[role]: ..."` 零 env 零前缀**。
3. **watch-expect-reply（误报修复）**：`Ledger.apply` 曾把一切 F→T send 登记「T 欠 F」，单向上报/回流（exec→coord
   交审上报、reviewer→coord approve 回流）收方本不回执却永久欠账 → watch 误报「连续 idle 未回执」。改账本记
   `expect_reply`（缺省 True），watch 只对期待回执消息登记 pending；上报/回流/ack/纯通知用 `coherd push --no-reply`。

### 技术栈 / 布局

- **两入口**：`bin/coherd`（bash，拉集群 + 入口路由）；`coherd {task,push,watch}`（python/typer，功能 CLI，**不做角色决策**）。
- **依赖**：python + typer + uv，editable install（改 `src/` 即时生效）。
- **目录**：`~/.config/coherd/{tasks,reviews,archive}/<ws>/`；账本 `~/.config/coherd/push-events.log`（`COHERD_CONFIG_HOME` 可覆盖隔离）。
- **共享 helper**：`src/coherd/client.py`（domstring 注 herdr_client）提供 `agent_list(socket_path)` + `_recv_full_json`，
  push 自派生与 watch.enum_panes 同源复用，避免复制 socket 代码。

---

## §2 断链兜底架构（一页讲清）

```
agent A ── coherd push <B> "[role]: ..." ──► ① append push-events.log (记账, 含 expect_reply)
                                             ② herdr agent prompt <B>    (送达+唤醒)
                                             ③ B 反向 push 回 A → 清 pending
                                             ④ watch 见 B idle ∧ pending 未清 → 提醒
                                             ⑤ 连续 2 次不清 → escalate coordinator/人
```

- **三命令分工**：`coherd push` 只记账+送达；`coherd watch` 只订阅+判定+提醒；`herdr agent read` 只查证据。
- **push 用法**：`coherd push <peer_agent> "<[role]: 信号 任务 — 详见 路径>"`。role 自动派生（`--role`→`COHERD_ROLE`→
  `HERDR_AGENT_NAME`→`agent.list` 末级 fallback），**无需 env 前缀**；`[role]:` 前缀仍手写（契约 §2 模板）。
- **回执语义（expect_reply 核心）**：`coherd push` 缺省**期待回执**（watch 登记 pending，防忘回执）；单向上报/回流/
  ack/纯通知用 `coherd push --no-reply`（不登记 pending，不产生新欠）。**不标 --no-reply 的上报令收方永久欠账 → watch 误报**。
- **记账边界（D10，唯一权威判断）**：
  - **记账** = 任务交互内两态——**期待回执**（默认 push：分派/交审请求/revise/讨论问询）+ **单向上报**（`--no-reply` push：上报/回流/ack/通知）。
  - **不记账** = standby 握手（§7 一次性）+ watcher 唤醒提醒 → 裸 `herdr agent prompt`。
  - 一句话：任务交互记账（默认期待、上报 --no-reply），handshake 与系统提醒裸发。

---

## §3 排查手册（出问题按此查，从最常见到最罕见）

> 总原则：先看 **①watch 进程 → ②账本 → ③socket 订阅 → ④role 映射** 四层，逐步定位。

### 3.1 watch 进程没起来（已修复，验证点）

- **症状**：断链兜底完全不工作，peers 断链后无人提醒。
- **根因（已修）**：`bin/coherd` 曾裸 `&` 起 watch，bash 退出后 SIGHUP 杀 → 兜底失效。改 `nohup ... & disown`。
- **定位**：`ps aux | grep "coherd watch" | grep -v grep` 应见 `watch --ws <短号>`。
- **修复**：`nohup coherd watch --ws <短号> & disown`（或 `--escalate-agent` 指定投递目标）。**新集群 `coherd init` 后必验本条**。

### 3.2 账本无记录（peers 没用 coherd push）

- **症状**：watch 活着但从不提醒（无 pending 可判）。
- **根因**：peers 读了旧契约/没读 brief，仍用裸 `herdr agent prompt` 发任务交互消息 → 不记账。
- **定位**：`tail -20 ~/.config/coherd/push-events.log` 有无 `op:send` 行；没有即此因。
- **修复**：确认 peers 读的是新版 CONTRACT（`grep "coherd push" ~/.config/coherd/CONTRACT.md` 应命中）；新集群 brief 已含记账边界提示。

### 3.3 watch 连不上 socket / 订阅失败

- **症状**：watch 起来但无订阅 ack，收到不了 idle 事件。
- **根因**：`HERDR_SOCKET_PATH` 未注入 / herdr server 未跑 / `events.subscribe` 参数错。
- **定位**：`echo $HERDR_SOCKET_PATH`（非空）；watch 前台运行看有无 `events.subscribe` 报错或 `subscription_started` ack。
- **关键事实（排查订阅用的知识）**：`pane.agent_status_changed` **强制 per-pane**（herdr 无粗订阅/workspace 通配）——watch 是启动 `agent.list` 枚举全部 pane 逐建订阅 + `pane.created`/`pane.agent_detected` 补发现。若只订阅一个 pane 或漏了 pane，某些角色永不触发。

### 3.4 role 映射失败（P1 曾踩的坑）

- **症状**：watch 收到 idle 事件但 role=None 早退，从不提醒。
- **根因**：想从事件载荷 `agent/display_agent/title` 找 role，但这三字段是 CLI 标签/None（`agent='claude'`），role 名只在 `AgentInfo.name`（经 `agent.rename` 写入），**不进事件载荷**。
- **正确路径（已实现）**：watch `agent.list` 的 `name` 建 `pane_id→role` 映射（`derive_role` 去 `${ws}-` 前缀），`role_from_event` 只作兜底。
- **定位**：若改成读事件载荷猜 role 必复发——排查时确认 `build_pane_map` 走的是 `agent.list`。

### 3.5 pending 误报 → 反提醒（本轮修复，重点验证）

- **症状**：watch 反复提醒某 peer「对 X 连续 idle 未回执」，但实际 X 契约本不回执。
- **根因（本轮已修）**：单向上报/回流（exec→coord 交审上报、reviewer→coord approve 回流）**误走默认 `coherd push`**（期待回执）→ 收方永久欠账 → 误报。
- **定位**：`push-events.log` 找「应为单向上报却无 expect_reply=false」的 send 行（`expect_reply` 缺省 true）。
- **修复**：单向上报/回流/ack/通知改用 `coherd push --no-reply`。**契约源 `roles/CONTRACT.md` 与装到 `~/.config` 的副本必须同步此规则**（曾踩：executor 只改了副本，新集群装 repo 版旧契约）。

### 3.6 watch 多实例 / 重复提醒

- **症状**：同一 pane 被重复提醒。
- **根因**：起了两个 watch（pid 锁未生效或手动二次起）。
- **定位**：`ps aux | grep "coherd watch"`（应只有 1 个）；pid 锁在 `~/.config/coherd/watch.pid`（`COHERD_CONFIG_HOME` 派生）。
- **修复**：杀多余实例；`coherd watch` 自身 pid 锁应拒第二个（`acquire True→False→True` 幂等）。

### 3.7 兜底机制已知软肋（非 bug，观察项）

- **O_APPEND 跨进程可见性时序**：POSIX 只保证不覆盖、不保证跨进程写可见时序 → 靠 watch 幂等 D5 兜底（同 pane 已提醒且 pending 未清 → 跳过）。
- **`send_prompt timeout=30` 阻塞**：高并发下多个 30s 堆积 → 靠节流（throttle 5s）防连发。
- **role 补发现枚举短连接重拉**：新 pane 时同步重拉 `agent.list`，节流已兜。
- **pending 单值 dict**（`{(ws,receiver): sender}`）：同 receiver 多欠并列会被后写覆盖 → **漏报方向**（早账被晚账覆盖少提醒一次），比误报安全，YAGNI 缓，未改。

---

## §4 格式约定（当前生效）

| 桶 | 放什么 | 命名 |
| --- | --- | --- |
| `tasks/<ws>/` | 活动 tracker + 设计 spec | 文件名 = id / `spec-<name>.md` |
| `archive/<ws>/` | 已完成 tracker + 审查结论 + 提案 | 原样 rename（id 不变） |
| `reviews/<ws>/` | 审查/讨论结论 | `{verdict}-<taskid>-<HHMMSS>.md` |

- 归档 tracker 重命名 = 同步改 frontmatter `id` + 补 `created_at`。

---

## §5 已知 issue / 待办

### 未修 issue（明确记录）

1. **`show`/`archive`/`status` 对 malformed tracker 抛未捕获 `ValueError` traceback**（仅 `list` 有容错）——定向访问+命中概率低，不阻塞。
2. **archive 复盘段**：归档内容从「任务定义」→「可检索经验」（决策理由/踩坑/教训），待落地。
3. **pending 单值覆盖（漏报方向）**：见 §3.7，YAGNI 缓。

### 开放 feature

- **#9** spec/ticket 概念制度化（设计定案 + 任务票），non-urgent。
- **#4** locale/CLI 语言不匹配、**#3** 零配置能力强制、**#2** workspace 隔离（见 GitHub issues）。

### 收尾待办（本次遗留）

- **push 远程 + PR**：`feat/push-watch-brokenlink`（issue #8 5 + 本轮 4 commits）push 到 origin，开 PR 合 main。
- **重启验证**：新集群 `coherd init` 后必验——§3.1 watch 存活（nohup 逃逸）+ §3.5 单向上报用 `--no-reply` 无误报。

---

## §6 历史

- v5 重构（事件驱动契约 + `coherd task` CLI + 持久锚点 + 两入口）→ 0.1.1。
- **issue #8 断链修复**：调研提案 → spec（D1–D10）→ T-A(push)/T-B(watch)/T-C(接线)/T-D(契约同步) 四任务全链路落地。设计决策、审查结论、踩坑（P1 role 映射断裂）全归档在 `archive/w2p/`（含 `spec-push-watch.md`）。
- **本轮巩固（本集群 w2t 吃狗粮）**：watch-nohup-survive（launcher nohup 逃逸）→ push-cli-self-derive（role 自派生，零 env 前缀）→ watch-expect-reply（--no-reply 单向上报，消除误报）。tracker/审查全归档在 `archive/w2t/`：`watch-nohup-survive.md` / `push-cli-self-derive.md` / `watch-expect-reply.md` + 对应 approve/discuss 结论。
