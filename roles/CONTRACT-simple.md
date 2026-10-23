# coherd 双角色简易模式契约（公共）

> 路径：本文件安装于 `~/.config/coherd/CONTRACT-simple.md`（与 `CONTRACT.md` 同目录）。
> **适用范围**：`coherd -s|--simple` 启动的双角色集群（`led` + `dev`）。三角色模式（coordinator / executor / reviewer）不受本文件影响，其权威契约仍是 `roles/CONTRACT.md`。
> **复用规则**：术语表、`[<role>|<type>]:` 标记注入机制、消息 body 格式、防重复成环、禁轮询/事件驱动铁律、token 控制、CLI 数据契约（`task`/`feedback`/`notify` 命令语义与 status 枚举含义）**逐条沿用 `CONTRACT.md`**，本文件不复述；范围内冲突以本文件为准（simple 专属差异）。
> per-role 执行细节：`roles/led.md` / `roles/dev.md`。dev 交审/revise/上报三段**语义变更**，见 `roles/dev.md` H1–H3，不得沿用 `roles/executor.md`。

## 0. 与三角色模式的差异（重映射总表）

| 原环节（三角色） | 双角色 |
| ------ | ------ |
| 用户意图流入 → coordinator | → `led` |
| 分派 coordinator → executor | `led` → `dev` |
| 交审 executor → reviewer | `dev` → `led` |
| 审查结论回流 reviewer → coordinator/executor | **消息消失**——led 既审又交付，同一 pane 内两动作，无跨甲方通知 |
| 整合交付 coordinator → 用户 | `led` → 用户 |
| spec 预审 coordinator → reviewer | **led 内部自审**（能力降级，见 §7） |
| libero 旁路管理（coordinator §8） | simple 模式无 libero 槽位；辅助角色不进本模式 |

角色名沿用 `${WS_SLUG}-<role>` 约定：`<ws>-led` / `<ws>-dev`（非裸单词）。CLI 按 `${ws}-` 前缀派生 role，不硬编码角色名，故无需新映射表。

## 1. 角色职责表

| 槽位 | 角色 | 职责 |
| ------ | ------ | ------ |
| led | 检查者（用户主交互） | 接收用户意图 → 拆解为任务分派；审 dev 产出（跑验证 + 三查/四查）；自审 spec；整合交付。**不写码**（工具白名单见 §5） |
| dev | 执行者 | 实现 led 分派的任务，产出可验证结果；阻塞上报 led。承担全部写操作 |

**角色分离铁律（不变量 I1）**：led 与 dev **必须为两个独立 agent 实例**。同一实例兼任 = 同一推理路径既写码又自审，禁止（`CONTRACT.md` §1）。led 不写码，写/审分离由 led↔dev 两个实例保证——合并 coordinator 与 reviewer 不违背该铁律。

## 2. 通信协议与环节→命令映射

协议本体（标记注入、body 格式、fire-and-forget、事件驱动、禁轮询）逐条沿用 `CONTRACT.md` §2；**命令名即语义（=标记名）**，agent 只写 body、不手写前缀。

| 环节 | 命令 | 回执语义 |
| ------ | ------ | ------ |
| led → dev 分派（4 字段） | `coherd feedback` | 期待回执（开工 ack / 阻塞上报） |
| led ↔ dev 讨论 | `coherd feedback` | 期待回执 |
| dev → led 交审 | `coherd feedback` | 期待回执（approve / revise）——**仅此一条，禁发第二条 notify**（H1） |
| led revise 退回 dev | `coherd feedback` | 期待回执（修订重交） |
| led 需求级变更分派 | `coherd feedback` | 先更新 tracker 再分派，不得借 `revise:` 夹带（H2） |
| dev 修订重交 | `coherd notify` | 单向 |
| dev 开工 ack | `coherd notify` | 单向，可选 |
| dev 阻塞上报 led | `coherd notify` | 单向，唯一路径（H3） |
| dev standby 握手 | `coherd notify` | 单向，一次性（§6） |
| led 交付 → 用户 | `coherd notify` | 单向 |
| 审查结论回流 | **不存在** | led 审完直接交付（差异总表） |
| spec 预审 | **无跨角色消息** | led 自审（§7 D9） |

read 用 `herdr agent read <name>`，仅用于核对状态/查证据，不作轮询等待（`CONTRACT.md` §2）。

**批处理纪律**（同 `CONTRACT.md` §7）：一批票据 = 一条分派消息；同一收件人 60 秒内需要发 ≥2 条同类消息 → 合并为一条。每条消息 = 对端一次完整 agent turn，合并即省一次唤醒。

## 3. 分派契约模板（4 字段）

led → dev 每条任务**必须**含以下 4 字段，缺失即任务未定义完整：

| 字段 | 含义 |
| ------ | ------ |
| objective | 目标：做什么 + 为什么 |
| DoD 验收标准 | 可验证的完成定义（可测、可查） |
| 输出格式 | 产出物路径/结构/上报内容 |
| 工具边界 | 允许读/写哪些路径、禁用什么 |

```
分派 <任务名>
- objective: <目标与理由>
- DoD: <可验证标准，逐条>
- 输出: <文件路径/消息结构>
- 边界: <允许读/写路径；禁止操作>
```

- 字段缺失 → dev 先向 led 补齐再动工；模糊分派导致的重复/遗漏由分派方（led）负责。
- 分派前 led 把 4 字段落盘 session 平铺 `<id>.task.md`（权威副本，路径与 schema 同 `CONTRACT.md` §3/CLI 数据契约），dev 契约上不可写。
- 复杂任务（走全链路判据）分派前 led 产 `<id>.spec.md`（决策清单 D1… + 架构 + 不变量/边界 + 测试决策；不含文件路径），tracker `parent_spec` 记 FK。**spec 变更归 led**。
- 分派消息指示 dev：完成后**直接交 led 审查**（一条 feedback，勿发第二条 notify）。

## 4. 审查循环（led 自审版）

最小审查集（每次审查必做）：

1. 跑验证命令（编译/测试/复现 DoD 场景），输出即证据。
2. 三查 + 忠实度轴（四查）：**正确性**（行为符合 DoD，对照 dev 的 DoD 自检逐条核）/ **安全**（权限、秘密、危险命令、越界写）/ **可维护性**（复杂度、命名、注释）/ **Spec 忠实度**（task 带 `parent_spec` 时：产出与 spec 决策逐条对照，偏离未入 spec = 不忠实）。
3. 结论二选一：`approve`（附理由）或 `revise`（附具体可执行问题清单，每条：位置 + 问题 + 修法）。

循环与终止：

- `approve` → led **直接整合交付**（无回流消息）→ `coherd notify` 上报用户。
- `revise` → `coherd feedback` 退回 dev → dev 修订 → 重交。rev→dev→led 不经第三方。
- **revise 上限 2 轮**：仍不通过 → 三角色模式升级 coordinator 仲裁；**simple 模式无第三方可升级**，由 led 自仲裁（改判 / 拆任务 / 终止），并以 `coherd notify` 告知用户决策与理由。此为流程降级，显式声明。
- **不代改**：问题一律退回 dev；led 改被审产出 = 自审自己的修改，破坏角色分离。
- **DoD 语义变更归 led**：先更新 tracker，再以新分派明示 dev；**不得用 `revise:` 夹带需求变更**（H2 的信号级硬规则，见 `roles/dev.md`）。
- 结论落盘 session 平铺 `<id>.<verdict>-<HHMMSS>.md`（verdict=approve/revise；秒戳到轮，与 `<id>.task.md` 同目录）——led 自审亦留证据链。

## 5. 工具白名单（行为级）

| 槽位 | 允许 | 禁止 |
| ------ | ------ | ------ |
| led | 只读/检索 + 跑验证（编译/测试/复现）；写协作产物（spec / tracker，经 `coherd task` CLI） | 直接编辑代码；改被审产出（须退回 dev）；越过任务工具边界 |
| dev | 完整代码编辑与运行工具 | 越出任务工具边界的写操作；改动配置/秘密文件 |

白名单为 `CONTRACT.md` §5 coordinator 行 + reviewer 行的并集；任务级边界（§3）与白名单冲突取交集。**能力分离默认不强制**：零配置路径不注入、不校验权限设置，边界靠契约与流程保障。simple 模式有写权限的槽位建议在受控仓库/沙箱运行。

## 6. 启动握手

- **单 standby（D5）**：dev 启动后读本文件确认身份，以 `coherd notify <led> "standby"` 上报一次，随即**转 idle 待机**。
- led 侧：**被动接收** dev 的 standby，不回执、不数齐、不轮询；确认后转 idle，等用户意图。
- 握手单向、一次性、不触发 §2 回复义务。led 不检测 dev 状态；未收到上报不追究、不重发——沉默即故障信号，用户自然察觉。

## 7. 能力降级声明（D9 / R1）

simple 模式以"少一个 agent、少一轮通信"换取简易，代价**必须显式**：

- **R1 无独立第二意见**：无独立 reviewer —— spec 预审、产出审查均由 led 自审。**不存在第三方复核**。用户选 simple 即接受此项；需要独立第二意见时切回三角色模式。
- **R2 分派与审查同源**：led 既定 DoD 又判 DoD → 自证风险。缓解：DoD 必须可测（§3 硬要求不变）；dev 交审须附 DoD 自检，led 逐条核验（非凭感觉）。**软缓解，非硬隔离**。
- **R3 单点**：led pane 挂 = 集群挂（与三角色模式 coordinator 挂同理，非新增风险）。
- **R4 用户误用**：用户可能把 led 当"全能 agent"直接让其写码。**led 不写码**（§5，沿 `CONTRACT.md` §5 coordinator 行）。
- **R5 流程降级**：revise 超限无第三方仲裁（§4）；无 libero 旁路槽位（差异总表）。

## 8. 不变量

- **I1 写/审分离**：led 与 dev 必为两个独立 agent 实例（§1）。
- **I2 CLI 不编排**：simple 模式复用现有 CLI **零改动**；禁止为角色决策改 CLI。
- **I3 隔离**：simple 模式不改变三角色模式任何行为；切模式只切 flag + brief + 布局。
- **I4 消息契约不变**：标记注入、feedback/notify 语义、body 格式逐条沿用。
- **I5 session 目录不变**：仍 `<ws>-<TASK_TS>-$$`，tracker/spec/verdict 文件命名不变。

## 9. 事实源与同步

本文件与 `roles/led.md`、`roles/dev.md` 的**唯一事实源是 repo `roles/`**；repo → `~/.config/coherd/` 单向覆盖分发，禁止只改 `~/.config` 副本（`CONTRACT.md` §10）。镜像一致校验需含本模式 3 个文档。