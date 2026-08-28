# HANDOFF.md — coherd 现状 + 断链兜底排查手册

> **定位**：当前及后续集群的**清晰起点** + **出问题好查**的排查入口。本文件是 issue #8（断链修复）+ w2t 三项
> 巩固 + **w2y 本轮四任务（watch 跨集群锁 / push→feedback+notify 拆分 / watch 生命周期绑 server / 全局一致性收口）**
> 落地后的最新状态快照。
> **分支**：`feat/push-watch-brokenlink`。issue #8 5 commits + w2t 4 commits + **w2y 未 commit（见 §5）**。
> **命令面已变**：`coherd push` 已拆为 `coherd feedback`（期待回执·挂账）/ `coherd notify`（单向·不挂账），
> `push` 子命令**已移除不留别名**；`coherd watch` 由 per-ws 多实例改为**全局单例绑 herdr server**。

---

## §1 当前状态（2026-08-27 · issue #8 + 本轮巩固三任务落地）

### 已实现（全链路 approve + 吃狗粮）

| 能力 | 说明 | 状态 |
| --- | --- | --- |
| `coherd task` CLI | `new / list / show / archive / status` | ✅ |
| `coherd feedback` | **期待回执**：写 `events.log` `expect_reply=true` 挂账，收方必须回一条 feedback 清账（关键交接：分派/交审/revise/讨论）。命令名即语义，无缺省陷阱 | ✅ T-A→w2y 拆 |
| `coherd notify` | **纯单向**：写账本 `expect_reply=false` 不挂账；delivered 假→非零退出提示转 feedback 重发（上报/回流/ack/握手） | ✅ w2y 拆 |
| `coherd watch` | **全局单例**断链兜底（绑 server：无 `--ws`，订阅全部 ws/pane，靠 per-agent workspace_id 派生 role，per-event ws 判账/投递） | ✅ T-B→w2y 改 |
| 入口 | `bin/coherd` switch `task\|feedback\|notify\|watch`（`push` 已移除）→ re-exec venv python | ✅ w2y 拆 |
| launcher 起 watch | 起集群末尾 `nohup coherd watch & disown`（**无 --ws**，全局单例，探测全局 `watch.pid` 幂等：首个集群起、其余复用） | ✅ w2y 改 |
| 契约记账边界 | CONTRACT §0/§2/§7 + per-role：环节→命令映射表为唯一权威（feedback 挂账 / notify 不挂 / 系统提醒裸 prompt）（D10） | ✅ w2y 改 |
| watch EOF 防护 | 读线程 EOF/OSError→`self.stop=True`→consumer 退→finally 释放锁；启动连不上 server→不留锁。防 bug1 zombie 复发 + 回归测试覆盖 | ✅ w2y 修 |

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
- **目录**：`~/.config/coherd/{tasks,reviews,archive}/<ws>/`；账本 `~/.config/coherd/events.log`（`COHERD_CONFIG_HOME` 可覆盖隔离）。
- **共享 helper**：`src/coherd/client.py`（domstring 注 herdr_client）提供 `agent_list(socket_path)` + `_recv_full_json`，
  push 自派生与 watch.enum_panes 同源复用，避免复制 socket 代码。

---

## §2 断链兜底架构（一页讲清）

```
agent A ── coherd feedback/notify <B> "[role]: ..." ──► ① append events.log (feedback: expect_reply=true 挂账; notify: false 不挂)
                                                        ② herdr agent prompt <B>    (送达+唤醒)
                                                        ③ B 回一条 feedback/notify → 反向清 pending
                                                        ④ 全局 watch 见 B idle ∧ pending 未清 → 提醒(裸 prompt)
                                                        ⑤ 连续 2 次不清 → escalate {event_ws}-coordinator
```

- **命令分工**：`coherd feedback`（挂账）/`coherd notify`（不挂账）记账+送达；`coherd watch` **全局单例**订阅+判定+提醒；`herdr agent read` 只查证据。
- **用法**：`coherd feedback|notify <peer_agent> "<[role]: 信号 任务 — 详见 路径>"`。role 自动派生（`--role`→`COHERD_ROLE`→
  `HERDR_AGENT_NAME`→`agent.list` 末级 fallback），无需 env 前缀；`[role]:` 前缀手写（契约 §2 模板）。
- **回执语义（feedback vs notify 显式，无缺省陷阱）**：`feedback`=期待回执（watch 登记 pending，收方必须回一条清账）；
  `notify`=纯单向（不登记 pending）。拆分消灭了「`coherd push` 缺省期待回执、忘标 `--no-reply` → 永久欠账 → watch 误报」这一
  病根（本轮首个 bug 即此）。notify 送达失败→CLI 非零退出提示转 feedback 重发。
- **记账边界（D10，环节→命令映射表为唯一权威）**：
  - **feedback 挂账** = 关键交接（coord→exec 分派、coord→rev 讨论/仲裁、exec→rev 交审、rev→exec revise 退回）。
  - **notify 不挂账** = 单向上报（exec→coord 交审上报、rev→coord approve/revise 回流、开工 ack、standby 握手、纯通知）。
  - **裸 `herdr agent prompt`** = 仅 watcher 系统唤醒提醒（不记账，防提醒成环）。standby 已统一走 notify（E3）。
- **全局 watch role 派生（w2y 关键）**：watch 不再有单一 `self.ws`；`build_pane_map` 用每个 agent 的 `workspace_id` strip
  `${ws}-` 前缀派生 role，`_remind`/`_escalate` 用**事件自带的 ws**。若沿用 watch 级 `self.ws` 派生，全局 watch 会产全名 role →
  查账 miss → 全 ws 兜底失效。`--ws` 仅作测试隔离过滤，env（`COHERD_WS`/`HERDR_WORKSPACE_ID`）不再静默填 self.ws。

---

## §3 排查手册（出问题按此查，从最常见到最罕见）

> 总原则：先看 **①watch 进程 → ②账本 → ③socket 订阅 → ④role 映射** 四层，逐步定位。

### 3.1 watch 进程没起来（已修复，验证点）

- **症状**：断链兜底完全不工作，peers 断链后无人提醒。
- **根因（已修）**：`bin/coherd` 曾裸 `&` 起 watch，bash 退出后 SIGHUP 杀 → 兜底失效。改 `nohup ... & disown`。
- **定位**：`ps aux | grep "coherd watch" | grep -v grep` 应见 `coherd watch`（**全局单例，无 --ws**）。
- **修复**：`nohup coherd watch & disown`（无 `--ws` = 全局；或 `--escalate-agent` 指定投递目标）。**新集群 `coherd init` 后必验本条**。全局 watch 首个集群拉起，其余集群探测 `watch.pid` 存活即复用。

### 3.2 账本无记录（peers 没走 feedback/notify）

- **症状**：watch 活着但从不提醒（无 pending 可判）。
- **根因**：peers 读了旧契约/没读 brief，仍用裸 `herdr agent prompt` 发任务交互消息 → 不记账。
- **定位**：`tail -20 ~/.config/coherd/events.log` 有无 `op:send` 行；没有即此因。
- **修复**：确认 peers 读的是新版 CONTRACT（`grep "coherd feedback\|coherd notify" ~/.config/coherd/CONTRACT.md` 应命中；旧版是 `coherd push`）；新集群 brief 已含记账边界提示。

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
- **根因（本轮已修）**：单向上报/回流（exec→coord 交审上报、reviewer→coord approve 回流）**误走默认 `coherd push`**（期待回执）→ 收方永久欠账 → 误报。
- **定位**：`events.log` 找「应为单向上报却无 expect_reply=false」的 send 行（`expect_reply` 缺省 true）。
- **修复**：单向上报/回流/ack/通知用 `coherd notify`（expect_reply=false 不挂账）；期待回执的交接用 `coherd feedback`，两条命令名即语义。**契约源 `roles/CONTRACT.md` 与装到 `~/.config` 的副本必须同步此规则**（曾踩：executor 只改了副本，新集群装 repo 版旧契约）。

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

### 3.8 契约改写只落 ~/.config 副本，repo 源没改 → install.sh 一冲就没（w2y 复发，重点防）

- **症状**：某任务改了 `~/.config/coherd/CONTRACT.md`（或 per-role 文档）并过了审，但 `./install.sh` 后改写**凭空消失**，
  新集群 agent 读到旧契约、用已删的命令（如 `coherd push`）→ 全线报错。
- **根因**：契约**事实源是 repo `roles/*.md`**，`install.sh` 单向 `repo → ~/.config`（覆盖前把旧副本存 `.bak.<ts>`）。
  executor 若只改 `~/.config` 副本、**没回写 `roles/`**，则副本改动是「一次性」的——下次 install/re-init 即被旧 repo 冲掉。
  这是 §3.5「副本与源必须同步」的**加强复发**：本轮 `feedback/notify` 契约改写就栽在这，靠 `.bak` 捞回。
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

### 收尾待办（w2y 本轮遗留）

- **未 commit**：w2y 4 任务改动全在工作区未提交（`bin/coherd` + `src/coherd/watch.py` + `src/coherd/cli.py` +
  `src/coherd/push.py` + `tests/test_watch.py` + **`roles/CONTRACT.md` + `roles/executor.md`（契约回写，见 §3.8）**）。
  建议 commit 前再跑一遍 `PYTHONPATH=src python3 -m unittest tests.test_watch tests.test_push`（35 全过）。
- **push 远程 + PR**：`feat/push-watch-brokenlink` 全量 push origin + 开 PR 合 main（含 w2y 未 commit 部分）。
- **重启验证（用户即将做）**：`./install.sh` 后 `coherd init`，必验——① §3.1 全局 `coherd watch`（无 --ws）存活；
  ② 多集群并存只起**一个**全局 watch、覆盖双 ws 兜底；③ §3.8 契约 `grep feedback roles/CONTRACT.md`>0 且 install 后副本一致；
  ④ feedback 挂账 / notify 不挂账，无 §3.5 误报；⑤ EOF：kill server → watch 自动退且 `watch.pid` 释放（无 zombie）。
- **账本噪声**：`events.log` 有 6 条 `w2x/w2z-nonexistent-peer` 测试遗留（无害、不触提醒）；后续验证一律用临时
  `log_path`（`push.run` 已支持注入）勿污染真实账本。

---

## §6 历史

- v5 重构（事件驱动契约 + `coherd task` CLI + 持久锚点 + 两入口）→ 0.1.1。
- **issue #8 断链修复**：调研提案 → spec（D1–D10）→ T-A(push)/T-B(watch)/T-C(接线)/T-D(契约同步) 四任务全链路落地。设计决策、审查结论、踩坑（P1 role 映射断裂）全归档在 `archive/w2p/`（含 `spec-push-watch.md`）。
- **本轮巩固（本集群 w2t 吃狗粮）**：watch-nohup-survive（launcher nohup 逃逸）→ push-cli-self-derive（role 自派生，零 env 前缀）→ watch-expect-reply（--no-reply 单向上报，消除误报）。tracker/审查全归档在 `archive/w2t/`：`watch-nohup-survive.md` / `push-cli-self-derive.md` / `watch-expect-reply.md` + 对应 approve/discuss 结论。
- **w2y 本轮四任务（集群 w2y 吃狗粮，全链路 approve）**：
  1. **watch-pid-perws**：watch pid 锁全局单例 → 老集群僵尸 watch 占锁、新集群起不来 watch（跨集群互斥）。改锁名挂 `watch-<ws>.pid`。→ 后被任务3 取代（回全局锁）。
  2. **push-feedback-notify**：`coherd push` 缺省期待回执 → 忘标 `--no-reply` 即挂账误报（任务1 收尾即遭此）。拆 `feedback`（挂账）/`notify`（不挂账）两命令，命令名即语义、无缺省陷阱；`push` 移除不留别名；`__post_init__` typing 瑕疵顺带修。tracker `archive/w2y/push-feedback-notify.md`。
  3. **watch-lifecycle-server**：watch 生命周期决策——A(绑 ws+自杀钩子=轮询，违契约禁轮询) vs **B(全局单 watch 绑 server，socket 断即死，隐式生命周期)**。采纳 B：role 派生改 per-agent workspace_id、`_remind`/`_escalate` 改 per-event ws、`run()` 删 ws raise、pid 锁回全局、读线程 EOF→`self.stop`→finally 释放锁（防 zombie）。讨论稿 `tasks/w2y/discuss-watch-lifecycle.md`。
  4. **watch-global-consistency**：B 落地与 bin/coherd §7.5 同批收口——§7.5 起全局 watch（去 --ws）+ 探测回 `watch.pid`；`__post_init__` 去 env 派生（无 --ws=全局）；补 EOF 回归测试 `test_read_loop_eof_stops_and_releases_lock`。第1轮 revise：恢复 stale 测试时误删 `test_acquire_then_reject_second`，补回后 PidLockTest 三例齐、全量 35。附「启动连不上 server 不留锁」加固。
  5. **契约回写 repo 修复（本轮新发现）**：install.sh 暴露任务2 契约改写只落 `~/.config` 副本、repo `roles/` 从未更新 → install 一冲就没。从 `.bak.1787890857` 捞回、回写 `roles/CONTRACT.md`+`roles/executor.md`。**新增 §3.8 防再犯**。
