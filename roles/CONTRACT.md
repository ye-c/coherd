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
| 回流 | 结论/状态消息上报 coordinator（approve/revise/阻塞） | §2 |
| 审查 (review) | reviewer 对 executor 产出按固定顺序做五查（门禁 → 越界 → 忠实度 → 正确性、安全与可维护性），给 approve/revise 二选一结论 | §4 |
| spec / 规格 | coordinator 产的 What 层权威工件，落平铺 `<id>.spec.md`：行为契约、领域模型、不变量、边界与非目标、决策清单（命名引用，如 D1）、验收标准；**不含文件路径、语言、库名**。与 plan 一一对应且共用同一标识；executor 实现与 reviewer 审查的共同事实源，tracker 以 `parent_spec` FK 追溯 | §3 |
| plan / 方案 | spec 对应的唯一 How 层工件（1:1，共用同一标识，落平铺 `<id>.plan.md`）：现状差异分析、架构调整、**改动文件白名单**、迁移与回滚；executor 改动面的唯一权威 | §3 |
| gate / 门禁 | 任务记录可携带的**单行**验证命令（非必填）；执行语义固定为仓库根 + `bash -lc` + 继承环境，只承诺本机可执行。reviewer 审查第一步先跑，非零退出按三类分流 | §3/§4 |
| drift / 规约漂移 | executor 发现 plan 的假设不成立（非环境问题）时回传的**需回执**信号（受影响任务 + 现实阻碍 + 待修订假设）；coordinator 必须三选一回应：改规格重派 / 降级替代 / 终止 | §4 |

## 1. 角色职责表

三角色为**槽位**（实现可配置，具体 agent CLI 由 `COHERD_*_CMD` 决定，见 docs/configuration.md）。三者必须为**三个独立实例**——同一实例兼任多角 = 单 agent 自己写的自己审，违背角色分离设计。

| 槽位 | 角色 | 职责 |
| ------ | ------ | ------ |
| coordinator | 协调者 | 接收用户意图，拆解为任务分派；可与 reviewer 讨论技术方案/审查结论；整合并交付 |
| executor | 执行者 | 实现 coordinator 分派的任务，产出可验证结果；阻塞时向 coordinator 上报 |
| reviewer | 审查者 | 按固定顺序五查 executor 的产出（门禁 → 越界 → 忠实度 → 正确性、安全与可维护性）并跑验证；可与 coordinator 讨论 |

## 2. 通信协议

- 有来有往: 收到 peer 消息（带 `[<role>|<type>]:` 标记）即判断回执义务——`[feedback]` 期待回执必回、`[notify]` 单向不回；回复走 `coherd feedback`/`coherd notify`（按环节映射表 §7 D10 选命令），非 pane 内自答; pane 内答了不走 wrapper = 未完成。问询/讨论型消息同样触发, 调查中可回状态级（"收到, 调查中"）, 不必等结论齐。回复义务按任务闭环计, 不按消息条数计; 同一任务重发或纯 ack 不产生新义务。**作用域: 任务交互过程（分派→执行→交审→结论回流）; 启动 standby 握手不在内（见 §7）。**
- **事件驱动铁律**：做事的 agent 完成动作后，主动 `coherd feedback`/`coherd notify` 对端。**不等待、不轮询、不靠对端 read 探活；不反馈 = 任务未完成。**
- **内容/信号分离**：prompt 只送短结构化信号 + 路径指针（approve 要点 / revise 摘要 ≤ 一句），结论正文与完整论证落文件。文件是内容载体（持久锚点、天然 EOF、可校验），prompt 是事件信号。完整结论格式见 §9 ①。
- **消息正文（body）格式**：`<信号> <任务名> — 详见 <文件绝对路径>`（信号如 `分派`/`交审`/`approve:`/`revise:`）。agent 只写 body，**前缀 `[<role>|<type>]:` 是 CLI 私有注入物，agent 不得手写**——正文以 `[` 开头一律视为自造前缀，CLI 直接拒绝。所见消息形如 `[executor|notify]: 交审 x — 详见 /path`，是注入后的最终形态，非写作模板
- agent 间任务交互消息：期待回执用 `coherd feedback <name> "<消息>"`、单向上报/回流/握手用 `coherd notify <name> "<消息>"`——两者 CLI 注入 `[<role>|<type>]:` 标记，接收方据标记判断是否回执；内部均调 `herdr agent prompt <name>` 送达 + 唤醒。读取用 `herdr agent read <name>`。
- 发 prompt 不用 --wait/--timeout: 分派即发(fire-and-forget), 转 idle 等 peer 主动上报(§7)。--wait 超时路径会 abort-but-delivered, 重发致消息堆积/死循环; 需确认状态用 herdr agent read, 不重发。
- 防重复成环: 疑似未达先 herdr agent read 查证据; 有证据即停, 无证据可重发 1 次; 仍无果上报 coordinator 仲裁。
- 用户可能用自定义昵称称呼各 agent; 遇未定义别名按上下文推断或询问, 不假设亦不硬编码映射。
- 每个集群的 herdr agent 名是 `${WS_SLUG}-<role>`（workspace 短号小写，如 `w1p-coordinator`），非裸单词；各角色从自身 agent 名前缀（`${WS_SLUG}-`）派生 peer 名互寻址，用完整名。
- 消息标记 `[<role>|<type>]:` 由 CLI 注入（命令名即标记名）；agent 只写 body，不手写前缀（见上文 body 格式）。无标记消息的来源判定见本节「消息来源判定」条；检测到正文自造前缀 → CLI 拒发。
- 每个 pane 自动注入 `HERDR_WORKSPACE_ID` / `HERDR_TAB_ID` / `HERDR_PANE_ID`。
- 汇报对称义务：executor 完成后以 `coherd feedback` 直接提交 reviewer 审查（附 DoD + 输出路径，不转发产物正文），交审后即转 idle，**不再另发交审预告上报**（coordinator 从 reviewer 的结论回流得知结果，第二份预告无新信息）；阻塞以 `coherd notify` 上报 coordinator（原因 + 已尝试手段）；reviewer 审查结论（**approve = `coherd notify` 只发 coordinator（单收件人，唯一权威回流）；revise = `coherd feedback` 退回 executor 修订 + `coherd notify` 回流 coordinator**）；approve 若附带**需要 executor 动手的可执行 nit**，把该 nit 用 `coherd feedback` 单独发 executor，**不重发第二条 approve**；executor 收到 approve 后**不回 ack**（下一步是等下一票分派，ack 无新信息）；spec/plan 预审回流同实现审查（**approve = `coherd notify` 回流 coordinator 放行；revise = `coherd feedback` 退回 coordinator 修订**，spec 变更归 coordinator，见 §4）；coordinator 整合交付以 `coherd notify` 上报用户。
- **token 控制**：① 通信精简——结论结构化 `approve: <要点>` / `revise: <问题清单逐条>`，要点式不叙述；executor 交审消息**正文 ≤ 400 字**（不含 DoD 逐条勾选清单——每条一行 `✓/✗` 不展开），必含 `交审 <任务名>` + DoD 逐条 ✓/✗ + 产物绝对路径 + `git diff` 范围 + 关键取舍**一句**；超出 400 字的内容**必须落文件**，消息只送路径指针。**合并 N 票时按票计：每票 ≤400 字，合并消息总上限 = 400 × N**（DoD 勾选清单同样不计入）；reviewer 批量审汇总消息同理：每票一行，按票计。② 输入端控制——消息引用路径不贴大文件正文，交审附 git diff 范围 reviewer 只读变更行，长任务串轮换 session。③ revise 循环最贵：一次返工 > 一切通信压缩，投资分派质量优先。

**通道作用域**：通道按对端身份确定。

| 对端 | 通道 | 该通道的既成事实 |
| ------ | ------ | ------ |
| 集群内 peer（agent 全名形如 `${WS_SLUG}-<role>`） | `coherd feedback` / `coherd notify` | 注入 `[<role>|<type>]:` 标记；写 session `events.log` 一行审计；送达调 `herdr agent prompt <name>`，故对端必须是 herdr 托管 agent（名字不存在时该命令退出码 1、消息不进对端） |
| 集群外 pi/omp session（即装载 `pi-intercom` 扩展的 session） | `intercom`（`ask` 的适用条件见全局 `AGENTS.md`） | pi 扩展 + 本机 broker；未装载该扩展的 session 收发均不可达；不注入 coherd 标记、不写 `events.log`；收到的消息带 `**From <sender>**` 头 |
| 集群外非 pi/omp agent | `herdr agent prompt <name> "<msg>"`，或 `coherd feedback/notify <裸名>`（裸名不做 `${ws}-` 前缀校验，放行） | 后者同样注入标记并记审计；对端不认标记时，标记退化为正文前缀 |

- **消息来源判定**（只取前缀/头，不取正文）：带 `[<role>|<type>]:` = 集群内 peer 任务消息；带 `**From <sender>**` 头 = 集群外 session 经 intercom 发来（来源是该 session，不是本地终端用户）；两者皆无 = 本地终端用户直接输入。
- **跨通道发送的后果**：集群内 peer 消息走 intercom → 正文无标记，回执义务判定失效且 `events.log` 无该条记录；集群外 session 消息走 `coherd feedback` → 带标记但无 agent 按标记回执，审计行存在而回执不会出现。
- **与外部规则的边界**：本契约的通道规定只覆盖集群内 peer。集群外对端的通道不在本契约范围内，由该 session 所在环境的规则决定（如全局 `AGENTS.md`）。集群内 peer 之间所有协作交互走 `coherd feedback` / `coherd notify`（无标记 = 回执义务丢失、审计断链）。
- `intercom` 通道同样适用「内容/信号分离」：大段论证与草案正文落文件，消息只送路径与结论；不设 400 字上限（该上限属本节 token 控制条，只覆盖集群内交审消息）。

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

- **工件四层与上游权威**：意图澄清 → 规格（What）→ 方案（How）→ 任务（Action），层层有门禁：无规格不做方案，无方案不拆票，无票据不写码。规格与方案**一一对应且共用同一标识**，落平铺 `<id>.spec.md` / `<id>.plan.md`（id 同 task id 格式）；任务只持 `parent_spec` 一个上游指针，不新增方案指针。spec/plan 是 executor 实现与 reviewer 审查的共同事实源；ticket = 4 字段垂直切片（可独立验证），与 spec/plan 冲突或超出处**以 spec 为准**（工件变更归 coordinator，见 §4）。触发判据与产物结构见 coordinator.md「spec 环节」。

- **spec 内容红线**：规格只讲行为契约、领域模型、不变量、边界与非目标、决策清单、验收标准；**不得出现具体文件路径、编程语言、第三方库名**。路径唯一归属方案的白名单。

- **plan 必填改动面**：现状差异分析（现有 vs 目标）、架构调整说明、**改动文件白名单**（新增/修改 + 影响范围）、迁移与回滚。executor 只改白名单内文件，越界按 §4 以行为判定。

- **工件元数据四键**：spec 与 plan 文件头固定四键——`id` / `kind`（`spec` 或 `plan`）/ `created_at`（`%Y-%m-%dT%H:%M:%SZ`）/ `parent_spec`（plan 填同标识 spec id，spec 留空串）。由 coordinator 手写遵守，**工具层不解析不校验**。

- **tracker 权威副本**：分派前 coordinator 把 4 字段落盘 session 目录平铺 `~/.config/coherd/sessions/<ws>-<TASK_TS>-$$/<id>.task.md`（session 目录由 bin/coherd 每启动创建并写死进 brief），executor 契约上不可写（运行时不强制，靠流程保障 + 事后核对，见 §5）。
- **CLI 数据路径**：tracker 以 session 目录平铺 `~/.config/coherd/sessions/<ws>-<TASK_TS>-$$/`，tracker 入口 `<id>.task.md`、reviewer 结论 `<id>.<verdict>-<HHMMSS>.md` 同目录（id 前缀防平铺撞名）；session 目录由 bin/coherd 启动 `mkdir -p` 创建（standalone CLI 由 `session_dir_for(create=True)` 自建）；tracker 入口与 id 由 `coherd task new` 生成（`next_id` 生成 `<id>`）。
- **spec 文件与 FK**：spec 落平铺 `<id>.spec.md`、plan 落 `<id>.plan.md`（与 `<id>.task.md` 同目录共存，`task list` glob `*.task.md` 不误抓）；`coherd task new --parent-spec <id>` 写 frontmatter `parent_spec`（FK 追溯，值 = spec id，缺省空串）。
- **门禁字段（gate）**：tracker 可选 `gate`（单行字符串，**非必填**，历史记录缺省合法）；`coherd task new --gate '<命令>'` 写入。执行语义固定：**仓库根 + `bash -lc` + 继承环境**，需净化环境的命令自带 `env -u VAR ...` 前缀，不依赖审查者侧处理；只承诺本机可执行，**不承诺跨机一致**。工具层只校验格式（拒换行、拒单字 `|`），不判断命令含义、不决定跑不跑。**tracker `gate` 是执行权威**；plan「门禁与验证」里的命令只是初稿，二者不一致时以 tracker 为准（改 tracker 归 coordinator）。
- **依赖留正文**：任务间依赖以任务正文手记表达，不进记录结构、不进 CLI 参数——工具层不做拓扑编排或阻塞判定（CLI 不做编排，守滑坡护栏）。
- executor **先读 tracker + spec/plan 再动工**；产出写 tracker「输出」字段指定路径，改动限 plan 白名单。

## 4. 审查义务与循环（B）

reviewer **最小审查集**（每次审查必做，顺序固定 = 五查）：

1. **确定性门禁**：任务带 `gate` 时先跑该命令（仓库根 + `bash -lc` + 继承环境），通过才进入人判；不带则该查跳过。非零退出按下方三类分流。
2. **改动面越界**：比对实际改动与 plan 的改动文件白名单。
3. **规格忠实度**：task 带 `parent_spec` 时，产出与 spec 决策逐条对照，偏离未入 spec = 不忠实。
4. **正确性**：行为符合 DoD（对照 executor 交审的 DoD 自检逐条核验）。
5. **安全性与可维护性**：权限、秘密、危险命令、越界写；复杂度、命名、注释。

结论二选一：`approve`（附理由）或 `revise`（附具体可执行问题清单），判定结论与判据记入审查结论文件。

**门禁失败三类分流**（先判性质，再决定走哪条路；所选分支与判据一句必须落结论文件）：

1. **环境性失败**（依赖缺失、端口占用、无网络、权限不足等）→ `coherd notify` 单向上报 coordinator 阻塞，**不计返工轮次**。
2. **门禁定义错误**（命令引用的路径不存在、测试目标拼错、命令本身不可执行）→ `coherd notify` 上报 coordinator 修订门禁，**不计返工轮次**。
3. **代码性失败**（命令可跑、语义正确、产出不满足）→ 判 `revise`，标准输出与错误输出落盘为证据。

**门禁执行边界**：工作目录固定为仓库根；reviewer 发现门禁与交审声明不一致时拒跑并上报。**字符串级判据**：命令含 `|`、`;`、`&`、`>`、`<`、`$(` 或反引号任一 → 判为复合命令，拒跑并上报（不靠肉眼判断）。**诚实条款**：拒绝复合命令只挡明显的链式注入，**不构成沙箱**——目标仓库代码与其测试夹具本身即任意代码执行面，报工单即信任 coordinator。此句随条款生效，不得被下游误读为「已安全」。

**越界判定以行为为准**：改动超出白名单但无行为变更（纯新增测试文件、机械性 import 修正等）且已在交审消息中声明者，放行；仅在改动改变行为时判返工。

**spec/plan 预审（工件审查）**：高风险/多权衡工件由 coordinator 抛 reviewer 预审（`coherd feedback`，期待回执）——查**完整性 / 可验证性 / 死角与危险面入边界字段 / 决策命名引用**（spec 另查无路径无库名；plan 另查白名单与迁移回滚齐备）；审不代改，`revise` 以 `coherd feedback` 退回 coordinator 修订（工件变更归 coordinator），`approve` 以 `coherd notify` 回流放行；libero 不参与预审（审查判定权 reviewer 独占）。

**规约漂移与结论失效**：

- executor 回传漂移（`coherd feedback`：受影响任务 + 现实阻碍 + 待修订假设）→ coordinator 冻结受影响任务并修订 spec/plan，回应必须三选一（改规格重派 / 降级替代 / 终止），**禁止只回「收到」**。
- spec 一旦变更，关联任务的既有 `approve` **自动失效**；由 coordinator 在重新分派消息中显式声明 `重审 <任务名>：旧 approve <审查结论文件绝对路径> 因规格 <标识> 变更作废` + 新 spec/plan 路径。缺该声明即分派不完整，reviewer 有权要求补齐。工具层无撤回动作，记录态不映射协作阶段。

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
| coordinator | 只读/检索类工具（拆解、分派、讨论、整合所需）；只读 git 命令（带 `GIT_OPTIONAL_LOCKS=0`）；写 session 协作元数据（spec / plan / tracker）；**一次性运维动作**（`git status --porcelain` 输出为空时，清单见 §12） | 直接编辑代码/写仓库文件（人类明确指派除外，见 §12）；未在 §12 放开的仓库级 git 写操作 |
| executor | 完整代码编辑与运行工具；独占 git 写操作与 `index.lock` 治理 | 越出任务工具边界的写操作；改动配置/秘密文件 |
| reviewer | 只读审查 + 跑验证；只读 git 命令（带 `GIT_OPTIONAL_LOCKS=0`）；写审查结论（verdict）；**一次性运维动作**（`git status --porcelain` 输出为空时，清单见 §12） | 直接修改被审产出（须退回 executor）；越过自己工具边界的操作；编辑仓库代码与改动配置；未在 §12 放开的仓库级 git 写操作 |

executor 槽位天然带写权限，建议在受控仓库/沙箱运行；权限收紧由用户 CLI 配置负责（同 reviewer 见 roles/reviewer.md）。

### git 锁争用（`index.lock`）

- 写操作（`add` / `commit` / `stash` / `checkout` / `reset`）取 `$GIT_DIR/index.lock`；取不到即报 `fatal: Unable to create '<gitdir>/index.lock': File exists.` 并中止。
- 冲突方向是从只读方到写方：`git status` 在刷新 index 时也取该锁。git 2.50.1 两次独立复现各 120 轮：`git status` 与 `git commit` 并发时，commit 因 `index.lock` 失败 64 轮与 69 轮；同条件改跑 `GIT_OPTIONAL_LOCKS=0 git status` → 两次均 0 轮失败（两次均本机实测，绝对值随机器与负载浮动，取方向不取量级）。
- 反向不成立：`index.lock` 已被占用时，只读命令（`git status` / `git diff` / `git log`）静默跳过 index 刷新，退出码 0，不报错。
- `GIT_OPTIONAL_LOCKS=0`（git ≥ 2.15）使只读命令不执行需要加锁的可选子操作。变量必须覆盖实际执行 git 的进程：`VAR=0 ./script.sh` 的前缀赋值会进入该命令环境并被其子进程继承（同 `export VAR=0`）；两种写法均覆盖脚本内部的 git 调用。git 文档对该变量的用途原文即「后台进程避免与其他操作产生锁争用」。
- 锁文件两种状态，处置不同：
  1. **有存活持锁方**（另有 git 进程在跑，或对端 agent 的写任务未完成）：等其完成（删除锁文件不终止持锁进程，冲突不因此结束）。
  2. **孤儿锁**（进程被 kill / 崩溃遗留，无 git 进程持有）：写操作持续失败，直到删除该文件。
- 孤儿锁判据（单一条件，不以任务状态作条件）：`pgrep -x git` 退出码为 1（本机同 uid 可见范围内无 comm 为 `git` 的进程 → 无存活持锁方；跨用户 / 容器内进程不可见，无法判定时走处置顺序 ④；`ps | grep git` 会匹配到 grep 自身，不可用）。删除动作本身仍受上表白名单约束：常规由写方（executor / dev）执行；仅当 `git status --porcelain` 输出为空时，删除孤儿锁属 §12「一次性运维动作」，任一槽位可直接做。
- 共享工作区（多 agent 同仓）不以 `git stash` / `checkout` 做版本对比：两者改写工作区文件，此间对端读到的是另一个版本。基线对比用独立副本：`git worktree add /tmp/<name> HEAD` → 在副本跑 → `git worktree remove /tmp/<name>`。
- 处置顺序：① 按「孤儿锁判据」判定 → ② 非孤儿：等持锁方完成，不删除 → ③ 孤儿：由写方（executor / dev）在任务工具边界（§3 边界字段）覆盖该仓库时删除 → ④ 边界未覆盖（冷启动 / 无活跃任务）：由主编排槽位（coordinator / led）先以 `git status --porcelain` 判是否有在途改动——输出为空则按 §12 一次性运维动作**直接删除孤儿锁**；输出非空（存在在途改动，删除后写方仍会重取锁）则不下手，改为下发一条边界含 `.git/index.lock` 的单次解锁任务，或 `coherd notify` 上报用户。

## CLI 集成（数据契约 + 滑坡护栏）

> **CLI 只做文件 CRUD + 格式校验，永不做角色决策**（分派/审查/判断）。

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
- executor/reviewer 启动后读 CONTRACT.md 确认身份, 以 `coherd notify` 向 coordinator 发一次 `standby` 上报（§0 standby/握手, notify 单向不回; 环节映射见 §7 D10）, 随即**转 idle 待机**（herdr 层 pane 挂起; 非 agent CLI 层 hub-wait 等机制, 见 §0 idle）; coordinator 收到两份上报后判集群起步就绪, 自身转 idle 待机后开始按用户意图分派, 之后全程事件驱动(§7 下条)。**此握手单向、一次性、不触发 §2 回复义务**——coordinator 不回"收到", exec/rev 不等回复。coordinator 不轮询(§0)、不检测 exec/rev 状态; 未收到上报也不追究、不重发——沉默即故障信号, 用户自然察觉。
- executor 完成 → 直接提交 reviewer 审查（reviewer 读产物 / `herdr agent read` 验证），结论 approve/revise 回流 coordinator；环境/依赖类阻塞 → `coherd notify` 上报 coordinator（原因 + 已尝试手段）；规约漂移 → `coherd feedback` 回流 coordinator（见 §4）；revise 循环 rev→exe→rev 不经 coordinator，超 §4 上限（2 轮）才介入仲裁。
- feedback/notify 遵循 §2 三铁律（见 §2）；pane 输出退化为辅助。
- **环节→命令映射（D10，唯一权威）**：命令名即语义（=标记名）——`coherd feedback` 注入 `[<role>|feedback]:` 标记（收方据标记需回执）、`coherd notify` 注入 `[<role>|notify]:` 标记（单向不回）；两者均写 session `events.log` 精简审计（`type` 字段标识类型，`body` 字段记原始正文，**无后台待回执登记/判定**；无 session 目录的冷启动回退全局 `events.log` 兜底）。环节映射表是唯一权威（coordinator 分派 / 讨论 / exec→rev 交审 / rev revise 退回 / coordinator→reviewer spec/plan 预审抛审 / 预审 revise 退回 coordinator 修订 / **executor 规约漂移回流** = `feedback`；approve 回流 coordinator（单收件人；含可执行 nit 才另发 executor）/ spec/plan 预审 approve 回流放行 / 改完重交 / 开工 ack / standby 握手 / **环境、依赖、门禁定义类阻塞上报** / 纯通知 = `notify`）。**阻塞语义二分**：环境/依赖/门禁定义类阻塞走 `notify`（无需回执）；规格假设失效走 `feedback` 漂移回流（需回执），两者不得混用。一句话：任务交互看映射表定 feedback/notify，命令名即标记名，接收方据标记判断是否回执——无人值守兜底靠"沉默即故障"人工察觉。
- **批处理纪律（降唤醒次数）**：每条消息 = 一次 `herdr agent prompt` = 对端一次完整 agent turn（重载 system prompt + 契约）。故一次唤醒尽量只装一件事：
  1. **一批票据 = 一条分派消息**：分项列出（每票一行：任务名 + tracker 路径 + objective 一句），**禁止逐票分条发**。
  2. **批量审**：reviewer 在同一轮唤醒里收到 ≥2 票交审 → **一次审完、一条消息汇总逐票结论**（每票一行 `approve:` / `revise:`），禁止逐票各发一条。
  3. **合并阈值（可核）**：同一收件人 **60 秒内需要发 ≥2 条同类消息 → 必须合并为一条**。分派 / 回流 / 结论各类分别适用；跨类型（如交审 feedback + 阻塞 notify）不合并。
     合并发生在**发送前规划**（一件事想清楚、一次写完再发），**不是 sleep 攒批**：禁止为了凑批而等待或轮询；若单条即刻可发就立刻发，不得为凑批延迟。合并的对象是「本来就该在同一轮发出的多条」，不是「还没发生的未来消息」。
- **回执语义**：`coherd feedback` = `[feedback]` 标记期待回执，收方据标记应回一条；`coherd notify` = `[notify]` 标记纯单向，不回。命令名即语义（=标记名），无缺省值陷阱。notify 送达失败 → CLI 非零退出提示转 feedback 重发，关键交接用 feedback 期望回执。
- **无后台待回执**：无程序化待回执登记与清除；回执义务由接收方据消息标记自觉履行，靠"沉默即故障、人自察觉"兜底。
- **活性/断链排查**：用 `docs/activity.md` 的 jq 配方看 session 时间线与静默时长（人工按需跑，**不进 brief、不注入 agent context**）。
- **环节时效（软条款，无硬时限）**：分派后 executor 宜尽速开工 ack（notify）或阻塞上报；交审后 reviewer 宜在合理时限内（参考 ≤2h，按任务规模自定）出结论或上报进度。超时无任何信号 = 断链候选，可据 session `events.log` 时间线介入。

## 9. token 控制

> 目标：不影响工作质量前提下，降低集群 token 消耗（详见 docs/token-control.md）。

**三块核心条款**：

- **① 通信精简**：结论结构化——`approve: <理由要点>` / `revise: <问题清单逐条>`；agent 间消息用要点式，避免叙述铺陈。executor 交审消息**正文 ≤ 400 字**（不含 DoD 逐条勾选清单——每条一行 `✓/✗` 不展开）。必含：`交审 <任务名>` + DoD 逐条 ✓/✗ + 产物绝对路径 + `git diff` 范围 + 关键取舍**一句**。超出 400 字的内容**必须落文件**，消息只送路径指针。**合并 N 票时按票计：每票 ≤400 字，合并消息总上限 = 400 × N**（DoD 勾选清单同样不计入）；reviewer 批量审汇总消息同理：每票一行，按票计。
- **② 输入端控制**（token 大头）：消息引用路径不贴大文件正文；交审附 `git diff` 范围，reviewer 只读变更行；长任务串轮换 session，防上下文膨胀。**文件交互降 token**：结论/产物落文件，feedback/notify 只送路径指针，peer 按需读，避免整段折入消息。
- **③ revise 循环最贵**：一次返工消耗 > 一切通信压缩的收益；投资分派质量（清晰 objective / 可测 DoD / 精确边界）优先于压缩单条消息。
- **④ 规模缩放判据**：简单任务跳过 reviewer 全链路须**同时满足** ≤2 文件改动 + 无安全/正确性敏感面；任一不满足 → 必走 executor → reviewer → coordinator 全链路（判据出处与决策细节见 coordinator.md `§6`）。

## 10. 事实源与同步（契约文档自身的治理）

- **唯一事实源**：repo `roles/*.md`（CONTRACT.md + coordinator/executor/reviewer/libero.md）为唯一事实源；`install.sh` 单向 repo → `~/.config/coherd/` 覆盖分发（旧副本存 `.bak.<ts>`）。
- **改写路径**：契约/角色文档改动一律先改 repo 源、再 `./install.sh` 同步；禁止只改 `~/.config` 副本。
- **审查验收**：审查清单含「镜像一致校验」——diff `roles/` vs `~/.config/coherd/` 五文档 + `templates/` 目录逐文件应为空。
- **brief 不重述**：启动 brief（`bin/coherd` `_brief`）只引 CONTRACT §7 D10（唯一权威映射），不重述环节→命令归组。
- **tracker 边界**：分派 tracker「边界」字段写 `roles/<doc>.md`，不写 `~/.config/coherd/<doc>.md`。

## 11. 外部讨论方（人类临时开的外部 session）

- **定义**：人类在集群外另开的 session，与集群无角色关系：无 `[<role>|<type>]:` 标记、无 tracker、不在 §1 槽位表内。人类决定它是否存在、与谁对话。
- **通道**：`intercom`（§2 通道作用域表第二行）；不注入 coherd 标记、不写 `events.log`。
- **结论性质**：外部结论是**输入证据**，不构成 §4 的 `approve` / `revise` 判定，也不替代 reviewer 的独立审查——三角色模式下审查判定权仍由 reviewer 独占（本条不构成 §4 的先例）。
- **对端感知**：引入外部讨论方时，coordinator 以**一条** `coherd notify` 告知 executor 与 reviewer：谁、讨论什么工件、是否触及当前任务边界。外部结论影响后续动作时走既有通道（新分派或 §4 漂移回应），**不直接改 executor 产出**。
- **版本冻结（机检判据）**：某工件「在审中」= 在 `~/.config/coherd/sessions/**/*.task.md` 中搜该工件路径，命中文件的 frontmatter `status` 为 `pending` 或 `active`。在审期间该工件只读：coordinator 若需修订，先 `coherd notify` 作废/挂起该 review 任务，落盘新版本后重新下派，**禁止就地并发篡改**；改动后以一条 `notify` 报 delta（文件 + 行号 + 一句原因）。
- **冲突处置**：外部结论与集群内审结论相反时，不自行取舍，一条消息报人类裁决。

## 12. 操作分类（coordinator 自判）

人类**未**指定时，用 `git status --porcelain` 判，不看动作大小：

| `git status --porcelain` | 覆盖 | 谁做 |
| ------ | ------ | ------ |
| 输出为空 | 只读（`status`/`diff`/`log`/`coherd task list`）+ **一次性运维动作**（切/建分支、push 已审分支、合并已审 PR、pull、`worktree`、删孤儿锁） | 任何槽位直接做，不开票 |
| 命中**仓库**内路径 | 源码、测试、工程配置（`.gitignore` / `pyproject.toml` / CI）、文档、`roles/` 契约 | executor（开票分派） |
| 只命中 session 协作元数据 | `~/.config/coherd/sessions/**` 下的 spec / plan / tracker / verdict | coordinator / reviewer 直接写 |
| 判不准 | — | 归入「仓库内路径」→ executor |
| 人类指定 coordinator 改仓库文件 | 情形与上表同，执行方改由人类定 | coordinator 直接做：commit body 记一行 `人类直接指派：<人类原话>`；审查权归人类，不开 tracker、不入 §4、**不设反向复核**；目标文件在 executor active 任务内时先 `coherd notify` 停机再动手 |

- 只读 git 命令带 `GIT_OPTIONAL_LOCKS=0`（§5 锁争用）。
- **一次性运维动作的界碑**：不产生工作区内容差异。产生了 diff 的动作（改文件、改配置）不属于本类，回到上表按路径归属判。
- **人类明确指派时不构成角色分离违例**：coordinator 直改仓库文件由人类担审查，但**不产生 executor/reviewer → coordinator 的反向复核链**（防止循环与角色颠倒）；目标文件若在 executor 的 active 任务内，须先停机（`coherd notify` 让其丢弃当前改动）再动手，**不得并发改同一文件**。
