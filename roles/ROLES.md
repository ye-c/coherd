# 集群角色与协作契约（协作事实源）

> 路径：本文件安装于 `~/.config/coherd/ROLES.md`。

## 1. 角色职责表

三角色为**槽位**（实现可配置，具体 agent CLI 由 `COHERD_*_CMD` 决定，见 docs/configuration.md）。三者必须为**三个独立实例**——同一实例兼任多角 = 单 agent 自己写的自己审，违背角色分离设计。

| 槽位 | 角色 | 职责 |
|------|------|------|
| coordinator | 协调者 | 接收用户意图，拆解为任务分派；可与 reviewer 讨论技术方案/审查结论；整合并交付 |
| executor | 执行者 | 实现 coordinator 分派的任务，产出可验证结果；阻塞时向 coordinator 上报 |
| reviewer | 审查者 | 审查 executor 的产出（正确性/安全/可维护性）并跑验证；可与 coordinator 讨论 |

## 2. 通信协议

- agent 间用 `herdr agent prompt <name> "<消息>"` 通信；读取用 `herdr agent read <name>`。
- 发 prompt 不用 --wait/--timeout: 分派即发(fire-and-forget), 转 idle 等 peer 主动上报(§7)。--wait 超时路径会 abort-but-delivered, 重发致消息堆积/死循环; 需确认状态用 herdr agent read, 不重发。
- 防重复成环: 分派即发(fire-and-forget), 不盲目重发。疑似未达 → 先 herdr agent read 查对端上报/处理证据: 读到任何证据即停(对端已收); 确无证据才可重发, 同一任务重发上限 1 次; 仍无果 → 停止重发并上报 coordinator 仲裁, 不得无限重发。
- 每个集群的 herdr agent 名是 `${LABEL}-<role>`（如 `mycoherd-coordinator`），非裸单词；互寻址用完整名。
- 消息以 `[<role>]: ` 前缀开头 = 同级 agent 发言；无前缀 = 用户直接输入。
- 每个 pane 自动注入 `HERDR_WORKSPACE_ID` / `HERDR_TAB_ID` / `HERDR_PANE_ID`。
- 汇报对称义务：executor 完成/阻塞/需审查以 `[executor]:` 上报 coordinator；reviewer 审查结论（approve/revise）以 `[reviewer]:` 上报 coordinator；coordinator 整合交付以 `[coordinator]:` 上报用户。

## 3. 分派契约模板（A）

coordinator→executor 每条任务**必须**包含以下 4 字段，缺失即视为任务未定义完整：

| 字段 | 含义 | 反例（不合格） |
|------|------|----------------|
| objective | 目标：做什么 + 为什么 | “写个文档” |
| DoD 验收标准 | 可验证的完成定义（可测、可查） | “尽量做好” |
| 输出格式 | 产出物路径/结构/上报内容 | “完成后告诉我” |
| 工具边界 | 允许读/写哪些路径、禁用什么 | “随便弄” |

分派消息模板：

```
[coordinator]: 分派 <任务名>
- objective: <目标与理由>
- DoD: <可验证标准，逐条>
- 输出: <文件路径/消息结构>
- 边界: <允许读/写路径；禁止操作>
```

约定：字段缺失 → executor 先向 coordinator 补齐再动工；模糊分派导致的重复/遗漏由分派方负责。

## 4. 审查义务与循环（B）

reviewer **最小审查集**（每次审查必做）：
1. 跑验证命令（编译/测试/复现 DoD 场景）。
2. 三查：**正确性**（行为符合 DoD）/ **安全**（权限、秘密、危险命令）/ **可维护性**（复杂度、命名、注释）。
3. 结论二选一：`approve`（附理由）或 `revise`（附具体可执行问题清单）。

循环与终止：
- `approve` → coordinator 整合交付。
- `revise` → 退回 executor 修订 → 重新提交 reviewer。
- **revise 上限 2 轮**：仍不通过 → 升级 coordinator 仲裁（改判 / 拆任务 / 终止）。
- 角色分离是架构核心：同一推理路径既写码又自评必失败，reviewer 不得代改被审产出，问题一律退回 executor。

## 5. 工具白名单（C）

下表为行为级白名单，不绑定具体 CLI：各槽位自带工具集（由所用 agent 决定），白名单只约束行为边界；任务级边界（§3）与白名单冲突时**取交集**。

| 槽位 | 允许 | 禁止 |
|------|------|------|
| coordinator | 只读/检索类工具（拆解、分派、讨论、整合所需） | 直接编辑代码/写文件（除非明确授权） |
| executor | 完整代码编辑与运行工具 | 越出任务工具边界的写操作；改动配置/秘密文件 |
| reviewer | 只读审查 + 跑验证 | 直接修改被审产出（须退回 executor）；越过自己工具边界的操作 |

executor 槽位天然带写权限，建议在受控仓库/沙箱运行；权限收紧由用户 CLI 配置负责（同 reviewer 见 docs/reviewer.md）。

## 6. 规模缩放与防失控

- 简单任务（1–2 文件、低风险）→ coordinator 单点派 executor，可不启动 reviewer 全链路。
- 高风险 / 正确性敏感任务 → 必走 executor → reviewer → coordinator 全链路（§4）。
- 防失控：出现级联/循环/重复工作 → 任一 agent 可喊停并上报 coordinator；revise 超限见 §4 仲裁。

## 7. 事件驱动交接

- 基于 herdr idle/done 事件交接：上一环完成 → 下一环主动拉取（`herdr agent read`）。
- executor 完成 → 通知 coordinator 可审查/可交付；阻塞 → 上报阻塞原因与已尝试手段。

## 8. libero（辅助角色）

**定义**：libero 是手动加载的第 4 类角色（对照 §1 三槽位表；§1 表不变）。
- **是**：用户手动拉起的辅助角色，承接旁路/一次性/辅助需求——交叉复核、补上下文、问答。
- **不是**：coherd 拉起的槽位；不进集群握手、不持有主任务、不在主循环内。

**6 条防污染硬条款**（违反任一条即视为角色污染，须立即停用）：
1. 不持主任务：不接 coordinator→executor 主链任务；只接用户旁路需求或 coordinator 显式调派。
2. 不写主产物路径：不碰 executor 的输出。
3. 不出 approve/revise：审查判定权 reviewer 独占（§4），libero 只给观察/建议。
4. 不分派：分派权 coordinator 独占（§3），不向 executor 派任务。
5. 不自晋升：不得自称 coordinator/executor/reviewer。
6. 临时性：完即弃，不持跨轮状态，单向 [libero]: 回报。