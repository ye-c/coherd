# HANDOFF.md — coherd 现状 + 断链兜底排查手册

> **定位**：当前及后续集群的**清晰起点** + **出问题好查**的排查入口。本文件是 issue #8（断链修复）落地后的最新状态快照。
> **分支**：issue #8 修复代码在 `feat/push-watch-brokenlink`（5 commits，**尚未 push 远程**）。

---

## §1 当前状态（2026-08-27 · issue #8 断链修复四任务已落地）

### 已实现（全链路 approve + 吃狗粮）

| 能力 | 说明 | 状态 |
| --- | --- | --- |
| `coherd task` CLI | `new / list / show / archive / status` | ✅ |
| `coherd push` | peer 间发消息的 runtime 记账 wrapper（append `push-events.log` + `herdr agent prompt` 送达） | ✅ T-A |
| `coherd watch` | 单例断链兜底 watcher（订阅 idle 事件 → 查 pending → 提醒/escalate） | ✅ T-B |
| 入口三合一 | `bin/coherd` switch `task\|push\|watch` → re-exec venv python | ✅ T-C |
| launcher 起 watch | 起集群末尾 `coherd watch --ws $WS_SLUG &`（pid 锁幂等） | ✅ T-C |
| 契约记账边界 | CONTRACT §0/§2/§7 + executor.md + brief：任务交互走 `coherd push`，standby/watcher 提醒裸 prompt（D10） | ✅ T-D |

### 技术栈 / 布局

- **两入口**：`bin/coherd`（bash，拉集群 + 入口路由）；`coherd {task,push,watch}`（python/typer，功能 CLI，**不做角色决策**）。
- **依赖**：python + typer + uv，editable install（改 `src/` 即时生效）。
- **目录**：`~/.config/coherd/{tasks,reviews,archive}/<ws>/`；账本 `~/.config/coherd/push-events.log`（`COHERD_CONFIG_HOME` 可覆盖隔离）。

---

## §2 断链兜底架构（一页讲清）

```
agent A ── coherd push <B> "[role]: ..." ──► ① append push-events.log (记账)
                                             ② herdr agent prompt <B>    (送达+唤醒)
                                             ③ B 反向 push 回 A → 清 pending
                                             ④ watch 见 B idle ∧ pending 未清 → 提醒
                                             ⑤ 连续 2 次不清 → escalate coordinator/人
```

- **三命令分工**：`coherd push` 只记账+送达；`coherd watch` 只订阅+判定+提醒；`herdr agent read` 只查证据。
- **记账边界（D10，唯一权威判断）**：
  - **记账** = 任务交互（分派/交审/approve·revise/讨论）→ `coherd push`
  - **不记账** = standby 握手（§7 一次性）+ watcher 唤醒提醒 → 裸 `herdr agent prompt`
  - **可判定锚点**：凡 standby / watcher 系统提醒 → 裸 prompt；其余 peer 间 `[role]:` 消息 → `coherd push`。

---

## §3 排查手册（出问题按此查，从最常见到最罕见）

> 总原则：先看 **①watch 进程 → ②账本 → ③socket 订阅 → ④role 映射** 四层，逐步定位。

### 3.1 watch 进程没起来（最常见，launcher 裸 `&` 无 nohup）

- **症状**：断链兜底完全不工作，peers 断链后无人提醒。
- **根因**：`bin/coherd` 起 watch 用裸 `&`，脚本退出后 watch 变孤儿、无 nohup 防护，可能被 SIGHUP 杀。
- **定位**：`ps aux | grep "coherd watch" | grep -v grep` 应见 `watch --ws <短号>`。
- **修复**：`nohup coherd watch --ws <短号> & disown`（或 `--escalate-agent` 指定投递目标）。

### 3.2 账本无记录（peers 没用 coherd push）

- **症状**：watch 活着但从不提醒（无 pending 可判）。
- **根因**：peers 读了旧契约/没读 brief，仍用裸 `herdr agent prompt` 发任务交互消息 → 不记账。
- **定位**：`tail -20 ~/.config/coherd/push-events.log` 有无 `op:send` 行；没有即此因。
- **修复**：确认 peers 读的是新版 CONTRACT（`grep "coherd push" ~/.config/coherd/CONTRACT.md` 应命中）；新集群 brief 已含记账边界提示。

### 3.3 watch 连不上 socket / 订阅失败

- **症状**：watch 起来但无订阅 ack，收到不了 idle 事件。
- **根因**：`HERDR_SOCKET_PATH` 未注入 / herdr server 未跑 / `events.subscribe` 参数错。
- **定位**：`echo $HERDR_SOCKET_PATH`（非空）；watch 前台运行看有无 `events.subscribe` 报错或 `subscription_started` ack。
- **关键事实（排查订阅用的知识）**：`pane.agent_status_changed` **强制 per-pane**（herdr 无粗订阅/workspace 通配）——watch 是启动 `pane.list` 枚举全部 pane 逐建订阅 + `pane.created`/`pane.agent_detected` 补发现。若只订阅一个 pane 或漏了 pane，某些角色永不触发。

### 3.4 role 映射失败（P1 曾踩的坑）

- **症状**：watch 收到 idle 事件但 role=None 早退，从不提醒。
- **根因**：想从事件载荷 `agent/display_agent/title` 找 role，但这三字段是 CLI 标签/None（`agent='claude'`），role 名只在 `AgentInfo.name`（经 `agent.rename` 写入），**不进事件载荷**。
- **正确路径（已实现）**：`watch.py` 用 `agent.list` 的 `name` 建 `pane_id→role` 映射（`derive_role` 去 `${ws}-` 前缀），`role_from_event` 只作兜底。
- **定位**：若改成读事件载荷猜 role 必复发——排查时确认 `build_pane_map` 走的是 `agent.list`。

### 3.5 pending 残留 → 死循环提醒

- **症状**：watcher 反复提醒同一 pane，但实际它没欠回执。
- **根因**：standby 握手误走 `coherd push`（违反 D10）——coordinator 不回 standby → pending 永不清 → watcher 死循环。
- **定位**：`push-events.log` 里 `from/to` 看是否有 standby 相关 send 行。
- **修复**：standby 必须裸 `herdr agent prompt`（账本无 op:send 行）。

### 3.6 watch 多实例 / 重复提醒

- **症状**：同一 pane 被重复提醒。
- **根因**：起了两个 watch（pid 锁未生效或手动二次起）。
- **定位**：`ps aux | grep "coherd watch"`（应只有 1 个）；pid 锁在 `~/.config/coherd/`（`COHERD_CONFIG_HOME` 派生）。
- **修复**：杀多余实例；`coherd watch` 自身 pid 锁应拒第二个（`acquire True→False→True` 幂等）。

### 3.7 兜底机制已知软肋（非 bug，观察项）

- **O_APPEND 跨进程可见性时序**：POSIX 只保证不覆盖、不保证跨进程写可见时序 → 靠 watch 幂等 D5 兜底（同 pane 已提醒且 pending 未清 → 跳过）。
- **`send_prompt timeout=30` 阻塞**：高并发下多个 30s 堆积 → 靠节流（throttle 5s）防连发。
- **role 补发现枚举短连接重拉**：新 pane 时同步重拉 `agent.list`，节流已兜。

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
2. **launcher 起 watch 的 `$?` 分支日志不可达**（T-C reviewer 备注）：`&` 后台派发返回恒 0，WARN 分支永不触发——仅日志措辞，watch 存活由 pid 锁+下次探测兜底。要修就把 `$?` 分支改成「静默起 + sleep 探测 pid 存活再报准」。
3. **archive 复盘段（§3.2）**：见旧 HANDOFF，归档内容从「任务定义」→「可检索经验」（决策理由/踩坑/教训），待落地。

### 开放 feature

- **#9** spec/ticket 概念制度化（设计定案 + 任务票），non-urgent。
- **#4** locale/CLI 语言不匹配、**#3** 零配置能力强制、**#2** workspace 隔离（见 GitHub issues）。

### 收尾待办（本次遗留）

- **push 远程**：`feat/push-watch-brokenlink` 5 commits 未 push，建议 push + 开 PR。
- **重启验证**：首次真实 `coherd init` 拉起 watch 的存活（§3.1 是第一排查点）。

---

## §6 历史

- v5 重构（事件驱动契约 + `coherd task` CLI + 持久锚点 + 两入口）→ 0.1.1。
- **issue #8 断链修复**（本 session）：调研提案 → spec（D1–D10）→ T-A(push)/T-B(watch)/T-C(接线)/T-D(契约同步) 四任务全链路落地。设计决策、审查结论、踩坑（P1 role 映射断裂）全归档在 `archive/w2p/`（含 `spec-push-watch.md`）。
