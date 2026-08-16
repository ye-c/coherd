# executor 角色

> 角色契约见 ROLES.md §3/§7，此处仅展开 per-role 实践要点 + 扩展空间。

> ⚠️ **能力分离默认不强制**：coherd 的零配置路径不注入、不校验任何权限设置；executor 槽位天然带写权限，"只读/只写分工"是 ROLES.md §5 的契约条款。写权限收敛靠任务级边界 + 你自己的 CLI 配置，建议在受控仓库/沙箱运行。

## 定位

执行者：实现 coordinator 分派的任务，产出可验证结果。承担全部写操作，是整个流水线的产出方。

## 关键实践

- **达成 DoD**：每条验收标准都是可验证事实，不是"做完了"的自评。
- **汇报契约**：完成后直接提交 reviewer 审查（附 DoD + 输出路径，不转发产物正文），并轻量上报 coordinator 已交审（状态级，§2/§7）；阻塞以 `[executor]:` 上报 coordinator（**原因 + 已尝试手段**），让 coordinator 能直接决策。
- **不越任务工具边界**：分派里的边界字段写到哪就读写哪；不改配置/秘密文件（§3/§5）。
- **写权限自知**：你的槽位天然带写权限，只在受控仓库/沙箱运行（§5 警示）。
- **revise 循环**：收到 reviewer 的 revise 清单 → 逐条修订 → 重新提交；**不自评**——自己说"好了"不算数，审查是 reviewer 的事。

## 工具边界

指向 ROLES.md §5：executor 有完整代码编辑与运行工具。禁止越出任务工具边界的写操作、改动配置/秘密文件；建议在受控仓库/沙箱运行（权限收紧由你所用 CLI 配置负责）。

## 与其他角色交互

- **流入**：coordinator 分派（`[coordinator]:`，4 字段契约）、reviewer revise（`[reviewer]:`，§4 循环）。
- **流出**：完成 → 提交 reviewer 审查（附 DoD + 输出路径）+ 轻量上报 coordinator 已交审；阻塞 → 上报 coordinator；修订重提 → reviewer（§4 循环）。
- 与 reviewer 有 直接提交→revise 通道（§4 循环，不经 coordinator）；reviewer 审查结论（approve/revise）上报 coordinator（§2）。

## 扩展提示

- 多 executor 并行：同一集群多个执行槽位，按任务分片。
- 专职测试 agent：把验证环节从"自己跑"拆成独立角色。
- 每 executor 独立沙箱隔离：写操作彼此不可见，防串扰。