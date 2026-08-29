# HANDOFF.md — coherd 现状 + 待办

> **定位**：session 布局重构 + 软方案落地后的最新清晰起点 + 待办清单。给新集群续接。
> **分支**：`feat/push-watch-brokenlink`，领先 origin **1 commit 未 push**（`23806d4`）。

## §1 当前状态（软方案 + session 布局已落地，全链路 approve）

| 项 | 状态 |
| --- | --- |
| 架构 | 消息自描述软方案（feedback/notify 两分）+ 数据根目录 **tasks/ → sessions/** 已重构 |
| 审查 | `w3m-session-reorg` 已 reviewer approve（DoD 8 条全过，32 tests OK，五文档 diff SAME） |
| 数据布局 | `~/.config/coherd/sessions/<ws>-<ts>-$$/` 每集群一次启动一目录，平铺 `.task.md` + 评审结论 + `events.log` |
| session 判定 | **放宽**：目录名匹配 `<ws>-*` 且为目录即记 session（无 task.md 的纯讨论/评审也计入）；events.log 归位 per-session |
| commit | 最近 `23806d4`（session 目录重构，8 文件 +58/−64），**未 push**（ahead 1） |

## §2 核心架构（当前生效）

- **消息两分**：`coherd feedback`（期待回执）/ `coherd notify`（单向知会），CLI 注入 `[<role>|<type>]:` 标记，agent 只写 body 不手写前缀。
- **命令名 = 标记名 = 单一事实源**：`feedback`→`[<role>|feedback]:`→`events.log type=feedback`，无双源。
- **无 watch**：watch.py 已删、cli 子命令移除、契约去 watch 登记。
- **回执义务**：接收方据标记自觉履行，靠"沉默即故障、人自察觉"兜底。
- **events.log**：per-session（`sessions/<ws>-<ts>-$$/events.log`），仅审计无后台待回执登记；无 session 目录冷启动回退全局 `~/.config/coherd/events.log` 兜底。
- **多任务同 session**：一个 task 一个 `<id>.task.md`，同目录平铺互不覆盖；评审结论 `<id>.<verdict>-<HHMMSS>.md` 与同名 task.md 同目录（id 前缀防撞、秒戳到轮多轮不撞）。

## §3 待办清单

### A. 紧急（1 commit 未 push）

1. **push 远程**：分支 `feat/push-watch-brokenlink` 领先 origin 1 commit（`23806d4`，session 目录重构）。

### B. 清理（reviewer 检出，真遗留未做）

1. **per-role 文档措辞漂移（软化案冲突，最需做）**：
   - `roles/executor.md`：L19「登记 coordinator 待回执、连累 watch 误报」、L20/L31「登记 reviewer 待回执：reviewer 不审时 watch 兜底提醒」、L54「涉及待回执清除」、L55「watcher 系统唤醒提醒走裸 herdr agent prompt」、L64「登记 reviewer 待回执 / 反向清除待回执」
   - `roles/reviewer.md`：L29「清除交审待回执」、L35「清除交审待回执并登记 executor 待回执」、L83「清除交审待回执」
   - 以上均为 **soft-plan 已废弃的「待回执登记/watch 兜底」机制措辞**，与 CONTRACT §0「无后台待回执登记」矛盾。改 repo 源后 `./install.sh` 同步镜像五文档一致。
2. **test_push 双重前缀**：`tests/test_push.py` L56/L220 以 `"[reviewer]: ok"` 为 body，L228 断言 `[coordinator|feedback]: [reviewer]: ok` 双重前缀，与 DoD2「body 不手写前缀」相悖。改为纯正文 body，断言 `[coordinator|feedback]: ok`。

### C. 验证（下次新集群启动必做）

1. 标记注入端到端：`coherd feedback` 投递以 `[<role>|feedback]:` 开头，notify 以 `[<role>|notify]:` 开头。
2. agent 只写 body、不手写 `[role]:` 前缀（无双重前缀）。
3. `./install.sh` 后五文档 `diff roles/ vs ~/.config` 空。
4. events.log 落 session 目录（而非全局）。

### D. 后续需求

1. （无阻塞项。session 布局重构已含原先 events.log per-session 需求，已落地。）

## §4 已知未决 / 观察项

1. **events.log 新旧格式混存**：历史全局 events.log 行旧 schema（`op`/`expect_reply`），per-session 新行 `type` 字段。审计读日志需容两种格式，未做迁移。
2. **agent 手写前缀 lag**：曾现 `[reviewer|notify]: [reviewer]: ...` 双重前缀——契约与代码已对（CLI 注入），agent 旧习惯切换有时间差，新集群启动验证确认（§3C 第2点）。
3. **弃 watch 固有成本**：agent 收到 `[feedback]` 却 idle/崩溃不回，无自动报警，唯一兜底"沉默即故障"人工察觉。
4. **镜像 diff 检不出对称陈旧**：本次 reviewer.md:29 旧路径 drift 因 repo 源与副本同旧、diff 显示 SAME 而漏过 approve，靠 reviewer 手动 grep 检出。教训：**措辞审查不能只依赖 diff**，需针对性 grep 废弃术语。
