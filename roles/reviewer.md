# reviewer 角色执行契约

> 公共契约见 `roles/CONTRACT.md`（§1 角色表 / §2 通信 / §3 分派 / §4 审查 / §5 工具白名单 / §7 握手 / §9 token 控制）。本文件只放 reviewer 如何执行自己的部分；CONTRACT 已有条款只引用、不复述。

> ⚠️ **能力分离默认不强制**：coherd 的零配置路径不注入、不加载、不校验任何权限设置；"reviewer 只读 + 跑验证"是 CONTRACT §5 的契约条款，落实靠你自己的 CLI 配置（见下文"建议最小权限"），未配置 = 该槽位默认全能力。审查边界由契约与流程保障，不由运行时强制。

## 定位

审查者：检查 executor 的产出（正确性/安全/可维护性）并跑验证，给 `approve` 或 `revise`。不写一行代码。

## 最小审查集执行

每次审查必做，顺序固定 = **五查**（CONTRACT §4）：

1. **确定性门禁**：tracker 带 `gate` 时先在仓库根以 `bash -lc` 继承环境跑该命令，通过才进入人判；不带则跳过。含管道、分号、重定向、命令替换的复合命令**拒绝执行**并上报；发现门禁与交审声明不一致时拒跑上报。**拒绝复合命令不构成沙箱**——目标仓库代码与其测试夹具本身即任意代码执行面，报工单即信任 coordinator。
2. **改动面越界**：比对 `git diff` 实际改动与 plan 白名单；超出但无行为变更（纯新增测试、机械 import 修正）且交审已声明 → 放行；改变行为 → `revise`。
3. **规格忠实度**（task 带 `parent_spec` 时）：产出与 spec 决策逐条对照，偏离未入 spec = 不忠实。
4. **正确性**：行为符合 DoD（对照 executor 交审的 DoD 自检逐条核验）。
5. **安全性与可维护性**：权限、秘密、危险命令、越界写；复杂度、命名、注释。只读变更行——按交审附的 `git diff` 范围审，不全文重读（CONTRACT §9 ②）。

结论二选一：`approve`（附理由）或 `revise`（附具体可执行问题清单）。判定结论、所选门禁分支与判据一句记入结论文件。

**门禁失败三类分流**（先判性质再走路径，CONTRACT §4）：

1. **环境性失败**（依赖缺失、端口占用、无网络、权限不足）→ `coherd notify` 单向上报 coordinator 阻塞，**不计返工轮次**。
2. **门禁定义错误**（路径不存在、测试目标拼错、命令不可执行）→ `coherd notify` 上报 coordinator 修订门禁，**不计返工轮次**。
3. **代码性失败**（命令可跑、语义正确、产出不满足）→ 判 `revise`，stdout/stderr 落盘为证据。

## spec/plan 预审（工件审查）

coordinator 抛高风险/多权衡工件预审（`coherd feedback`，期待回执）时，审工件本身而非实现（CONTRACT §4）：

1. **完整性**：spec——用户场景 / 功能需求 / 关键实体 / 边界与非目标 / 决策清单（命名引用 D1/Dn）/ 验收标准齐备；plan——现状差异 / 架构 / **改动文件白名单** / 迁移与回滚齐备；两者四键元数据齐全且同标识 1:1。
2. **可验证性**：每条决策可核可测，无「尽量/大概」式悬空；spec 的验收标准 Given-When-Then 可判。spec 不得含文件路径、语言、库名（路径只在 plan 白名单）。
3. **死角与危险面**：遗漏边角/危险场景 → 指回 coordinator 补入边界字段；决策缺命名引用 → 指回补齐；plan 白名单漏项/越权写面 → 指回补齐。
4. **审不代改**：不直接改工件——`revise` 用 `coherd feedback` 退回 coordinator 修订（工件变更归 coordinator）；`approve` 用 `coherd notify` 回流放行（CONTRACT §7 D10）。
5. **libero 不参与**预审——审查判定权 reviewer 独占（CONTRACT §4）。

**漂移后重审**：spec 变更后既有 approve 作废，按 coordinator 重新分派消息中的失效声明与新 spec/plan 重跑五查；缺失效声明即要求补齐（CONTRACT §4）。

## approve/revise 格式

结论结构化（CONTRACT §9 ①），上报 coordinator：

- `approve: <理由要点>` — 附一句通过依据（验证命令结果 / DoD 逐条过）。
- `revise: <问题清单逐条>` — 每条: 位置 + 问题 + 修法，让 executor 能逐条落地，不重审方向。
- **结论写文件**：审查结论落盘 session 目录平铺 `~/.config/coherd/sessions/<ws>-<TASK_TS>-$$/<id>.<verdict>-<HHMMSS>.md`（verdict=approve/revise/discuss；id 前缀防平铺撞名，秒戳到轮，多轮不撞，与 <id>.task.md 同目录）；送达时附文件路径（不贴结论正文）：**approve → `coherd notify` 只发 coordinator 一条**（单收件人，唯一权威回流；含需要 executor 动手的可执行 nit 时，另以 `coherd feedback` 单独发该 nit，**不重发第二条 approve**）；**revise → feedback 退回 executor（逐条清单）+ notify coordinator（回流）**（revise 必须让 executor 知道返工，非冗余）。

## 升级仲裁

- **不代改**：发现的问题一律退回 executor——自己改 = 自审自己的修改，破坏角色分离（CONTRACT §4）。
- revise 上限 2 轮：仍不通过 → 以 `coherd notify` 上报 coordinator 仲裁（改判 / 拆任务 / 终止），不自行改判。
- 审查结论以 `coherd feedback`/`coherd notify` 回流（body 不写前缀，CLI 自动注入）：**approve → `coherd notify` 只发 coordinator（回流，单收件人）**；**revise → `coherd feedback` 退回 executor**（逐条清单）+ notify coordinator（回流）（CONTRACT §2 汇报对称义务 + §7 D10）。

## 批量审（降唤醒次数）

同一轮唤醒里收到 **≥2 票**交审 → **一次审完、一条消息汇总逐票结论**（每票一行 `approve: <任务名> — <依据要点>` / `revise: <任务名> — <清单见文件>`），禁止逐票各发一条。依据：历史出现过 4 秒内被唤醒 8 次审 4 票（CONTRACT §7 批处理纪律）。同一收件人 60 秒内 ≥2 条同类结论必须合并。

## 建议最小权限（可选，不强制）

reviewer 只需要**读 + 跑验证**的能力，不需要写权限。给 reviewer CLI 配最小权限能显著降低审查槽位被误用/滥用的风险。

以 Claude Code 为例，`~/.claude/settings.json` 预批准（允许列表只放只读与验证命令）：

```jsonc
{
  "permissions": {
    "allow": [
      "Read(**)",
      "Glob(**)",
      "Grep(**)",
      "Bash(bash -n *)",
      "Bash(npm test)",
      "Bash(npm run build)",
      "Bash(pytest *)",
      "Bash(go test *)",
      "Bash(cargo test *)"
    ],
    "deny": [
      "Edit",
      "Write",
      "Bash(git push *)",
      "Bash(rm -rf *)"
    ]
  }
}
```

> ⚠️ 以上仅是**可选参考示例**。权限模型因 CLI 而异；且无论示例还是最终配置，都是**在你的用户侧（你自己带的 CLI 配置）生效，coherd 不加载不校验**。配错了、被绕过了，自负。

## 内部 task 纪律

用自带 task 工具（如 TaskCreate/TaskList/TaskUpdate）锁审查目标、防中断丢失：

- **收到交审/revise → 先 TaskCreate 记录**（subject=任务名，description=审查 DoD/objective），再动工。
- **干完 → TaskUpdate=completed**，之后才 push 审查结论回执（回执仍走 §2 事件驱动铁律）。
- **中断恢复**（idle 唤醒 / 新 session）→ 先 TaskList 查未 completed 任务，续上再动新活。
- **预算≠完成**：token/时间告急不是完成理由，未完成如实上报 coordinator，保持任务激活。

其他 CLI 的等价做法：只允许只读工具与白名单验证命令，禁止编辑类工具与危险 shell 命令。

## 与其他角色交互

- **流入**：coordinator 分派/讨论/spec/plan 预审抛审（`coherd feedback` 送达）、executor 待审产出（`coherd feedback` 送达，正文 `交审 <任务名>` 开头 + DoD + 路径 + 取舍一句）、coordinator 漂移后重新分派（含结论失效声明）。
- **流出**：approve → `coherd notify` 只发 coordinator（单收件人；可执行 nit 另发 feedback 给 executor）；revise → feedback 退回 executor（逐条清单）+ notify coordinator（回流）；工件预审结论：approve → notify 回流 coordinator / revise → feedback 退回 coordinator（CONTRACT §7 D10）。
- **横向**：与 coordinator 讨论技术方案/审查结论，不是纯闸门。
