---
name: coherd
description: 把当前 agent 加载为 coherd 协作集群的某个角色(coordinator / executor / reviewer / libero), 或单独加载某角色职责。用于在任意 pane 手动让 agent 快速具备协作角色。第一个参数指定角色(coordinator|executor|reviewer|libero); 仅角色名 = standalone 单 agent 模式; 角色名后跟 peer agent 名 = cluster 集群模式(读 ~/.config/coherd/CONTRACT.md 公共契约 + 对应 per-role 文档执行完整契约)。
---

# coherd — 角色加载器

## 触发方式

- pi: /skill:coherd <role> [peer...]
- Claude Code: /coherd <role> [peer...]
- <role> 四选一: coordinator | executor | reviewer | libero

## 双模式

- 无参数 → 提示: Usage: /skill:coherd <coordinator|executor|reviewer|libero> [peer...]
- 无 peer 参数 → standalone: 只加载该角色职责, 不涉及 peer 通信协议。
- 有 peer 参数(如 w9-executor w9-reviewer) → cluster: 加载完整契约, 读 ~/.config/coherd/CONTRACT.md 的公共章节 + 自身角色 per-role 文档执行。

## 加载守卫(上下文判定)

- 先检测: 用 test "${HERDR_ENV:-}" = 1 判断——HERDR_ENV=1 表示当前在 herdr 管理的集群 pane 内。
- coordinator / executor / reviewer: 需 HERDR_ENV=1; 否则报错并停止加载, 提示起集群或改加载 libero。
- libero: standalone 无 HERDR_ENV 要求, 脱离集群也成立(面向你, 被动响应)。带 peer 参数走 cluster 需 HERDR_ENV=1, 否则报错提示改 standalone 或进集群。

## 角色职责(standalone 内联, 对齐 CONTRACT.md §1 去 peer 措辞)

- coordinator: 接收意图, 拆解为任务分派, 整合并交付。
- executor: 实现分派的任务, 产出可验证结果。
- reviewer: 审查产出(正确性/安全/可维护性), 跑验证, 给 approve/revise 结论。
- libero: 承接用户的旁路/辅助需求, 交叉复核、补上下文、问答; 不进主循环, 被动响应(交互由用户定向发起)。

- **standalone 通用身份上线(rename, 四角色通用)**: 仅角色名加载 = standalone 模式, 无 peer 通信协议。当前 pane 是否 HERDR 集群 pane (HERDR_ENV=1) 决定 rename, 不看 standalone/cluster 标签。HERDR_ENV=1 时互寻址依赖 agent 名 = `${WS_SLUG}-<role>`(CONTRACT §2 名规则), 名字不带该前缀就无法被 peer 寻址。coord/exec/reviewer standalone 在集群 pane 内**同样须 rename** 建立寻址名——对齐 bin/coherd 拉起时脚本统一 rename 的行为, 本步覆盖手动加载路径:
  1. `herdr agent rename "$HERDR_PANE_ID" "<slug>-<自身角色>"`, slug 取本 pane workspace 短号小写(如 HERDR_WORKSPACE_ID=wB → wb-coordinator / wb-executor / wb-reviewer)
  2. 自身 agent 已为目标名 → 跳过(幂等); 报 agent_name_taken(槽位已有实例 / bin/coherd 已拉起该槽位)→ 报错停止加载, 不顶替——三角色须独立实例(CONTRACT §1)
  3. 非 herdr 环境(HERDR_ENV 未设)则跳过 rename

- **libero standalone 加载须知(对齐 ~/.config/coherd/libero.md 静默上线)**: 仅角色名加载 = standalone 模式, 无 peer 通信协议; 但若当前在 herdr 集群 pane 内(HERDR_ENV=1), 仍须**静默上线 rename** 以可被发现, 不因 standalone 而跳过:
  1. `herdr agent rename "$HERDR_PANE_ID" "<label>-libero"`, label 取本 pane workspace 短号小写(如 HERDR_WORKSPACE_ID=wB → wb-libero; 对齐 bin/coherd 的 `${WS_SLUG}-<role>` 命名)
  2. 不发主动消息; 交互由用户定向发起
  3. 非 herdr 环境(HERDR_ENV 未设)则跳过 rename
- libero 分支详见 ~/.config/coherd/libero.md(辅助角色); standalone/cluster 同样按有无 peer 参数区分; cluster 模式的 libero rename 走下方步骤 0, standalone 走本节 1-3(步骤 0 与本节 slug 来源一致: cluster 从 peer 推断, standalone 取本 pane workspace 短号)。

## cluster 模式执行步骤

0. **身份上线(rename, 四角色通用)**: cluster 加载 = 加入 peer 集群, 互寻址依赖自身 agent 名 = `${WS_SLUG}-<role>`(CONTRACT §2 名规则; bin/coherd 拉起时脚本已统一 rename, 本步覆盖手动加载路径)。先确认/建立自身名再继续:
   - slug 取 peer 名前缀小写(peer=w9-executor → w9)或 HERDR_WORKSPACE_ID 短号小写; 目标名 = `<slug>-<自身角色>`(libero → `<slug>-libero`)。
   - 自身 agent 已为目标名 → 跳过(幂等)。
   - 否则 `herdr agent rename "$HERDR_PANE_ID" "<目标名>"`; 报 agent_name_taken(槽位已有实例 / bin/coherd 已拉起该槽位)→ 报错停止加载, 不顶替——三角色须独立实例(CONTRACT §1)。
1. read ~/.config/coherd/CONTRACT.md 公共契约 + 自身角色 per-role 文档 (~/.config/coherd/{coordinator,executor,reviewer}.md; libero 读 ~/.config/coherd/libero.md)。
2. 按 CONTRACT.md §1 明确自己角色, 按 §2 设消息前缀 [<role>]:。
3. 按 CONTRACT.md §3-§4 运作分派/审查契约, peer 名取 args。(libero 除外——libero 不进分派/审查循环, 按 ~/.config/coherd/libero.md 执行)
4. 按 CONTRACT.md §2 用 herdr agent prompt <peer> "<msg>" 通信
