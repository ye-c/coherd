# HANDOFF.md — coherd v5 重构交接

> **用途**：本文件是 coherd 重构的分派起点。未来在 coherd 仓库内开集群（coordinator/executor/reviewer），由集群按本文件落地。
> **来源**：w27 集群（coordinator=pi / executor=omp / reviewer=claude）2026-08-26 讨论收敛。
> **状态**：方案定稿，未实现。实现由未来 coherd 集群执行。

---

## 0. 两个独立议题（别混淆）

本次讨论有**两条独立改动线**，不互斥也不等同，可分别落地：

| | 议题 1：agent 内部 task 纪律 | 议题 2：跨 agent 文件交互重构 |
| --- | --- | --- |
| 层次 | prompt 层（优化 agent 自己的 loop） | 架构层（改跨 agent 通信） |
| 出发点 | omp `/goal`（目标锁定+防偷换+完成须证据）能否通用化 | pane 输出+herdr read 有截断/重启丢/读多读少缺陷 |
| 前提 | 三 agent 都有 task 工具（已证实：pi TaskCreate、omp /goal、cc task） | 不依赖 agent 内部工具 |
| 落脚点 | 契约教 agent 用**自带 task 工具**做目标纪律，不改架构 | 改通信从 pane 输出到文件+typer CLI |
| 跨 agent 可见？ | ❌ task 工具是 agent 本地状态，跨 agent 不可见 | ✅ 文件是跨 agent 共享锚点 |
| 关系 | 议题 1 不能替代议题 2（本地状态跨 agent 不可见） | 议题 2 不排斥议题 1（agent 内部是否用 task 工具是独立决策） |

**落地建议**：议题 1 轻（改 roles/*.md 加几条 prompt 指令），议题 2 重（改架构+新增 CLI）。两者可分别排轮次，不必捆绑。

---

## 1. 背景与动机

### 1.1 纯文档契约的天花板

coherd 当前是「纯 bash bin/coherd（340 行，做拉起+standby）+ roles/*.md 契约文档（agent 自律）」架构。问题：

- **「有来有往」靠提示词自律**：§2 规定收到 `[<role>]:` 前缀消息即产生 push back 义务。但实测中 executor/reviewer 反复出现「干活了、pane 里输出了、但没主动 `herdr agent prompt` push 给对端」的漏回执。
- **根因**：纯提示词约束力随上下文膨胀衰减。token 压力下 agent 把「输出即完成」当默认，回执义务被压缩遗忘。
- **加强无效**：「有来有往」原则加强多次，仍复发。

### 1.2 实测证据

w27 集群讨论本方案过程中，reviewer 连续多轮：

- 在自己 pane 完成完整分析（`herdr agent read` 可见）
- 但未主动 `herdr agent prompt` push 结论给 coordinator
- coordinator 不得不用 read 去捞（违反事件驱动，引入轮询风险）

点名批评后 reviewer 才纠错并 push。证明：**靠记忆的回执义务不可靠**。

**附带发现的角色边界越线**：讨论中 reviewer 曾绕过 coordinator，直接和用户私聊对齐方向后跑去查社区，导致 coordinator 发消息时 reviewer 答非所问（给调研而非正面认 A/B 原则）。这揭示 reviewer 横向协作时不应绕过 coordinator 直连用户拍板——未来集群注意此角色边界。

### 1.3 社区调研（reviewer 查）

业界多 agent 编排的主流是**文件交互**（Anthropic 官方推荐「one agent writes a file, another reads and responds to it」）：

| 模式 | Token 成本 | 一致性机制 | coherd 现状 |
| --- | --- | --- | --- |
| 黑板/共享文件 | 高 | 广播+自选 | — |
| 消息传递 | 低 | 声明依赖图 | — |
| **活文档/外部文件** | **极低** | **外部文件读，session 重启存活** | ← 应走这条 |
| 事件驱动增量 | 低 | 治理层 | — |

coherd 当前 pane 输出 + herdr read 本质是「消息传递变体」——有消息传递的缺点（上下文膨胀、截断、重启丢失），没有共享状态的优势（持久边界、可校验）。

---

## 1.5 议题 1：agent 内部 task 工具纪律（轻、prompt 层）

### 1.5.1 动机

omp 有 `/goal`（目标锁定+防偷换+完成须证据+中断恢复）。pi 有 `TaskCreate/TaskList/TaskUpdate/TaskExecute`。claude 有 task 跟踪。**三 agent 都有内建 task 工具，但 coherd 契约一个字没提怎么用它们**——全靠 agent 自觉。

这导致：agent 执行长任务时，目标/进度/回执义务全在上下文记忆里，上下文一压缩就丢。和漏 push 同源。

### 1.5.2 落地（roles/*.md 加几条 prompt 指令，不改架构）

在 executor.md / coordinator.md / reviewer.md 各加一节「内部 task 纪律」：

- **收到分派/revise → 先 TaskCreate 记录**（subject=任务名，description=DoD/objective），再动工
- **干完 → TaskUpdate=completed**，之后才发 push 回执（回执动作仍走 §2 事件驱动铁律）
- **中断恢复（idle 唤醒/新 session）→ 先 TaskList 查未 completed 任务**，续上
- **预算≠完成**：token/时间告急不是完成理由，未完成如实上报保持任务激活

### 1.5.3 与议题 2 的关系

- task 工具是 **agent 本地状态**，跨 agent 不可见——coordinator 看不到 executor 的 TaskList
- 所以议题 1 **不能替代**议题 2 的跨 agent 文件锚点
- 但议题 1 **补的是 agent 自身 loop 纪律**（防 executor 忘回执、防 coordinator 忘分派进度），是议题 2 没覆盖的一层
- 两者**叠加**最稳：agent 内部用 task 工具防遗忘 + 跨 agent 用文件+CLI 做权威锚点

### 1.5.4 诚实边界

- task 工具仍是 agent 自律调用，不是运行时强制（agent 可能忘调 TaskCreate）
- 比 prompt 纯提醒强：TaskList 是持久状态，上下文压缩不丢，agent 唤醒可自查
- 治"agent 自己忘了"，不治"跨 agent 通信丢"——后者靠议题 2

---

## 2. 议题 2：v5 方案 — 事件驱动铁律 + 内容/信号分离 + 持久锚点（架构层）

### 2.1 三铁律（CONTRACT §2）

1. **事件驱动铁律**：做事的 agent 完成动作后，主动 `herdr agent prompt` push 对端。**不等待、不轮询、不靠对端 read 探活。不 push = 任务未完成。**
2. **内容/信号分离**：prompt 只送「事件信号 + 文件路径指针」，**不承载结论正文**。文件是内容载体（持久锚点、天然 EOF、可校验），prompt 是事件信号。
3. **push 格式**：`[<role>]: <信号> <任务名> — 详见 <文件绝对路径>`

### 2.2 持久锚点文件（tracker）

每个动作的产出落文件，不靠 pane 输出：

- **coordinator 分派前**写 tracker（4 字段：objective/DoD/输出/边界）到 `~/.config/coherd/tasks/<ws>/<id>.md`
- **executor** 产出写目标 repo（tracker 的「输出」字段指定路径）
- **reviewer** 审查结论写 `~/.config/coherd/reviews/<ws>/<id>.md`
- **approve 后** coordinator 归档 tracker + 结论到 `~/.config/coherd/archive/<ws>/`

### 2.3 两条保护

1. **tracker 权威副本放 coordinator 侧**（`~/.config/coherd/`），executor 物理不可改 → 事后对账有权威底本。
2. **revise DoD 语义变更必经 coordinator 更新 tracker**（不走 rev→exe→rev 直通）；实现级修订仍走闭环。

### 2.4 砍掉的加戏（不再考虑）

- ❌ [done] 机械标记 / 消息终止符 — 加戏偏离本源，事后补发是时间错位
- ❌ 恢复检查（唤醒扫末条消息）— 本末倒置
- ❌ A/B 二分类（交付型 vs 讨论型）— 给 agent 添判断负担
- ❌ TaskCreate/TaskUpdate 作为**跨 agent** 锚点 — task 工具是 agent 本地状态，跨 agent 不可见。**注意：砍的是"跨 agent 锚点"用途，不是 agent 内部用途**——agent 内部用 task 工具做目标纪律仍正当（见议题 1）

### 2.5 §6 轻量轮仍写 tracker

跳的是 reviewer，不是 tracker。轻量轮：coordinator 写 tracker → executor 读→产出→push done 给 coordinator（不经 reviewer）→ coordinator 读产出文件自判 → 归档。

---

## 3. typer CLI 升级

### 3.1 两入口设计（刻意，不合一）

| 入口 | 语言 | 职责 | 理由 |
| --- | --- | --- | --- |
| `bin/coherd`（保留 bash） | bash | 拉起：herdr workspace/pane/rename/standby | herdr 调用是 shell 原生，typer subprocess 包一层更脆 |
| `coherd task`（新增 typer） | python/typer | 任务管理：new/list/show/archive/status | struct + 查重 + 归档是机械动作，agent 不该用 token 做 ls/grep |

### 3.2 命令面

```bash
# 任务管理（typer）
coherd task new --task-name X --objective X --dod X --output X --ws X  # 生成 tracker，打印路径
coherd task list [--ws X] [--status pending|active|done]              # 列摘要
coherd task show ID                                                    # 打印完整 tracker
coherd task archive ID                                                 # 移入 archive/
coherd task status ID --set pending|active|done                        # 更新状态

# 拉起（保留 bash bin/coherd）
coherd start <ws-slug>                                                 # herdr workspace+pane+rename+standby
```

**不做的命令**（防滑坡）：

- `coherd dispatch` — coordinator 语义决策
- `coherd review` — reviewer 语义决策
- `coherd status` — herdr agent list 的活

### 3.3 struct

YAML frontmatter + Markdown body。**不加 pyyaml 依赖**，手写 15 行解析器（9 固定字段，`split '---'` 取 block，按行 `split(': ')` 建 dict）。

```yaml
---
id: w27-20260826-001              # ws-YYYYMMDD-序号，CLI 自动生成，做文件名防注入防重复
ws: w27                           # herdr workspace 短号
created_at: 2026-08-26T14:30:00Z
task_name: 重构 llm-switch
status: pending|active|done
parent_id:                        # revise 链（预留，本轮不实现）
objective: |
  ...
dod: |
  ...
output_path: /home/chace/code/tallyman/...
---

# 正文（可选，agent 补充上下文）
```

**id 生成规则**：`<ws>-<YYYYMMDD>-<序号>`，序号同 ws 同日从 001 递增，CLI 自动查重。**id 做文件名，任务名只放 struct 字段**，彻底防注入（正则 `[a-zA-Z0-9_-]`）防重复。

**路径**：`~/.config/coherd/tasks/<ws>/<id>.md` / `reviews/<ws>/<id>.md` / `archive/<ws>/<id>.md`

### 3.4 文件校验机制（不引入 markers/hash）

靠「先写文件→close→再 push」+ 文件存在且非空=完整。不引入应用层 markers/hash（加戏已砍）。文件系统的原子写入（写完后 rename 或 close）已足够。下游 agent 收到 push 后读文件，不存在或空→退回上游重写。

### 3.5 CLI 调用时机

- `task new` — coordinator 分派前调（生成 tracker 后再发分派消息）
- `task list` — 任何 agent 随时调（幂等只读，不改变状态）
- `task show` — 任何 agent 随时调（读完整 tracker）
- `task archive` — coordinator 收到 approve 后调
- `task status --set` — executor 开始动工时 set active、完成时 set done（下轮实现）

### 3.6 滑坡护栏（写进 CLAUDE.md）

> coherd CLI 只做文件 CRUD + 格式校验，**永不做角色决策**（分派/审查/判断）。不绑特定 agent CLI（pi/omp/claude）是原架构初衷；coherd typer 是数据管理工具不是 agent 编排引擎。

### 3.7 技术栈

- python + typer + uv（对齐 tallyman 形态）
- pyproject.toml + `src/coherd/cli.py`
- install.sh 末尾加 `uv add typer && uv sync`，不破坏现有拷贝逻辑

---

## 4. 落地清单

### 4.1 契约补丁（roles/*.md）

| 文件 | 节 | 加什么 | 行 |
| --- | --- | --- | --- |
| CONTRACT.md | §2 有来有往段后 | 三铁律（事件驱动+内容信号分离+push格式） | +3 |
| CONTRACT.md | §3 分派模板后 | 分派前写 tracker（coord 侧权威副本，executor 不可写）+ executor 读 tracker | +2 |
| CONTRACT.md | §4 循环与终止后 | DoD 语义变更归 coord + 归档 | +2 |
| CONTRACT.md | §7 末 | push 内容=信号+路径，pane 输出退化为辅助 | +1 |
| CONTRACT.md | §9 ②段 | 文件交互降低输入端 token | +1 |
| executor.md | 接分派段 | 读 tracker→产出写文件→push reviewer 路径 | +2 |
| reviewer.md | approve/revise 格式段 | 结论写文件→push coord 路径 | +1 |

**总计**：CONTRACT +9 / executor +2 / reviewer +1。不动 coordinator.md/libero.md/§3 模板/§5。

### 4.2 CLI 新增

- `pyproject.toml`（name=coherd，deps=[typer]，requires-python>=3.10，entry `coherd=coherd.cli:app`）
- `src/coherd/cli.py`（typer app + task 子命令组）
- `src/coherd/tracker.py`（tracker 读写 + YAML frontmatter 手写解析器）
- `src/coherd/id_gen.py`（id 生成 + 查重）

### 4.3 install.sh 适配

末尾加：

```bash
uv add typer && uv sync
```

不破坏现有 bin/coherd symlink + roles 拷贝 + skills 安装逻辑。

### 4.4 CLAUDE.md 护栏

新增「滑坡护栏」段（§3.4 内容）。

---

## 5. 最小落地轮次（建议）

| 轮 | 做 | 验证 |
| --- | --- | --- |
| **R1** ✅已完成 | CONTRACT 补丁（§2/§3/§4/§7/§9）+ executor/reviewer 补丁 + 议题1 task 纪律节 | 契约文件 git diff 审查 |
| **R2** | pyproject + cli.py + tracker.py + id_gen.py（task new/list/show/archive） | `coherd task new` 生成 valid tracker、`list` 可见、`show` 打印 |
| **R3** | install.sh 适配 uv + CLAUDE.md 护栏 | 重装后 `coherd task` 可用 |
| **R4（下轮）** | `task status --set` 状态机 + bash bin/coherd 适配新 tracker 路径 | status 变更落 struct |
| **不做** | bash→typer 统一入口（两入口是刻意设计） | — |

---

## 5.5 R1 落地记录

> **状态：已完成**（w2a 集群，2026-08-26）。revise 1 轮后 approve。

- **改了什么**：`roles/` 下 CONTRACT.md / coordinator.md / executor.md / reviewer.md 纯文档补丁（已同步到 `~/.config/coherd/`）。
- **CONTRACT.md**：三铁律（事件驱动 / 内容·信号分离 / push 格式，§2）；tracker 权威副本 + 自举过渡 + DoD 语义变更归 coord + 归档（§3/§4）；§7 收口见 §2。
- **conduct 决策**：R1 只做契约补丁，不做 CLI / 不装依赖 / 不动 bin/install.sh。议题1 一并落地。
- **共识修正**（revise 采纳）：①内容/信号分离措辞对齐 §9①（prompt 带短结构化信号+路径，结论正文落文件，不设绝对句）；②「executor 物理不可写」改「契约上不可写（运行时不强制，靠流程+对账)」，避免与能力分离声明矛盾；③补充自举过渡：CLI 落地前 coordinator 手写 tracker、`<id>`=任务名、目录由首写方 mkdir -p 兜底；④§7 删重复只留引用。
- **reviewer 交付物**不留挡板：revise 4 处全修，approve。
- **此后可直接做 R2**（CLI：pyproject + cli.py + tracker.py + id_gen.py）。

## 6. 未决/下轮

- `parent_id` revise 链（预留 struct 字段，本轮不实现）
- 跨 ws 任务关联（不管，ws 内闭环，YAGNI）
- `task status --set` 状态机
- bash bin/coherd 适配新 tracker 路径（brief 消息是否带 tracker 路径）
- tracker 正文（frontmatter 之外的 markdown body）是否需要标准化，还是留给 agent 自由发挥

---

## 7. 讨论历程（审计线索）

| 轮 | 议题 | 结论 |
| --- | --- | --- |
| 1 | 1 | coherd 加 /goal 机制可行性：路径 A（契约硬化）可行，路径 B（驱动各 CLI 内建 goal）违架构 |
| 2 | 1+2 | libero 落地清单 M1-M4：tracker 落盘(议题2) + TaskCreate/回执/预算≠完成(议题1) |
| 3 | 2 | reviewer 查漏：tracker 放 coord 侧 + revise DoD 变更归 coord + 归档清理 |
| 4 | 1+2 | 用户质疑纯文档防幻觉：确认靠角色分离 + 机器事实锚点，不是 100% 运行时强制 |
| 5 | 1 | 用户指出 task 工具编排方向：三 agent 都有 task 工具，但跨 agent 不可见，只能做单 agent 锚点 |
| 6 | 2 | reviewer 提 [done] 机械标记：用户砍（加戏偏离本源，事后补发时间错位） |
| 7 | 2 | 用户定事件驱动铁律：做完主动 push，不等待不轮询，不 push=未完成 |
| 8 | 2 | reviewer 社区调研：文件交互是主流，pane read 是消息传递变体有缺陷 |
| 9 | 2 | 用户拍板重开持久锚点：v5 定稿——铁律 + 内容信号分离 + 文件锚点 + 两保护 |
| 10 | 2 | 用户指出 ws 分桶仍可能重复：引入 struct + CLI（typer+uv，对齐 tallyman） |
| 11 | 2 | reviewer typer 评估：两入口设计 + 命令面 + struct + 护栏 |
| 12 | 1 | 用户末尾提醒两个议题未分清：HANDOFF 重构拆分议题1(prompt层) vs 议题2(架构层) |

---

## 8. 给未来集群的指引

> 你（未来 coherd 集群的 coordinator）读到这份 HANDOFF.md = 你的分派起点。
> 按 §5 轮次分派 executor，每轮走 executor→reviewer→coordinator 全链路。
> 改 `~/code/coherd/roles/` + `~/code/coherd/src/` + `~/code/coherd/install.sh` + `~/code/coherd/CLAUDE.md`。
> 改完跑 `install.sh` 同步到 `~/.config/coherd/` 生效。
> **吃自己的狗粮**：用 coherd 集群机制重构 coherd 自己。

[done]
