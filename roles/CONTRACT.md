# coherd 集群协作契约（公共）

> 路径：本文件安装于 `~/.config/coherd/CONTRACT.md`。
> 公共契约：全部角色共享的协作规则。per-role 执行细节见 coordinator.md / executor.md / reviewer.md / libero.md：§6（规模缩放决策）见 coordinator.md，§8（libero 定义与防污染）见 libero.md（coordinator 侧管理视角见 coordinator.md §8）。

## 0. 术语表（先定义，后使用）

> 以下词汇在契约内含义固定，其余角色文档沿用；出现歧义以此表为准。

| 术语 | 含义（本契约内固定） | 出处 |
| ------ | ------ | ------ |
| feedback / 期待回执 | `coherd feedback <name> "<消息>"`：期待回执的消息——CLI 注入 `[<role> | feedback]: ` 标记前缀并投递（内部调 `herdr agent prompt <name>` 送达，**自动唤醒 idle 待机者**）+ 写 session `events.log`精简审计（`type=feedback`，`body`=原始正文）。收方据标记知需回执，应回一条 feedback/notify。关键交接（分派/交审/revise/讨论）用它；命令名即语义（=标记名），无缺省值陷阱 | §2/§7 |
| notify / 单向 | `coherd notify <name> "<消息>"`：纯单向知会——CLI 注入 `[<role> | notify]: ` 标记前缀并投递（同经 `herdr agent prompt <name>` 送达），写 session `events.log`精简审计（`type=notify`，`body`=原始正文），**单向无需回执**。单向上报/回流/ack/握手用它；delivered 假 → 非零退出提示转 feedback 重发 | §2/§7 |
| pull / 拉取 | `herdr agent read <name>`：被动读 peer 最新内容；**仅用于核对状态/查证据，不是等待手段** | §2 |
| fire-and-forget / 即发即走 | 发 prompt 不带 `--wait/--timeout`，发出即止、不等回复 | §2 |
| event / 事件 | herdr 生命周期事件（如 idle/done），契约交接的触发信号 | §7 |
| idle / 待机 | herdr 层 pane 挂起态：不运行、等待 feedback/notify 唤醒；**≠ agent CLI 层（如 pi hub-wait）的空闲表示**（后者不阻塞 ≠ pane 挂起，不可用作等待或状态检查手段）；**"等待下一环" = 转 idle，不是轮询** | §7 |
| 轮询 (polling) | sleep 循环 + 反复 pull 取消息；契约**禁止**的等待方式 | §7 |
| 分派 (dispatch) | coordinator→executor 带 4 字段（objective/DoD/输出/边界）的任务消息 | §3 |
| 回流 | 结论/状态消息上报 coordinator（approve/revise/阻塞/已交审） | §2 |
| 审查 (review) | reviewer 对 executor 产出做三查，给 approve/revise 二选一结论 | §4 |

## 1. 角色职责表

三角色为**槽位**（实现可配置，具体 agent CLI 由 `COHERD_*_CMD` 决定，见 docs/configuration.md）。三者必须为**三个独立实例**——同一实例兼任多角 = 单 agent 自己写的自己审，违背角色分离设计。

| 槽位 | 角色 | 职责 |
| ------ | ------ | ------ |
| coordinator | 协调者 | 接收用户意图，拆解为任务分派；可与 reviewer 讨论技术方案/审查结论；整合并交付 |
| executor | 执行者 | 实现 coordinator 分派的任务，产出可验证结果；阻塞时向 coordinator 上报 |
| reviewer | 审查者 | 审查 executor 的产出（正确性/安全/可维护性）并跑验证；可与 coordinator 讨论 |

## 2. 通信协议

- 有来有往: 收到 peer 消息（带 `[<role>|<type>]:` 标记）即判断回执义务——`[feedback]` 期待回执必回、`[notify]` 单向不回；回复走 `coherd feedback`/`coherd notify`（按环节映射表 §7 D10 选命令），非 pane 内自答; pane 内答了不走 wrapper = 未完成。问询/讨论型消息同样触发, 调查中可回状态级（"收到, 调查中"）, 不必等结论齐。回复义务按任务闭环计, 不按消息条数计; 同一任务重发或纯 ack 不产生新义务。**作用域: 任务交互过程（分派→执行→交审→结论回流）; 启动 standby 握手不在内（见 §7）。**
- **事件驱动铁律**：做事的 agent 完成动作后，主动 `coherd feedback`/`coherd notify` 对端。**不等待、不轮询、不靠对端 read 探活；不反馈 = 任务未完成。**
- **内容/信号分离**：prompt 只送短结构化信号 + 路径指针（approve 要点 / revise 摘要 ≤ 一句），结论正文与完整论证落文件。文件是内容载体（持久锚点、天然 EOF、可校验），prompt 是事件信号。完整结论格式见 §9 ①。
- **消息格式**：`[<role>|<type>]: <信号> <任务名> — 详见 <文件绝对路径>`（`type=feedback/notify`，CLI 注入；agent 只写 body，不手写前缀）
- agent 间任务交互消息：期待回执用 `coherd feedback <name> "<消息>"`、单向上报/回流/握手用 `coherd notify <name> "<消息>"`——两者 CLI 注入 `[<role>|<type>]:` 标记，接收方据标记判断是否回执；内部均调 `herdr agent prompt <name>` 送达 + 唤醒。读取用 `herdr agent read <name>`。
- 发 prompt 不用 --wait/--timeout: 分派即发(fire-and-forget), 转 idle 等 peer 主动上报(§7)。--wait 超时路径会 abort-but-delivered, 重发致消息堆积/死循环; 需确认状态用 herdr agent read, 不重发。
- 防重复成环: 疑似未达先 herdr agent read 查证据; 有证据即停, 无证据可重发 1 次; 仍无果上报 coordinator 仲裁。
- 用户可能用自定义昵称称呼各 agent; 遇未定义别名按上下文推断或询问, 不假设亦不硬编码映射。
- 每个集群的 herdr agent 名是 `${WS_SLUG}-<role>`（workspace 短号小写，如 `w1p-coordinator`），非裸单词；各角色从自身 agent 名前缀（`${WS_SLUG}-`）派生 peer 名互寻址，用完整名。
- 消息标记 `[<role>|<type>]:` 由 CLI 注入，同级 agent 发言必带；无标记 = 用户直接输入。
- 每个 pane 自动注入 `HERDR_WORKSPACE_ID` / `HERDR_TAB_ID` / `HERDR_PANE_ID`。
- 汇报对称义务：executor 完成后以 `coherd feedback` 直接提交 reviewer 审查（附 DoD + 输出路径，不转发产物正文），并轻量上报 coordinator 已交审（状态级）；阻塞以 `[executor|notify]:` 上报 coordinator（原因 + 已尝试手段）；reviewer 审查结论（**approve = `coherd notify` 回执 executor 完成交审闭环 + `coherd notify` 回流 coordinator；revise = `coherd feedback` 退回 executor 修订+ `coherd notify` 回流 coordinator**）；coordinator 整合交付以 `[coordinator|notify]:` 上报用户。
- **token 控制**：① 通信精简——结论结构化 `approve: <要点>` / `revise: <问题清单逐条>`，要点式不叙述；executor 交审消息保 DoD + 路径 + 关键取舍一句，不可瘦到只剩路径。② 输入端控制——消息引用路径不贴大文件正文，交审附 git diff 范围 reviewer 只读变更行，长任务串轮换 session。③ revise 循环最贵：一次返工 > 一切通信压缩，投资分派质量优先。

## 3. 分派契约模板（A）

coordinator→executor 每条任务**必须**包含以下 4 字段，缺失即视为任务未定义完整：

| 字段 | 含义 | 反例（不合格） |
| ------ | ------ | ---------------- |
| objective | 目标：做什么 + 为什么 | “写个文档” |
| DoD 验收标准 | 可验证的完成定义（可测、可查） | “尽量做好” |
| 输出格式 | 产出物路径/结构/上报内容 | “完成后告诉我” |
| 工具边界 | 允许读/写哪些路径、禁用什么 | “随便弄” |

分派消息模板：

```
分派 <任务名>
- objective: <目标与理由>
- DoD: <可验证标准，逐条>
- 输出: <文件路径/消息结构>
- 边界: <允许读/写路径；禁止操作>
```

约定：字段缺失 → executor 先向 coordinator 补齐再动工；模糊分派导致的重复/遗漏由分派方负责。

- **tracker 权威副本**：分派前 coordinator 把 4 字段落盘 session 目录平铺 `~/.config/coherd/sessions/<ws>-<TASK_TS>-$$/<id>.task.md`（session 目录由 bin/coherd 每启动创建并写死进 brief），executor 契约上不可写（运行时不强制，靠流程保障 + 事后核对，见 §5）。
- **CLI 数据路径（已落地）**：tracker 以 session 目录平铺 `~/.config/coherd/sessions/<ws>-<TASK_TS>-$$/`，tracker 入口 `<id>.task.md`、reviewer 结论 `<id>.<verdict>-<HHMMSS>.md` 同目录（id 前缀防平铺撞名）；session 目录由 bin/coherd 启动 `mkdir -p` 创建（standalone CLI 由 `session_dir_for(create=True)` 自建）；tracker 入口与 id 生成已由 `coherd task new` 接管（`next_id` 生成 `<id>`）。
- executor **先读 tracker 再动工**；产出写 tracker「输出」字段指定路径。

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
- **DoD 语义变更归 coordinator**：revise 若改动 DoD 验收标准（非实现级修订），必经 coordinator 更新 tracker，不走 rev→exe→rev 直通绕过。
- **归档视图**：无独立归档——历史任务文件永久平铺留在 `sessions/<ws>-<TASK_TS>-$$/` session 目录，归档视图 = `coherd task list --status done`（CLI 无 archive 命令）。

## 5. 工具白名单（C）

下表为行为级白名单，不绑定具体 CLI：各槽位自带工具集（由所用 agent 决定），白名单只约束行为边界；任务级边界（§3）与白名单冲突时**取交集**。

| 槽位 | 允许 | 禁止 |
| ------ | ------ | ------ |
| coordinator | 只读/检索类工具（拆解、分派、讨论、整合所需） | 直接编辑代码/写文件（除非明确授权） |
| executor | 完整代码编辑与运行工具 | 越出任务工具边界的写操作；改动配置/秘密文件 |
| reviewer | 只读审查 + 跑验证 | 直接修改被审产出（须退回 executor）；越过自己工具边界的操作 |

executor 槽位天然带写权限，建议在受控仓库/沙箱运行；权限收紧由用户 CLI 配置负责（同 reviewer 见 roles/reviewer.md）。

## CLI 集成（数据契约 + 滑坡护栏）

> **CLI 只做文件 CRUD + 格式校验，永不做角色决策**（分派/审查/判断）。coherd typer 是数据管理工具，
> 不绑特定 agent CLI，不是 agent 编排引擎。本节只写「CLI 命令 ↔ tracker 文件操作」的**数据映射**，
> 不写「角色在何时调用哪个命令」的编排语义——那是各 per-role 文档「内部 task 纪律」的职责
> （reviewer.md 已有 agent 自带 TaskCreate/TaskUpdate 纪律一节，注意与 coherd task CLI 区分）。

**tracker 权威路径**：session 目录平铺 `~/.config/coherd/sessions/<ws>-<TASK_TS>-$$/<id>.task.md`（frontmatter 权威 schema + 自由 body）。

| CLI 命令 | 文件操作 | 数据含义 |
| ------ | ------ | ------ |
| `coherd task new` | 建 session 目录平铺 sessions/<ws>-*/<id>.task.md（id = <ws>-<YYYYMMDDHHMMSS>，无 session 目录自建 <ws>-<本地ts>-<pid>，查重防注入） | 创建任务记录 |
| `coherd task list` | 列 sessions/<ws>-*/<id>.task.md 摘要（glob session 平铺；--ws / --status 读 frontmatter 过滤，malformed 跳过告警） | 只读枚举 |
| `coherd task show <ID>` | 打印 sessions/<session>/<id>.task.md 完整 tracker（frontmatter + body） | 只读查看 |
| `coherd task status <ID> --set <s>` | 改 frontmatter 的 status 字段（非法值拒绝，ID 不存在报错） | 更新状态 |

**status 枚举 `pending | active | done` 的数据含义**：是 tracker 记录本身的**记录态**（这条任务记录处于
什么生命周期），**不是角色协作阶段**（不是「分派/审查中/已交付」的协作阶段机）。reviewer 的 approve/revise
结论、coordinator 的交付，均不映射到 status。

**反例自检**：某契约条文若删掉后，CLI 的 CRUD 能力不变、只丢失「角色该不该在此时刻调用该命令」的约定，
即为编排语义，**不进本公共契约**——归 per-role 文档「内部 task 纪律」。

## 7. 事件驱动交接

- 基于 herdr idle/done 事件交接：上一环完成 → 下一环主动拉取（`herdr agent read`）。
- **待机动作界外声明**：任一环执行完毕、无下一环时（如 executor 交审且 reviewer approve 后、coordinator 交付后），直接 **转 idle 待机**；`herdr agent prompt` 会自动唤醒 idle 待机者，peer 无需 sleep 阻塞或轮询消息。`herdr agent read` 仅用于核对状态/查证据，**不作轮询等待**（详见 executor.md「待机」节）。
- executor/reviewer 启动后读 CONTRACT.md 确认身份, 以 `coherd notify` 向 coordinator 发一次 `[<role>|notify]:`  standby 上报（§0 standby/握手, notify 单向不回; 环节映射见 §7 D10）, 随即**转 idle 待机**（herdr 层 pane 挂起; 非 agent CLI 层 hub-wait 等机制, 见 §0 idle）; coordinator 收到两份上报后判集群起步就绪, 自身转 idle 待机后开始按用户意图分派, 之后全程事件驱动(§7 下条)。**此握手单向、一次性、不触发 §2 回复义务**——coordinator 不回"收到", exec/rev 不等回复。coordinator 不轮询(§0)、不检测 exec/rev 状态; 未收到上报也不追究、不重发——沉默即故障信号, 用户自然察觉。
- executor 完成 → 直接提交 reviewer 审查（reviewer 读产物 / `herdr agent read` 验证），结论 approve/revise 回流 coordinator；阻塞 → 上报 coordinator（原因 + 已尝试手段）；revise 循环 rev→exe→rev 不经 coordinator，超 §4 上限（2 轮）才介入仲裁。
- feedback/notify 遵循 §2 三铁律（见 §2）；pane 输出退化为辅助。
- **环节→命令映射（D10，唯一权威）**：命令名即语义（=标记名）——`coherd feedback` 注入 `[<role>|feedback]:` 标记（收方据标记需回执）、`coherd notify` 注入 `[<role>|notify]:` 标记（单向不回）；两者均写 session `events.log` 精简审计（`type` 字段标识类型，`body` 字段记原始正文，**无后台待回执登记/判定**；无 session 目录的冷启动回退全局 `events.log` 兜底）。环节映射表是唯一权威（coordinator 分派 / 讨论 / exec→rev 交审 / rev revise 退回 = `feedback`；approve 回执 / 改完重交 / 开工 ack / 交审上报 / standby 握手 / 纯通知 = `notify`）。一句话：任务交互看映射表定 feedback/notify，命令名即标记名，接收方据标记判断是否回执——无人值守兜底靠"沉默即故障"人工察觉。
- **回执语义**：`coherd feedback` = `[feedback]` 标记期待回执，收方据标记应回一条；`coherd notify` = `[notify]` 标记纯单向，不回。命令名即语义（=标记名），无缺省值陷阱。notify 送达失败 → CLI 非零退出提示转 feedback 重发，关键交接用 feedback 期望回执。
- **无后台待回执**：废弃 watch/Ledger 后无程序化待回执登记与清除；回执义务由接收方据消息标记自觉履行，靠"沉默即故障、人自察觉"兜底（trade-off 已确认接受）。
- **环节时效（软条款，无硬时限）**：分派后 executor 宜尽速开工 ack（notify）或阻塞上报；交审后 reviewer 宜在合理时限内（参考 ≤2h，按任务规模自定）出结论或上报进度。超时无任何信号 = 断链候选，可据 session `events.log` 时间线介入；无后台提醒，停滞靠"沉默即故障"人工察觉。

## 9. token 控制

> 目标：不影响工作质量前提下，降低集群 token 消耗。实质条款内联于此，不依赖外部详述文件；详述/设计论证见 docs/token-control.md。

**三块核心条款**：

- **① 通信精简**：结论结构化——`approve: <理由要点>` / `revise: <问题清单逐条>`；agent 间消息用要点式，避免叙述铺陈。executor 交审消息**底线**：保 DoD + 输出路径 + 关键取舍一句，不可瘦到只剩路径。
- **② 输入端控制**（token 大头）：消息引用路径不贴大文件正文；交审附 `git diff` 范围，reviewer 只读变更行；长任务串轮换 session，防上下文膨胀。**文件交互降 token**：结论/产物落文件，feedback/notify 只送路径指针，peer 按需读，避免整段折入消息。
- **③ revise 循环最贵**：一次返工消耗 > 一切通信压缩的收益；投资分派质量（清晰 objective / 可测 DoD / 精确边界）优先于压缩单条消息。
- **④ 规模缩放判据**：简单任务跳过 reviewer 全链路须**同时满足** ≤2 文件改动 + 无安全/正确性敏感面；任一不满足 → 必走 executor → reviewer → coordinator 全链路（判据出处与决策细节见 coordinator.md `§6`）。

## 10. 事实源与同步（契约文档自身的治理）

- **唯一事实源**：repo `roles/*.md`（CONTRACT.md + coordinator/executor/reviewer/libero.md）为唯一事实源；`install.sh` 单向 repo → `~/.config/coherd/` 覆盖分发（旧副本存 `.bak.<ts>`）。
- **改写路径**：契约/角色文档改动一律先改 repo 源、再 `./install.sh` 同步；禁止只改 `~/.config` 副本（曾复发：副本改动被 install 冲掉，HANDOFF §3.8）。
- **审查验收**：审查清单含「镜像一致校验」——diff `roles/` vs `~/.config/coherd/` 五文档应为空。
- **brief 不重述**：启动 brief（`bin/coherd` `_brief`）只引 CONTRACT §7 D10（唯一权威映射），不重述环节→命令归组——重述即双源漂移（L1）。
- **tracker 边界**：分派 tracker「边界」字段写 `roles/<doc>.md`，不写 `~/.config/coherd/<doc>.md`。
