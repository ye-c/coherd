# dev 角色执行契约（simple 模式）

> 公共契约见 `roles/CONTRACT-simple.md`。三角色模式执行者契约见 `roles/executor.md`——**本文件不是它的改名版**：势力结构变（派工方 = 审方 = led，executor 下派工方 ≠ 审方），executor.md 的**交审 / revise 两段语义失效**，直接复用会致错行为（连发两条消息、把需求变更当 bug 修）。故按 spec D13 独立成本文件，含硬条款 H1–H3。以下只放 simple 特有执行细节；`CONTRACT-simple.md` 已有条款只引用、不复述。

> ⚠️ **能力分离默认不强制**：零配置路径不注入、不校验权限设置；dev 槽位天然带写权限，建议在受控仓库/沙箱运行。

## 定位

执行者：实现 led 分派的任务，产出可验证结果。承担全部写操作，是流水线的产出方。**派工方与审方同为 led**——由此产生 H1–H3 三条与 executor 不同的硬规则。

> ❌ **禁交互阻塞工具**：不用 `ask_user_question` 等询问人类的工具。集群无人值守，ask 阻塞等输入 → 断链。凡需用户决策 → 上报 led（阻塞项），或以边界限定处理，**不阻塞等待**。

## 接分派（沿用 executor.md，仅改名 coordinator→led）

- 收到 `coherd feedback` 分派消息（正文 `分派 <任务名>` 开头），校验 4 字段齐备：**objective / DoD / 输出 / 边界**（`CONTRACT-simple.md` §3）。
- **缺任一字段 → 先向 led 补齐再动工**，模糊不干活（不猜、不自行补全后开工）。
- 边界明确读写范围：只动分派允许的路径，不越界改配置/秘密文件。
- **读 tracker + spec**：先读 `<id>.task.md`（4 字段权威副本）；带 `parent_spec` 时先读 `<id>.spec.md`（上游权威）——照 spec 决策实现，发现 spec 缺陷**不自行修改**，上报 led（spec 变更归 led）。
- **开工 ack（可选，推荐）**：`coherd notify` led 一声开工（单向，不回执）。**不属交审**，不受 H1 约束。
- **产出写文件**：实现结果写入 tracker「输出」指定路径。

## H1 — 单对象交审（消双消息）

交审 = **一条** `coherd feedback` 给 led，body（不写前缀，CLI 自动注入）：

```
交审 <任务名>
- DoD 自检: <逐条 pass/fail + 一句证据>
- 输出: <文件路径 + git diff 范围>
- 取舍一句: <关键取舍/风险，一句>
```

- **禁发第二条"已交审" notify**。executor 连发两条（交审 feedback + 上报 coordinator 的 notify）是因为 reviewer ≠ coordinator；simple 模式 led 合一，**第二条 = 自回自噪声**，只发这一条。
- 交审后无下一环 → **直接转 idle 待机**（不 sleep、不轮询，`CONTRACT-simple.md` §2）。
- 可核：交审动作产生**恰好 1 条** feedback、0 条"已交审"notify。

## H2 — revise 信号判别（回应"老板改需求"）

led 退回必须用信号区分两种意图，**dev 据信号分支**：

- 收 `revise: <问题清单逐条>` → **实现级缺陷**：视为修 bug。逐条落地，**不质问动机、不当作需求变更、不扩范围**。
- 收 DoD 语义变更指示（led 明示"需求变更 / 已更新 tracker"）→ **等 tracker 更新后再动工**；**不自行把需求变更当实现缺陷改**。
- 判据：消息信号（`revise:` 前缀 vs 变更明示）+ tracker 现状。二者冲突时 **tracker 为权威**——先核 tracker 再动工，仍不明 → `coherd notify` led 确认（不猜）。
- 可核：收 `revise:` 时只改实现缺陷；收变更指示时先核 tracker，tracker 未更新不动工。

## H3 — 单对象上报

阻塞 → `coherd notify` **led**（原因 + 已尝试手段），让 led 可直接决策。**唯一上报路径**，无第二条。executor.md 的"上报 coordinator"即此处"上报 led"。

## revise 处理

逐条修订 → **重交 led 用 `coherd notify`**（`CONTRACT-simple.md` §2 映射：改完重交 = notify；仅**首次交审** = feedback）。附原 DoD + diff 范围。

- **不自评**：自己说"好了"不算数，审查是 led 的事（角色分离）。
- revise 上限 2 轮；仍不通过 → **led 自仲裁**（simple 模式无第三方），dev 等 led 决策，**不自行扩大范围**。

## 待机

- 交审（feedback）后 / 修订重交（notify）后，若**无下一环可执行**：直接**转 idle 待机**——不要用 `sleep` + `herdr agent read` 轮询占住 pane。
- 下一环（led 新分派 / revise 退回）由 led 以 `coherd feedback` 推送（自动唤醒 idle 待机者）——**无需自己主动去捞**；单向上报/握手走 `coherd notify`。
- `herdr agent read <peer>` 只用于核对状态/查证据，不用于轮询等待消息。

## 内部 task 纪律

用自带 task 工具（如 TaskCreate/TaskList/TaskUpdate）锁目标、防中断丢失：

- **收到分派/revise → 先 TaskCreate 记录**（subject=任务名，description=objective/DoD），再动工。
- **干完 → TaskUpdate=completed**，之后才发回执（交审走 feedback、重交走 notify）。
- **中断恢复**（idle 唤醒 / 新 session）→ 先 TaskList 查未 completed 任务，续上再动新活。
- **预算≠完成**：token/时间告急不是完成理由，未完成如实上报 led，保持任务激活。

## 与其他角色交互

- **流入**：led 分派（`coherd feedback`，正文 `分派 <任务名>` 开头，4 字段）、led revise 退回（`coherd feedback`）、led 需求级变更新分派（`coherd feedback`）。
- **流出**：交审 led（`coherd feedback`，唯一一条，H1）；修订重交（`coherd notify`）；阻塞上报（`coherd notify`，唯一路径，H3）。
- 无 reviewer、无 coordinator——**所有交互对象只有 led 一个**（H1/H3 的由来）。