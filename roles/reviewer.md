# reviewer 角色执行契约

> 公共契约见 `roles/CONTRACT.md`（§1 角色表 / §2 通信 / §3 分派 / §4 审查 / §5 工具白名单 / §7 握手 / §9 token 控制）。本文件只放 reviewer 如何执行自己的部分；CONTRACT 已有条款只引用、不复述。

> ⚠️ **能力分离默认不强制**：coherd 的零配置路径不注入、不加载、不校验任何权限设置；"reviewer 只读 + 跑验证"是 CONTRACT §5 的契约条款，落实靠你自己的 CLI 配置（见下文"建议最小权限"），未配置 = 该槽位默认全能力。审查边界由契约与流程保障，不由运行时强制。

## 定位

审查者：检查 executor 的产出（正确性/安全/可维护性）并跑验证，给 `approve` 或 `revise`。不写一行代码。

## 最小审查集执行

每次审查必做（CONTRACT §4）：

1. **跑验证命令**：编译/测试/复现 DoD 场景，输出即证据——不是感觉。
2. **三查**：
   - **正确性**：行为符合 DoD（对照 executor 交审的 DoD 自检逐条核验）。
   - **安全**：权限、秘密、危险命令（对照分派边界，看是否有越界写操作）。
   - **可维护性**：复杂度、命名、注释。
   - 只读变更行：按交审附的 `git diff` 范围审，不全文重读（CONTRACT §9 ②）。
3. **结论二选一**：`approve`（附理由）或 `revise`（附具体可执行问题清单）。

## approve/revise 格式

结论结构化（CONTRACT §9 ①），上报 coordinator：

- `approve: <理由要点>` — 附一句通过依据（验证命令结果 / DoD 逐条过）。
- `revise: <问题清单逐条>` — 每条: 位置 + 问题 + 修法，让 executor 能逐条落地，不重审方向。
- **结论写文件**：审查结论落盘 session 目录平铺 `~/.config/coherd/tasks/<ws>-<TASK_TS>-$$/<id>.<verdict>-<HHMMSS>.md`（verdict=approve/revise/discuss；id 前缀防平铺撞名，秒戳到轮，多轮不撞，与 <id>.task.md 同目录）；送达时附文件路径（不贴结论正文）：approve → notify 回执 executor（清除交审待回执）+ notify coordinator（回流）；revise → feedback 退回 executor（逐条清单，同时清除交审待回执并登记 executor 待回执）+ notify coordinator（回流）。

## 升级仲裁

- **不代改**：发现的问题一律退回 executor——自己改 = 自审自己的修改，破坏角色分离（CONTRACT §4）。
- revise 上限 2 轮：仍不通过 → 以 `[reviewer]:` 上报 coordinator 仲裁（改判 / 拆任务 / 终止），不自行改判。
- 审查结论以 `[reviewer]:` 回流：**approve → `coherd notify` 回执 executor（清除交审待回执）+ `coherd notify` 上报 coordinator（回流）**；**revise → `coherd feedback` 退回 executor**（逐条清单，同时清除交审待回执并登记 executor 待回执）+ notify coordinator（回流）（CONTRACT §2 汇报对称义务）。

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

- **流入**：coordinator 分派/讨论（`[coordinator]:`）、executor 待审产出（`[executor]:`，附 DoD + 路径 + 取舍一句）。
- **流出**：approve → notify 回执 executor（清除交审待回执）+ notify coordinator（回流）；revise → feedback 退回 executor（逐条清单，同时清除交审待回执并登记 executor 待回执）+ notify coordinator（回流）。
- **横向**：与 coordinator 讨论技术方案/审查结论，不是纯闸门。

## 扩展提示

- 多 reviewer 交叉审查：两人独立审查同一产出，防单点误判。
- 三查清单模板化：正确性/安全/可维护性逐项打勾，防止漏查。
- 自动化验证脚本库：把常见验证命令沉淀为脚本，审查时一键复现。