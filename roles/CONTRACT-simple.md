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
| spec/plan 预审 coordinator → reviewer | **led 内部自审（两者同批）**（能力降级，见 §7） |
| libero 旁路管理（coordinator §8） | simple 模式无 libero 槽位；辅助角色不进本模式 |

角色名沿用 `${WS_SLUG}-<role>` 约定：`<ws>-led` / `<ws>-dev`（非裸单词）。CLI 按 `${ws}-` 前缀派生 role，不硬编码角色名，故无需新映射表。

## 1. 角色职责表

| 槽位 | 角色 | 职责 |
| ------ | ------ | ------ |
| led | 检查者（用户主交互） | 接收用户意图 → 拆解为任务分派；审 dev 产出（跑验证 + 五查）；自审 spec/plan；整合交付。**不写码**（工具白名单见 §5） |
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
| spec/plan 预审 | **无跨角色消息** | led 自审，spec 与 plan 同批（§7 D9） |

read 用 `herdr agent read <name>`，仅用于核对状态/查证据，不作轮询等待（`CONTRACT.md` §2）。

**通道作用域**：对端为集群内 peer（`${ws}-dev` / `${ws}-led`）时协作交互只用上表命令；对端为集群外 session 时用 `intercom`。通道选择、消息来源判定（`[<role>|<type>]:` / `**From <sender>**` / 两者皆无）、`intercom` 的内容/信号分离均沿用 `CONTRACT.md` §2，本文件不复述。

**批处理纪律**（同 `CONTRACT.md` §7）：一批票据 = 一条分派消息；同一收件人 60 秒内需要发 ≥2 条同类消息 → 合并为一条。每条消息 = 对端一次完整 agent turn，合并即省一次唤醒。

**省略对端与 ws**：`coherd feedback` / `notify` 的 peer 位在 simple 模式下可留空——CLI 按自身 role 反推唯一对端（led↔dev）；role 不在 led/dev 时 CLI 报 `缺 peer` 并不发送。省略 peer 时正文只能走 `-`（stdin）或 `--body-file`（不可再占 peer 位）。`--ws` 同理缺省取 `HERDR_WORKSPACE_ID` 小写（`coherd feedback` / `notify` / `task new` 一致），env 也未设时报错。

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
- **工件四层**：意图澄清 → 规格（What，`<id>.spec.md`，无路径/语言/库名）→ 方案（How，`<id>.plan.md`，与 spec 同标识 1:1，含现状差异 / 架构 / **改动文件白名单** / 迁移回滚）→ 任务。无规格不做方案，无方案不拆票。四键元数据手写：`id` / `kind`（spec 或 plan）/ `created_at`（`%Y-%m-%dT%H:%M:%SZ`）/ `parent_spec`；模板取 `~/.config/coherd/templates/`。tracker `parent_spec` 记 FK。**工件变更归 led**。
- **门禁字段**：tracker 可选 `gate`（单行命令，非必填）；`coherd task new --gate '<命令>'` 写入。执行语义同 `CONTRACT.md` §3：仓库根 + `bash -lc` + 继承环境，需净化环境自带 `env -u VAR ...`，不承诺跨机一致。工具层只校验格式。
- 分派消息指示 dev：完成后**直接交 led 审查**（一条 feedback，勿发第二条 notify）；改动限 plan 白名单。

## 4. 审查循环（led 自审版）

最小审查集（每次审查必做，顺序固定 = 五查）：

1. **确定性门禁**：tracker 带 `gate` 时先在仓库根以 `bash -lc` 继承环境跑该命令，通过才进入人判；不带则跳过。**字符串级判据**：命令含 `|`、`;`、`&`、`>`、`<`、`$(` 或反引号任一 → 判为复合命令，拒跑并上报（不靠肉眼判断）。**拒绝复合命令不构成沙箱**——门禁执行即信任 dev 提供的仓库代码。
2. **改动面越界**：比对实际改动与 plan 白名单；超出但无行为变更（纯新增测试、机械 import 修正）且交审已声明 → 放行；改变行为 → revise。
3. **规格忠实度**（task 带 `parent_spec` 时）：产出与 spec 决策逐条对照，偏离未入 spec = 不忠实。
4. **正确性**：行为符合 DoD（对照 dev 的 DoD 自检逐条核）。
5. **安全性与可维护性**：权限、秘密、危险命令、越界写；复杂度、命名、注释。

结论二选一：`approve`（附理由）或 `revise`（附具体可执行问题清单，每条：位置 + 问题 + 修法）。结论文件记明所走门禁分支与判据一句。

**门禁失败三类分流**（simple 模式无第三方，由 led 自行处置）：

1. **环境性失败**（依赖缺失、端口占用、无网络、权限不足）→ 修环境/补齐依赖后重跑，**不计返工轮次**；无法解决则 `coherd notify` 告知用户。
2. **门禁定义错误**（路径不存在、测试目标拼错、命令不可执行）→ led 修订 tracker 门禁后重跑，**不计返工轮次**。
3. **代码性失败**（命令可跑、语义正确、产出不满足）→ 判 `revise`，stdout/stderr 落盘为证据。

**自审豁免声明**：led 自审 spec/plan 与自审产出不违背「同一路径不得既写码又自评」——**led 不写码**，写方是 dev；故该自审属既有豁免，**不构成三角色模式的先例**。

循环与终止：

- `approve` → led **直接整合交付**（无回流消息）→ `coherd notify` 上报用户。
- `revise` → `coherd feedback` 退回 dev → dev 修订 → 重交。rev→dev→led 不经第三方。
- **revise 上限 2 轮**：仍不通过 → 三角色模式升级 coordinator 仲裁；**simple 模式无第三方可升级**，由 led 自仲裁（改判 / 拆任务 / 终止），并以 `coherd notify` 告知用户决策与理由。此为流程降级，显式声明。
- **不代改**：问题一律退回 dev；led 改被审产出 = 自审自己的修改，破坏角色分离。
- **DoD 语义变更归 led**：先更新 tracker，再以新分派明示 dev；**不得用 `revise:` 夹带需求变更**（H2 的信号级硬规则，见 `roles/dev.md`）。
- **规约漂移**：dev 以 `coherd feedback` 回传（受影响任务 + 现实阻碍 + 待修订假设）→ led 冻结任务、修订 spec/plan，回应三选一（改规格重派 / 降级替代 / 终止），禁止只回「收到」；spec 变更后既有 approve 作废，重新分派须声明 `重审 <任务名>：旧 approve <结论文件绝对路径> 因规格 <标识> 变更作废` + 新工件路径。
- 结论落盘 session 平铺 `<id>.<verdict>-<HHMMSS>.md`（verdict=approve/revise；秒戳到轮，与 `<id>.task.md` 同目录）——led 自审亦留证据链。

## 5. 工具白名单（行为级）

| 槽位 | 允许 | 禁止 |
| ------ | ------ | ------ |
| led | 只读/检索 + 跑验证（编译/测试/复现）；写协作产物（spec / tracker，经 `coherd task` CLI） | 直接编辑代码；改被审产出（须退回 dev）；越过任务工具边界 |
| dev | 完整代码编辑与运行工具 | 越出任务工具边界的写操作；改动配置/秘密文件 |

白名单为 `CONTRACT.md` §5 coordinator 行 + reviewer 行的并集；任务级边界（§3）与白名单冲突取交集。**能力分离默认不强制**：零配置路径不注入、不校验权限设置，边界靠契约与流程保障。simple 模式有写权限的槽位建议在受控仓库/沙箱运行。

**git 锁争用**：led 行为与 `CONTRACT.md` §5 coordinator/reviewer 行同（只读 git 命令带 `GIT_OPTIONAL_LOCKS=0`、不执行 git 写操作与删锁）；dev 行为与 executor 行同（独占 git 写操作与 `index.lock` 治理）。孤儿锁判据与四条处置顺序见 `CONTRACT.md` §5「git 锁争用」。

## 6. 启动握手

- **单 standby（D5）**：dev 启动后读本文件确认身份，以 `coherd notify <led> "standby"` 上报一次，随即**转 idle 待机**。
- led 侧：**被动接收** dev 的 standby，不回执、不数齐、不轮询；确认后转 idle，等用户意图。
- 握手单向、一次性、不触发 §2 回复义务。led 不检测 dev 状态；未收到上报不追究、不重发——沉默即故障信号，用户自然察觉。

## 7. 能力降级声明（D9 / R1）

simple 模式以"少一个 agent、少一轮通信"换取简易，代价**必须显式**：

- **R1 无独立第二意见**：无独立 reviewer —— spec/plan 预审、产出审查均由 led 自审。**不存在第三方复核**。用户选 simple 即接受此项；需要独立第二意见时切回三角色模式。（人类临时开的外部 session 不改变本条，见 §10。）
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

本文件与 `roles/led.md`、`roles/dev.md` 的**唯一事实源是 repo `roles/`**；repo → `~/.config/coherd/` 单向覆盖分发，禁止只改 `~/.config` 副本（`CONTRACT.md` §10）。镜像一致校验需含本模式 3 个文档 + `templates/` 目录逐文件。

## 10. 外部讨论方（人类临时开的外部 session）

- **定义**：人类在集群外另开的 session，与集群无角色关系：无 `[<role>|<type>]:` 标记、无 tracker、不在 §1 槽位表内。人类决定它是否存在、与谁对话。
- **通道**：`intercom`（`CONTRACT.md` §2 通道作用域表第二行）。
- **结论性质**：外部结论是**输入证据**，不构成 §4 的 `approve` / `revise` 判定，也不补齐 §7 R1 的独立第二意见缺口——不因开了外部 session 而获得「独立第二意见」；simple 模式仍按 R1 / R2 承担自证与单点风险。
- **意图重定向（写权不转移）**：人类关于写代码的直接指令恒定性为**分派意图**——led 接收后落盘 tracker 并分派 dev 执行，不自行代写；写/审分离（I1）为硬性不变量，口头授权未免除自写自审禁令。工件落盘归属按 §5 白名单，本条不重列。
- **对端感知**：引入外部讨论方时，led 以**一条** `coherd notify` 告知 dev：谁、讨论什么工件、是否触及 dev 当前任务边界。外部结论影响后续动作时走既有通道（新 `feedback` 分派或 `revise:` 退回），不直接改 dev 产出。
- **版本冻结（机检判据）**：某工件「在审中」= 在 `~/.config/coherd/sessions/**/*.task.md` 中搜该工件路径，命中文件的 frontmatter `status` 为 `pending` 或 `active`。在审期间该工件只读：led 若需修订，先 `coherd notify` 作废/挂起该 review 任务，落盘新版本后重新下派，禁止就地并发篡改；改动后以一条 `notify` 报 delta（文件 + 行号 + 一句原因）。
- **冲突处置**：外部结论与集群内审结论相反时，不自行取舍，一条消息报人类裁决。