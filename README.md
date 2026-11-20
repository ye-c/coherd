# coherd

coherd 把多个 AI agent 组织成一个小团队：一个规划、一个干活、一个审查。编排逻辑已内置，配好 backend 即用。

也提供**双角色简易模式**（`coherd -s`）：led（协调+审查合一）+ dev（执行）两 pane，代价是没有独立第二意见（见下文）。

> ⚠️ 安全须知：本 repo 不提供任何 agent wrapper、不绕过任何权限确认。agent 的权限与密钥由你自己的 CLI 配置负责，详见下文"安全"与 roles/reviewer.md。

## 工作原理

```
你 ──> coordinator（协调）──> executor（执行）──> reviewer（审查）──> coordinator（整合）──> 你
              │                                                          │
              └──────── approve: 交付  /  revise: 退回 executor 重做 ◀───┘
```

- **coordinator**（协调者）：接收你的意图，拆成带验收标准的任务。
- **executor**（执行者）：实现任务，产出可验证结果。
- **reviewer**（审查者）：跑验证 + 五查（门禁 → 越界 → 忠实度 → 正确性、安全与可维护性），给 `approve` 或 `revise`。
- **revise 上限 2 轮**，仍不通过则由 coordinator 仲裁（改判/拆任务/终止）。
- 三角色是**槽位**：具体 agent CLI 可配置，不绑定任何特定实现（见 docs/configuration.md）。

## 前置依赖

| 依赖 | 作用 | 安装 |
| ------ | ------ | ------ |
| herdr | 终端多路复用器；管理 workspace/pane/agent | <https://github.com/…> |
| jq | 解析 herdr JSON 输出 | `brew install jq` |
| 任意 agent CLI ×3 | 三个槽位各一个；必须是 herdr 内置识别的 21 种之一（见 docs/agents.md） | 各自官方安装方式 |

> 不需要 pi/omp/claude code 三件套——你手上的任何 herdr 可识别 agent 都能填进槽位。也**不需要** coherd 替你配置模型/密钥：各 CLI 的认证配置由你自己维护。

## 安装

手工步骤与 `./install.sh` **二选一**，不要都跑（都跑会各留一份 `.bak`，徒增困惑）。

```bash
# 手动安装（install.sh 亦可用）
cp bin/coherd ~/.local/bin/                 # 或 /usr/local/bin，确保在 PATH
mkdir -p ~/.config/coherd
cp roles/CONTRACT.md roles/coordinator.md roles/executor.md roles/reviewer.md roles/libero.md ~/.config/coherd/
cp roles/CONTRACT-simple.md roles/led.md roles/dev.md ~/.config/coherd/   # 双角色简易模式 (-s)
mkdir -p ~/.config/coherd/templates                                     # spec/plan 骨架
cp -R roles/templates/. ~/.config/coherd/templates/                     # 同 spec/plan 骨架
# 一键版:
./install.sh                                # 拷贝+备份+依赖提示
```

> 模板那两行：源路径尾缀 `/.` 保证不嵌套——目标已存在时连跑两次仍单层（`cp -R roles/templates <已有目录>/` 会嵌成 `templates/templates/`）。`./install.sh` 的做法不同：先把旧目录 `mv` 成 `.bak` 再整目录拷，目标不存在故不嵌层（见 install.sh 注释）。

## 配置

coherd 只问三件事：三个角色各用什么命令启动。设置 `COHERD_*_CMD` 环境变量，或写 `~/.config/coherd/coherd.conf`：

```bash
export COHERD_COORDINATOR_CMD=~/bin/my-coordinator-cli
export COHERD_EXECUTOR_CMD=~/bin/my-executor-cli
export COHERD_REVIEWER_CMD=~/bin/my-reviewer-cli
```

都不设置时，coordinator / reviewer 回退查找 PATH 中的 `pi`、executor 回退 `omp`；再找不到就报错并指向 docs/configuration.md。

双角色简易模式（`-s`）用两槽位 `COHERD_LED_CMD` / `COHERD_DEV_CMD`；不设置时分别回退 `COHERD_COORDINATOR_CMD` / `COHERD_EXECUTOR_CMD`，再回退 `pi` / `omp`。

## 用法

```bash
coherd [init] [-s|--simple] [-p|--portrait] [-t|--tabs] [-e|--executors N] [--agent role=cmd[,...]] [REPO] [LABEL]
# REPO 仓库目录（默认当前目录）；LABEL workspace 标签（默认仓库名）
# init 强制(重)建：同 label 已存在时先关闭再重建（CONTRACT.md/brief/agent 配置改动后重启用）；不存在则等同普通创建
# -s / --simple   双角色简易模式：led（检查者）/ dev（执行者）两个 tab；-p 在该模式下无意义（忽略并告警）
# -p / --portrait 竖屏布局（默认横屏，无需赋值，存在即启用）
# -t / --tabs     每角色独立 tab（1 coord / 2 rev / 3 exec / 4 libero 手动）；与 -p 互斥，tabs 优先；-s 恒用 tab，此 flag 冗余
# -e / --executors 启动执行者数量（1–8，默认 1；N≥2 时强制 tabs 布局）；与 -s 互斥
# --agent         按角色覆盖本次启动命令（如 --agent led=codex,dev=opencode）；per-run，优先于 COHERD_*_CMD 与 PATH 回退
```

- 横屏（默认）：reviewer 左上 / executor 右上 / coordinator 下全宽
- 竖屏：`-p` / `--portrait` 触发 — coordinator 上 / reviewer 中 / executor 下
- tabs：`-t` / `--tabs` 触发 — 每角色独立 tab（1 coord / 2 rev / 3 exec），另备 4-libero 自由 tab 供手动加载
- 多执行者：`-e N`（N≥2，上限 8）触发 — 强制 tabs 布局（1 coord / 2 rev / 3..N+2 exec-1..N / N+3 libero）
- simple（`-s`）恒两个 tab：1 led / 2 dev（无需 `-t`）
- agent 命名：`-e 1`（或默认）为 `${ws}-coordinator` / `${ws}-executor` / `${ws}-reviewer`；`-e N`（N≥2）时执行者带序号 `${ws}-executor-<n>`（n = 1..N），coordinator / reviewer 名不变
- 消息标记：agent 间 `coherd feedback` / `coherd notify` 由 CLI 注入 `[<role>|feedback]:` / `[<role>|notify]:` 前缀；多执行者时带实例序号，如 `[executor#2|notify]:`（接收端只匹配 role，序号仅供展示）
- **并行扇出前先冻结共享面**：`-e N` 拆票前需判定能否并行、扇出前定稿共享面。定义、判据与三动作见 `CONTRACT.md` §3——本处只给指针，不复述条款

```bash
coherd                              # 在当前目录起集群（横屏）
coherd ~/code/myapp                 # 指定仓库
coherd -p ~/code/myapp mylabel      # 竖屏 + 自定义标签
coherd -t ~/code/myapp              # 每角色独立 tab（含手动 libero tab）
coherd -e 3 ~/code/myapp            # 启动 3 个 executor 并行集群（强制 tabs）
coherd -s ~/code/myapp              # 双角色简易模式（led / dev 两个 tab）
coherd init ~/code/myapp            # 强制重建同 label 集群（已存在先关闭）
```

重复运行同一 label 不会重建：已存在则聚焦打开（`init` 子命令除外，它会先关闭再重建）。任一路径不通（缺 jq、缺命令行配置）会直接报错退出。

## 任务记录与消息 CLI

`coherd` 子命令可单独调用，不必先起集群（`task` 做 tracker CRUD，`feedback` / `notify` 发 agent 间消息；CLI 只做存取，不做角色决策）。

tracker：

```bash
coherd task new -t "任务名" -o "目标 + 为什么" -d "可验证完成定义" --output "产出路径"
#   可选: --ws / --status pending|active|done / --body / --parent-spec <spec id> / --gate <单行命令>
#   → 写 ~/.config/coherd/sessions/<session>/<id>.task.md 并打印路径
coherd task list [--ws <ws>] [--status <状态>]   # 摘要：id / status / 建日 / task_name
coherd task show <ID>                            # 完整 tracker（frontmatter + 正文）
coherd task status <ID> --set pending|active|done
```

tracker ID 格式 `<ws>-<14位秒时间戳>-<2位序号>`（UTC `YYYYMMDDHHMMSS` + `01`–`99`；同 ws 同秒重复创建时序号递增），如 `wr1-20261120055148-01`。

消息（两者都写 session `events.log` 审计，正文只写 body——`[` 开头的自造前缀会被 CLI 拒绝）：

```bash
coherd feedback <peer_agent> "<正文>"   # 期待回执：收方应回一条（分派 / 交审 / revise / 讨论）
coherd notify   <peer_agent> "<正文>"   # 单向知会：无需回执（ack / 上报 / 回流 / 握手）
```

- 命令名即语义（=注入的标记名），无缺省值陷阱；单向上报用 `notify`，需要对方回应才用 `feedback`。
- 自身 `ws` / `role` 缺省取 `HERDR_WORKSPACE_ID` / `COHERD_ROLE`（或从 agent 名派生）；不在集群 pane 内调时显式给 `--ws` / `--role`。
- 正文可走 `-`（stdin）或 `--body-file`，避开 shell 求值。
- simple 模式（`-s`）对端唯一（led↔dev），可省略 peer 位。
- `notify` 送达失败会非零退出并提示改用 `feedback` 重发；`feedback` 送达失败不丢审计行。

## 双角色简易模式（`-s`）

两个 tab 的小集群：用户与 **led**（检查者）交互，led 干活拆解给 **dev**（执行者）。

```
你 ──> led（协调 + 审查）──> dev（执行）──> led（自审 + 整合交付）──> 你
```

- **led** = coordinator + reviewer 合一：拆解分派、跑验证审查、整合交付；**不写码**。
- **dev** = executor：实现任务，交审只发一条消息给 led（led 兼任审方，无第二条上报）。
- 写/审分离仍是两个独立 agent 实例——led 不写码，铁律守住。
- ⚠️ **能力降级**：无独立 reviewer，即**没有独立第二意见**（spec/plan 预审、产出审查都是 led 自审）。需要第三方复核时用默认三角色模式。
- **revise 上限 2 轮**，超限由 led 自仲裁（改判/拆任务/终止）——简易模式无第三方可升级。

契约见 `roles/CONTRACT-simple.md` + `roles/led.md` / `roles/dev.md`（安装到 `~/.config/coherd/`）。三角色模式的文档与行为**零改动**，两套模式以 `-s` 切换。

## 三 agent 协作契约

完整契约见 `roles/CONTRACT.md`（公共，安装到 `~/.config/coherd/CONTRACT.md`）+ 四份 per-role（`roles/{coordinator,executor,reviewer,libero}.md`），要点：

- **分派契约**：coordinator→executor 每条任务必带 4 字段——objective / DoD 验收标准 / 输出格式 / 工具边界。字段缺了先补，模糊不干活。
- **审查循环**：reviewer 每次必做五查——门禁（任务携带的单行验证命令）→ 改动面越界（对照方案白名单）→ 规格忠实度 → 正确性 → 安全性与可维护性；给双向结论，revise 上限 2 轮。
- **工具白名单**：coordinator 只读/检索，executor 完整编辑，reviewer 只读审查；任务级边界与白名单取交集。
- **规模缩放**：低风险小任务可省掉审查环节，高风险任务必走全链路。
- **共享面与并行判定**：多执行者并行时，`N≥2` 一律产 plan（不得按轻任务跳步）+ 方案必抛预审，扇出前冻结共享面；判据与三动作见 `CONTRACT.md` §3（此处只给指针，不复述条款）。

## 安全

- coherd 只做一件事：建 workspace+pane → 跑你给的命令 → 识别改名 → 发 brief。**它不提供任何 agent wrapper，不注入 env，不背 `--dangerously-skip-permissions` 这类权限责任**。
- **agent 的权限与密钥是你自己 CLI 配置的事，自负**。默认不绕过任何确认。
- reviewer 槽位建议最小权限（只读 + 跑验证），具体做法参考 roles/reviewer.md——是建议，不强制。
- 若你的 reviewer CLI 配置了跳过权限确认，那是在你自己的沙箱环境里做的决定，与 coherd 无关。

## 局限

- 冷门 agent CLI 不在 herdr 内置识别的 21 种之内就无法用（见 docs/agents.md）。
- **有界不一致（bounded incoherence）**：reviewer 审查的可能是 executor 编辑**进行中**的树，不是原子快照。缓解：reviewer 验证前以 `git status`/`diff` 感知进行中改动，DoD 尽量定义在可复现状态。
