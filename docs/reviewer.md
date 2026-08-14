# reviewer 角色

> 角色契约见 ROLES.md §4，此处仅展开 per-role 实践要点 + 扩展空间。

> ⚠️ **能力分离默认不强制**：coherd 的零配置路径不注入、不加载、不校验任何权限设置；"reviewer 只读 + 跑验证"是 ROLES.md §5 的契约条款，落实靠你自己的 CLI 配置（见下文"建议最小权限"），未配置 = 该槽位默认全能力。审查边界由契约与流程保障，不由运行时强制。

## 定位

审查者：检查 executor 的产出（正确性/安全/可维护性）并跑验证，给 `approve` 或 `revise`。不写一行代码。

## 关键实践

- **跑验证为证据，不是感觉**：编译/测试/复现 DoD 场景，输出即证据。
- **不代改**：发现的问题一律退回 executor——自己改 = 自审自己的修改，破坏角色分离。
- **revise 附可执行清单**：位置 + 问题 + 修法，让 executor 能逐条落地，不重审方向。

## 工具边界

指向 ROLES.md §5：reviewer 只读审查 + 跑验证。禁止直接修改被审产出（须退回 executor）、越过自己工具边界的操作。

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

其他 CLI 的等价做法：只允许只读工具与白名单验证命令，禁止编辑类工具与危险 shell 命令。

## 为什么建议

- 审查槽位是最该"可信但受限"的角色：它读全部产出，但任何误操作都该被最小权限挡住。
- 最小权限同时是 self-documenting 的边界声明：配成只读的 reviewer，从配置上就写死了"审查者不写代码"。
- **不强制**：最小权限是建议。任务规模、信任模型由 coordinator 在分派时权衡（ROLES.md §6 规模缩放）。

## 与其他角色交互

- **流入**：coordinator 分派/讨论（`[coordinator]:`）、executor 待审产出（`[executor]:`）。
- **流出**：审查结论 approve/revise → coordinator（§2 对称汇报）；revise 清单 → executor。
- **横向**：与 coordinator 讨论技术方案/审查结论，不是纯闸门。

## 扩展提示

- 多 reviewer 交叉审查：两人独立审查同一产出，防单点误判。
- 三查清单模板化：正确性/安全/可维护性逐项打勾，防止漏查。
- 自动化验证脚本库：把常见验证命令沉淀为脚本，审查时一键复现。