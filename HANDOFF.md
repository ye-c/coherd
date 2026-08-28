# HANDOFF.md — coherd 现状 + 断链兜底排查手册

> **定位**：当前及后续集群的**清晰起点** + **出问题好查**的排查入口。本文件反映最近 3 提交（`c3a7316`→`982c546`→`679fd5e`）
> 落地后的最新状态：watch 全局化 + push 拆 feedback/notify + 契约回执登记边界收口 + 事件日志命名 events.log + 注释清理。
> **分支**：`feat/push-watch-brokenlink`（均**已 commit**，未 push 远程，见 §5）。
> **命令面**：`coherd push` 已删不留别名，拆为 `coherd feedback`（期待回执·登记待回执）/ `coherd notify`（单向·不登记待回执）；
> `coherd watch` 为**全局单例绑 herdr server**；事件日志统一 `events.log`。

> 历史归档（issue #8 断链修复、w2t 巩固、w2y 四任务详情）均在 `archive/<ws>/` 与各 commit message，本文件不再复述。

---

## §1 当前状态（最近 3 提交落地后）

### 已实现（全链路 approve + 吃狗粮）

| 能力 | 说明 | 状态 |
| --- | --- | --- |
| `coherd task` CLI | `new / list / show / archive / status` | ✅ |
| `coherd feedback` | **期待回执**：写 `events.log` `expect_reply=true` 登记待回执，收方必须回一条 feedback 清除待回执（关键交接：分派/交审/revise/讨论）。命令名即语义，无缺省陷阱 | ✅ |
| `coherd notify` | **纯单向**：写 `events.log` `expect_reply=false` 不登记待回执；delivered 假→非零退出提示转 feedback 重发（上报/回流/ack/握手） | ✅ |
| `coherd watch` | **全局单例**断链兜底（绑 server：无 `--ws`，订阅全部 ws/pane，靠 per-agent workspace_id 派生 role，per-event ws 判定待回执/投递） | ✅ |
| `coherd task` CLI | `new / list / show / archive / status`（tracker CRUD，不做角色决策） | ✅ |
| 入口 | `bin/coherd` switch `task\|feedback\|notify\|watch`（`push` 已移除）→ re-exec venv python | ✅ |
| launcher 起 watch | 起集群末尾 `nohup coherd watch & disown`（**无 --ws**，全局单例，探测全局 `watch.pid` 幂等：首个集群起、其余复用） | ✅ |
| 契约回执登记边界 | CONTRACT §0/§2/§7 + per-role：环节→命令映射表为唯一权威（feedback 登记待回执 / notify 不登记 / 系统提醒裸 prompt） | ✅ |
| watch EOF 防护 | 读线程 EOF/OSError→`self.stop=True`→consumer 退→finally 释放锁；启动连不上 server→不留锁。防 zombie 复发 + 回归测试覆盖 | ✅ |

### 技术栈 / 布局

- **两入口**：`bin/coherd`（bash，拉集群 + 入口路由）；`coherd {task,feedback,notify,watch}`（python/typer，功能 CLI，**不做角色决策**）。
- **依赖**：python + typer + uv，editable install（改 `src/` 即时生效）。
- **目录**：`~/.config/coherd/{tasks,reviews,archive}/<ws>/`；事件日志 `~/.config/coherd/events.log`（`COHERD_CONFIG_HOME` 可覆盖隔离）。
- **共享 helper**：`src/coherd/client.py` 提供 `agent_list(socket_path)` + `_recv_full_json`，
  feedback/notify 自派生与 watch.enum_panes 同源复用，避免复制 socket 代码。

---

## §2 断链兜底架构（一页讲清）

```text
agent A ── coherd feedback/notify <B> "[role]: ..." ──► ① append events.log (feedback: expect_reply=true 登记待回执; notify: false 不登记)
                                                        ② herdr agent prompt <B>    (送达+唤醒)
                                                        ③ B 回一条 feedback/notify → 反向清除待回执
                                                        ④ 全局 watch 见 B idle ∧ 待回执未清除 → 提醒(裸 prompt)
                                                        ⑤ 连续 2 次未清除 → escalate {event_ws}-coordinator
```

- **命令分工**：`coherd feedback`（登记待回执）/`coherd notify`（不登记）回执登记+送达；`coherd watch` **全局单例**订阅+判定+提醒；`herdr agent read` 只查证据。
- **用法**：`coherd feedback|notify <peer_agent> "<[role]: 信号 任务 — 详见 路径>"`。role 自动派生（`--role`→`COHERD_ROLE`→
  `HERDR_AGENT_NAME`→`agent.list` 末级 fallback），无需 env 前缀；`[role]:` 前缀手写（契约 §2 模板）。
- **回执语义（feedback vs notify 显式，无缺省陷阱）**：`feedback`=期待回执（watch 登记待回执，收方必须回一条以清除待回执）；
  `notify`=纯单向（不登记 pending）。拆分消灭了「`coherd push` 缺省期待回执、忘标 `--no-reply` → 待回执永不解除 → watch 误报」这一
  病根（`push` 缺省期待回执时代的首个 bug）。notify 送达失败→CLI 非零退出提示转 feedback 重发。
- **回执登记边界（环节→命令映射表为唯一权威）**：
  - **feedback 登记待回执** = 关键交接（coord→exec 分派、coord→rev 讨论/仲裁、exec→rev 交审、rev→exec revise 退回）。
  - **notify 不登记待回执** = 单向（approve: notify 回执 executor 清除交审待回执 + notify 回流 coordinator；改完重交(反向清除 exec 待回执)、exec→coord 交审上报、开工 ack、standby 握手、纯通知）。
  - **裸 `herdr agent prompt`** = 仅 watcher 系统唤醒提醒（不登记待回执，防提醒成环）。standby 已统一走 notify。
  - 代价注记：方案A（交审=feedback 登记待回执）后 reviewer 不审由 watch 兜底；watch 时间维度提醒为 CLI 后置，无待回执环节的停滞仍靠「沉默即故障」（见 §7 偏差2 变更）。
- **全局 watch role 派生（关键）**：watch 不再有单一 `self.ws`；`build_pane_map` 用每个 agent 的 `workspace_id` strip
  `${ws}-` 前缀派生 role，`_remind`/`_escalate` 用**事件自带的 ws**。若沿用 watch 级 `self.ws` 派生，全局 watch 会产全名 role →
  待回执查询 miss → 全 ws 兜底失效。`--ws` 仅作测试隔离过滤，env（`COHERD_WS`/`HERDR_WORKSPACE_ID`）不再静默填 self.ws。

---

## §3 排查手册（出问题按此查，从最常见到最罕见）

> 总原则：先看 **①watch 进程 → ②events.log → ③socket 订阅 → ④role 映射** 四层，逐步定位。

### 3.1 watch 进程没起来（已修复，验证点）

- **症状**：断链兜底完全不工作，peers 断链后无人提醒。
- **根因（已修）**：`bin/coherd` 曾裸 `&` 起 watch，bash 退出后 SIGHUP 杀 → 兜底失效。改 `nohup ... & disown`。
- **定位**：`ps aux | grep "coherd watch" | grep -v grep` 应见 `coherd watch`（**全局单例，无 --ws**）。
- **修复**：`nohup coherd watch & disown`（无 `--ws` = 全局；或 `--escalate-agent` 指定投递目标）。**新集群 `coherd init` 后必验本条**。全局 watch 首个集群拉起，其余集群探测 `watch.pid` 存活即复用。

### 3.2 events.log 无记录（peers 没走 feedback/notify）

- **症状**：watch 活着但从不提醒（无 pending 可判）。
- **根因**：peers 读了旧契约/没读 brief，仍用裸 `herdr agent prompt` 发任务交互消息 → 不登记待回执。
- **定位**：`tail -20 ~/.config/coherd/events.log` 有无 `op:send` 行；没有即此因。
- **修复**：确认 peers 读的是新版 CONTRACT（`grep "coherd feedback\|coherd notify" ~/.config/coherd/CONTRACT.md` 应命中；旧版是 `coherd push`）；新集群 brief 已含回执登记提示。

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

### 3.5 pending 误报 → 反提醒（已修复，重点验证）

- **症状**：watch 反复提醒某 peer「对 X 连续 idle 未回执」，但实际 X 契约本不回执。
- **根因（已修）**：单向上报/回流（exec→coord 交审上报、reviewer→coord approve 回流）**误走缺省期待回执的登记** → 收方待回执永不解除 → 误报。
- **定位**：`events.log` 找「应为单向上报却无 expect_reply=false」的 send 行（`expect_reply` 缺省 true）。
- **修复**：单向上报/回流/ack/通知用 `coherd notify`（expect_reply=false 不登记待回执）；期待回执的交接用 `coherd feedback`，两条命令名即语义。**契约源 `roles/CONTRACT.md` 与装到 `~/.config` 的副本必须同步此规则**（曾踩：executor 只改了副本，新集群装 repo 版旧契约）。

### 3.6 watch 多实例 / 重复提醒

- **症状**：同一 pane 被重复提醒。
- **根因**：起了两个 watch（pid 锁未生效或手动二次起）。
- **定位**：`ps aux | grep "coherd watch"`（应只有 1 个）；pid 锁在 `~/.config/coherd/watch.pid`（`COHERD_CONFIG_HOME` 派生）。
- **修复**：杀多余实例；`coherd watch` 自身 pid 锁应拒第二个（`acquire True→False→True` 幂等）。

### 3.7 兜底机制已知软肋（非 bug，观察项）

- **O_APPEND 跨进程可见性时序**：POSIX 只保证不覆盖、不保证跨进程写可见时序 → 靠 watch 幂等 D5 兜底（同 pane 已提醒且待回执未清除 → 跳过）。
- **`send_prompt timeout=30` 阻塞**：高并发下多个 30s 堆积 → 靠节流（throttle 5s）防连发。
- **role 补发现枚举短连接重拉**：新 pane 时同步重拉 `agent.list`，节流已兜。
- **pending 单值 dict**（`{(ws,receiver): sender}`）：同 receiver 多项待回执并列会被后写覆盖 → **漏报方向**（早项被晚项覆盖少提醒一次），比误报安全，YAGNI 缓，未改。

### 3.8 契约改写只落 ~/.config 副本，repo 源没改 → install.sh 一冲就没（w2y 复发，重点防）

- **症状**：某任务改了 `~/.config/coherd/CONTRACT.md`（或 per-role 文档）并过了审，但 `./install.sh` 后改写**凭空消失**，
  新集群 agent 读到旧契约、用已删的命令（如 `coherd push`）→ 全线报错。
- **根因**：契约**事实源是 repo `roles/*.md`**，`install.sh` 单向 `repo → ~/.config`（覆盖前把旧副本存 `.bak.<ts>`）。
  executor 若只改 `~/.config` 副本、**没回写 `roles/`**，则副本改动是「一次性」的——下次 install/re-init 即被旧 repo 冲掉。
  这是 §3.5「副本与源必须同步」的**加强复发**：`feedback/notify` 契约改写就栽在这，靠 `.bak` 捞回。
- **定位**：`grep -c feedback roles/CONTRACT.md` vs `grep -c feedback ~/.config/coherd/CONTRACT.md`——repo=0 而副本>0 即中招；
  改写丢失时 `grep -l feedback ~/.config/coherd/CONTRACT.md.bak.* | head -1` 可捞最近含改写的备份。
- **铁律**：**任何契约/角色文档改写，一律直接写 repo `roles/<doc>.md`**（事实源），写完再 `./install.sh` 同步到 `~/.config`。
  分派 tracker 的「边界」字段应写 `roles/CONTRACT.md` 而非 `~/.config/coherd/CONTRACT.md`。

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

### 收尾待办（w2y 遗留）

- **push 远程 + PR**：`feat/push-watch-brokenlink` 最近 3 提交（`c3a7316`/`982c546`/`679fd5e`）已本地 commit、**未 push 远程**，待 push origin + 开 PR 合 main。
- **重启验证（用户即将做）**：`./install.sh` 后 `coherd init`，必验——① §3.1 全局 `coherd watch`（无 --ws）存活；
  ② 多集群并存只起**一个**全局 watch、覆盖双 ws 兜底；③ §3.8 契约 `grep feedback roles/CONTRACT.md`>0 且 install 后 diff roles/ vs ~/.config 五文档一致（§10 镜像校验）；
  ④ feedback 登记待回执 / notify 不登记待回执，无 §3.5 误报；⑤ EOF：kill server → watch 自动退且 `watch.pid` 释放（无 zombie）。
- **events.log 噪声**：`events.log` 有 6 条 `w2x/w2z-nonexistent-peer` 测试遗留（无害、不触提醒）；后续验证一律用临时
  `log_path`（`push.run` 已支持注入）勿污染真实事件日志。

---

## §6 历史（只留最近 3 提交；更早归档在 `archive/<ws>/` + 各 commit message）

- **`c3a7316`** feat(cli)：push 拆为 feedback/notify，watch 锁按 ws 派生。
- **`982c546`** feat：watch 全局化（生命周期绑 server、per-agent ws 派生 role、EOF→stop→释放锁）+ push 拆分 + 契约回执登记边界收口（交审降 notify、approve 只回流 coord）。
- **`679fd5e`** refactor：事件日志统一命名 `push-events.log`→`events.log`（读写端点对齐）+ 清理开发遗留注释 + ruff 格式化。

> 更早的 issue #8 断链修复、w2t 三项巩固、w2y 四任务详述均已归档（`archive/w2p`、`archive/w2t`、`archive/w2y` 含各自 tracker + approve/discuss 结论），不在此复述。

---

## §7 反面教材：一次真实 loop 的事件日志轨迹（w2y · comment-sweep）

> 新集群开工先读这节——下面每一步都是**真实事件日志行**（`events.log`/`push-events.log` 的 `op:send`），
>
> ⚠️ **映射已变更（apply-ledger-fix 方案A 落地，2026-08-28）**：交审由 notify 改为 `feedback`（登记 reviewer 待回执，reviewer 不审由 watch 兜底）；approve = notify 回执 executor 清除交审待回执 + notify 回流 coordinator。下方轨迹为变更前（旧语义）真实事件日志；现状映射以 §2 与 CONTRACT §7 D10 为准。
>
> 标 `REPLY`=feedback（登记待回执）、`notify`=不登记待回执。看得到正确链路，也看得到两个真实偏差。

### 轨迹（coord=w2y-coordinator，下同）

```text
06:02:46  coord  --REPLY-->  exec      分派 comment-sweep（feedback 登记待回执：exec 待回执 coord）
06:03:03  exec   --REPLY-->  coord     开工确认 ✗偏差1：开工 ack 应是 notify，用了 feedback → 反向登记 coord 待回执
06:03:20  coord  --notify--> exec     批准+清除待回执：一条 notify 既反向清除分派待回执、又不产生新待回执
06:02:46  coord  --notify--> rev      （预告交审，notify）
06:04:59  exec   --notify--> rev      交审 ✓（旧语义：交审=notify 单向，不登记 rev 待回执）
06:04:59  exec   --notify--> coord    已交审上报 ✓
06:06:44  rev    --REPLY-->  exec     revise 退回 ✓（feedback 登记待回执：exec 待回执 rev，逼 exec 必改重交）
06:06:44  rev    --notify--> coord    revise 回流 coord ✓
06:07:38  exec   --notify--> rev      重交审 ✓（notify 反向清除「exec 待回执」+ 不登记新待回执，闭环）
06:07:38  exec   --notify--> coord    重交上报 ✓
06:08:17  rev    --notify--> coord    approve 只回流 coord ✓✓（旧语义验证点：不再双发 exec）
```

### 两个偏差 = 新集群最易犯的错

1. **开工 ack 用成 feedback**（06:03:03）：`feedback`=期待回执=登记待回执。开工确认是单向状态上报，该 `notify`。
   用 feedback 就多登记一笔「coord 待回执」→ 逼 coord 再补一条 notify 去清除（06:03:20 就是补这个）。
   **记**：开工 ack / 交审上报 / 回流 / 握手 = notify，别手滑 feedback。
2. **交审降 notify 的代价**（06:04:59，旧语义）：exec→rev 交审是 notify=不登记待回执 → **若 reviewer 收了交审长期不审，watch 无待回执可提醒**（断链无人兜）。
   本 loop 侥幸 rev 及时审；但这是**已知软肋不是 bug**——契约取舍「沉默即故障、用户自然察觉」。新集群别指望交审有兜底。**（方案A 落地后已修复：交审走 feedback 登记 reviewer 待回执，reviewer 不审由 watch 兜底；approve 以 notify 回执 executor 清除待回执——见顶部变更注记。）**

### 正确点（照做）

- approve（方案A 后）＝ `notify` 回执 executor（清除交审待回执，不登记新待回执）+ `notify` 回流 coordinator——两条消息职责不同（回执 vs 回流），不是冗余双发。（历史：w2y 当时 approve 只回流 coord 不再双发 exec，因当时交审=notify 无待回执可清。）
- revise 用 feedback（06:06:44）逼出重交，重交用 notify（06:07:38）恰好反向清除待回执——**每轮 revise 恰好一条登记、一条 notify 清除**，循环无残留。
