---
name: coherd
description: 把当前 agent 加载为 coherd 协作集群的某个角色(coordinator / executor / reviewer / libero), 或单独加载某角色职责。用于在任意 pane 手动让 agent 快速具备协作角色。第一个参数指定角色(coordinator|executor|reviewer|libero); 仅角色名 = standalone 单 agent 模式; 角色名后跟 peer agent 名 = cluster 集群模式(读 ROLES.md 全文执行完整契约)。
---

# coherd — 角色加载器

## 触发方式
- pi: /skill:coherd <role> [peer...]
- Claude Code: /coherd <role> [peer...]
- <role> 四选一: coordinator | executor | reviewer | libero

## 双模式
- 无参数 → 提示: Usage: /skill:coherd <coordinator|executor|reviewer|libero> [peer...]
- 无 peer 参数 → standalone: 只加载该角色职责, 不涉及 peer 通信协议。
- 有 peer 参数(如 w9-executor w9-reviewer) → cluster: 加载完整契约, 读 ~/.config/coherd/ROLES.md 的 §2-§7 执行(消息前缀/peer 寻址/握手/分派契约/审查循环)。

## 角色职责(standalone 内联, 对齐 ROLES.md §1 去 peer 措辞)
- coordinator: 接收意图, 拆解为任务分派, 整合并交付。
- executor: 实现分派的任务, 产出可验证结果。
- reviewer: 审查产出(正确性/安全/可维护性), 跑验证, 给 approve/revise 结论。
- libero: 承接用户的旁路/一次性/辅助需求, 交叉复核、补上下文、问答; 不进主循环, 单向汇报。

libero 分支详见 ROLES.md §8(辅助角色, 6 条防污染硬条款); standalone/cluster 同样按有无 peer 参数区分。

## cluster 模式执行步骤
1. read ~/.config/coherd/ROLES.md 全文。
2. 按 §1 明确自己角色, 按 §2 设消息前缀 [<role>]:。
3. 按 §3-§4 运作分派/审查契约, peer 名取 args。(libero 除外——libero 不进分派/审查循环, 按 ROLES.md §8 执行)
4. 按 ROLES.md §2 用 herdr agent prompt <peer> "<msg>" 通信
