---
name: coherd
description: 把当前 agent 加载为 coherd 协作集群的某个角色(coordinator / executor / reviewer / libero / led / dev), 或单独加载某角色职责。用于在任意 pane 手动让 agent 快速具备协作角色。第一个参数指定角色(coordinator|executor|reviewer|libero|led|dev); 仅角色名 = standalone 单 agent 模式; 角色名后跟 peer agent 名 = cluster 集群模式(读公共契约 + 对应 per-role 文档执行完整契约)。led/dev 属 simple 双角色模式, 公共契约是 CONTRACT-simple.md; 省略 peer 时按本 workspace slug 自动配对(见「手动配对」)。
---

# coherd — 角色加载器

## 触发方式

- pi: /skill:coherd <role> [peer...]
- Claude Code: /coherd <role> [peer...]
- 其他 agent CLI (omp/codex/opencode…) 无 slash 命令: 直接喂 bootstrap prompt, 见「手动配对」。
- <role> 六选一: coordinator | executor | reviewer | libero | led | dev

## 双模式

- 无参数 → 提示: Usage: /skill:coherd <coordinator|executor|reviewer|libero|led|dev> [peer...]
- 无 peer 参数 → standalone: 只加载该角色职责, 不涉及 peer 通信协议。**led/dev 例外**: 省略 peer 即按本 workspace slug 配对(见「手动配对」), 不是孤角色。
- 有 peer 参数(如 w9-executor w9-reviewer) → cluster: 加载完整契约, 读公共契约(~/.config/coherd/CONTRACT.md; **led/dev 读 CONTRACT-simple.md**)的公共章节 + 自身角色 per-role 文档执行。

## 加载守卫(上下文判定)

- 先检测: 用 test "${HERDR_ENV:-}" = 1 判断——HERDR_ENV=1 表示当前在 herdr 管理的集群 pane 内。
- coordinator / executor / reviewer / led / dev: 需 HERDR_ENV=1; 否则报错并停止加载, 提示起集群或改加载 libero。
- **led / dev 特例**: 无 HERDR_ENV 时不得静默降级为“全能 agent”——simple 模式靠 led↔dev 两独立实例分离写/审(CONTRACT-simple §1 I1), 单实例既写又审即破铁律。报错时说明: 需在第二个 herdr pane 起对位角色。
- libero: standalone 无 HERDR_ENV 要求, 脱离集群也成立(面向你, 被动响应)。带 peer 参数走 cluster 需 HERDR_ENV=1, 否则报错提示改 standalone 或进集群。

## 角色职责(standalone 内联, 对齐 CONTRACT.md §1 去 peer 措辞)

- coordinator: 接收意图, 拆解为任务分派, 整合并交付。
- executor: 实现分派的任务, 产出可验证结果。
- reviewer: 审查产出(正确性/安全/可维护性), 跑验证, 给 approve/revise 结论。
- led (simple 模式): coordinator + reviewer 职责合并——接收用户意图, 拆解分派给 dev, 审 dev 产出 + 自审 spec, 整合交付。**不写码**。职责细节见 ~/.config/coherd/led.md。
- dev (simple 模式): 实现 led 分派的任务, 产出可验证结果; 承担全部写操作; 阻塞上报 led。职责细节见 ~/.config/coherd/dev.md。
- libero: 承接用户的旁路/辅助需求, 交叉复核、补上下文、问答; 不进主循环, 被动响应(交互由用户定向发起)。

- **standalone 通用身份上线(rename, 新磁盘角色均适用)**: 仅角色名加载 = standalone 模式, 无 peer 通信协议。当前 pane 是否 HERDR 集群 pane (HERDR_ENV=1) 决定 rename, 不看 standalone/cluster 标签。HERDR_ENV=1 时互寻址依赖 agent 名 = `${WS_SLUG}-<role>`(CONTRACT §2 名规则), 名字不带该前缀就无法被 peer 寻址。coord/exec/reviewer/led/dev standalone 在集群 pane 内**同样须 rename** 建立寻址名:
  1. `herdr agent rename "$HERDR_PANE_ID" "<slug>-<自身角色>"`, slug 取本 pane workspace 短号小写(如 HERDR_WORKSPACE_ID=wB → wb-coordinator / wb-executor / wb-reviewer; led/dev 同规则 → wb-led / wb-dev——该前缀同时是 `coherd feedback/notify` 派生自身 role 的依据, 不可省略或改名, 见「手动配对」)
  2. 自身 agent 已为目标名 → 跳过(幂等); 报 agent_name_taken(槽位已有实例 / bin/coherd 已拉起该槽位)→ 报错停止加载, 不顶替——各角色须独立实例(CONTRACT §1; simple 仅 led/dev 两实例)
  3. 非 herdr 环境(HERDR_ENV 未设)则跳过 rename

- **libero standalone 加载须知(对齐 ~/.config/coherd/libero.md 静默上线)**: 仅角色名加载 = standalone 模式, 无 peer 通信协议; 但若当前在 herdr 集群 pane 内(HERDR_ENV=1), 仍须**静默上线 rename** 以可被发现, 不因 standalone 而跳过:
  1. `herdr agent rename "$HERDR_PANE_ID" "<label>-libero"`, label 取本 pane workspace 短号小写(如 HERDR_WORKSPACE_ID=wB → wb-libero; 对齐 bin/coherd 的 `${WS_SLUG}-<role>` 命名)
  2. 不发主动消息; 交互由用户定向发起
  3. 非 herdr 环境(HERDR_ENV 未设)则跳过 rename
- libero 分支详见 ~/.config/coherd/libero.md(辅助角色); standalone/cluster 同样按有无 peer 参数区分; cluster 模式的 libero rename 走下方步骤 0, standalone 走本节 1-3。

## cluster 模式执行步骤

0. **身份上线(rename, 六角色通用)**: cluster 加载 = 加入 peer 集群, 互寻址依赖自身 agent 名 = `${WS_SLUG}-<role>`(CONTRACT §2 名规则)。先确认/建立自身名再继续:
   - slug 取 peer 名前缀小写(peer=w9-executor → w9)或 HERDR_WORKSPACE_ID 短号小写; 目标名 = `<slug>-<自身角色>`(libero → `<slug>-libero`)。**led/dev 未给 peer 参数时 slug 一律取 HERDR_WORKSPACE_ID 小写**。
   - 自身 agent 已为目标名 → 跳过(幂等)。
   - 否则 `herdr agent rename "$HERDR_PANE_ID" "<目标名>"`; 报 agent_name_taken(槽位已有实例 / bin/coherd 已拉起该槽位)→ 报错停止加载, 不顶替——各角色须独立实例(CONTRACT §1)。
1. read 公共契约 + 自身角色 per-role 文档: 三角色/libero 读 ~/.config/coherd/CONTRACT.md + {coordinator,executor,reviewer,libero}.md; **led/dev 读 ~/.config/coherd/CONTRACT-simple.md + {led,dev}.md**——simple 模式的交审/revise/上报三段语义与三角色不同, 读 CONTRACT.md 会致错行为(dev.md 开篇有此警告)。
2. 按自身契约 §1 明确自己角色; 消息前缀依自身契约 §2(三角色/libero `[<role>]:`; simple 固定用 `coherd feedback/notify`, 由 CLI 注入 `[<role>|<type>]:`)。
3. 按自身契约的分派/审查契约运作, peer 名取 args。(libero 除外——不进分派/审查循环; led 审完直接交付, 无跨甲方结论回流)
4. 按 §2 用 `coherd feedback <peer> "<body>"` / `coherd notify <peer> "<body>"` 通信——CLI 注入标记并送达(内部调 herdr agent prompt, 自动唤醒 idle 待机者)。**禁手写首前缀**(CLI 会拒收), **禁裸用 herdr agent prompt**(无标记 = 对端当用户消息处理, 且 CLI 无法派生自身 role)。

## 手动配对（simple 两角色, 不经启动器）

目的: 手动在任意 herdr pane 起任意 agent CLI 充当 led/dev 并配对——试其他 agent CLI 用, 不走 bin/coherd。
**配对不需要 rendezvous 文件或守护进程**: 命名约定 + 一次握手就够, 协议层零新增 (CLI 也不为此改——发现/配对属角色决策, 不入 CLI 护栏)。

1. **自身命名**: 各 pane 内 rename 自己为 `<slug>-<角色>`, slug = `HERDR_WORKSPACE_ID` 小写 (wB → `wb-led` / `wb-dev`)。
2. **role 派生**: `coherd feedback/notify` 从 `HERDR_WORKSPACE_ID` 派生 ws、从自身 agent 名剥 `<slug>-` 前缀派生 role (`src/coherd/push.py`)。前缀是协议硬要求, 两种偏离后果不同:
   - **无 agent 名**(未 rename, 且无 `COHERD_ROLE` / `HERDR_AGENT_NAME`) → 三段来源全缺 → CLI 报 `无法派生 role`, **响亮失败**;
   - **名不含 `<slug>-` 前缀**(如改名成 `foo`) → **不报错**, 但注入的标记变成 `[foo|notify]:`——**身份静默错标**, peer 无法按 role 归属 (derive_role 对无前缀名原样返回, 实测 `derive_role("led", "w5w") == "led"`)。
3. **peer 由约定推出**: 同 slug、角色对位 → led 的 peer 是 `<slug>-dev`, dev 的 peer 是 `<slug>-led`。不用手输, 也无需发现对方。

谁先起都行: `herdr agent prompt` 自动唤醒 idle 待机者, 后起方发一条握手即可(无轮询)。simple 握手: **dev 发一条** `coherd notify <slug>-led "standby"`, led 被动接收不回执(CONTRACT-simple §6)。

**bootstrap prompt(任意 agent CLI)**

非 pi/CC 的 CLI 没有 `/coherd`, 直接喂 prompt 让它读契约上线(不带 `[x]:` 前缀 = 用户发的, 符合 herdr 归属协议):

```bash
herdr agent start <slug>-dev --kind opencode --pane <paneID>
herdr agent prompt <slug>-dev "读 ~/.agents/skills/coherd/SKILL.md 与 ~/.config/coherd/CONTRACT-simple.md、~/.config/coherd/dev.md, 加载为 dev 角色: agent 名 <slug>-dev, peer <slug>-led; 读完后 coherd notify <slug>-led standby, 随即转 idle 待机。"
```

**边界与坑**

- **一 workspace 一对**: slug 由 workspace 派生, 同 workspace 内跑不了第二对; 换 pair 就另开 herdr workspace(天然隔离)。名被占 → `agent_name_taken`, 报错停止加载不顶替(CONTRACT-simple §1 I1)。
- **范围仅 simple 两角色**: 三角色的 peer 是集合(coord ↔ exec,rev), 约定推断不成立, 仍由 bin/coherd 起队 + 显式 peer。
- **一键/批量场景**用启动器覆盖 flag: `coherd -s --agent led=codex,dev=opencode`(per-run, 不碰全局 conf; 优先于 `COHERD_*_CMD` 与 PATH 回退)。
- **禁裸用 herdr agent prompt**: 手动模式同样必须走 `coherd feedback/notify`(理由同 cluster 步骤 4)。
- libero 与手动配对正交: 无 peer 依赖, 单独加载即可。
