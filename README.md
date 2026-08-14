# coherd

coherd 把多个 AI agent 组织成一个小团队：一个规划、一个干活、一个审查。编排逻辑已内置，配好 backend 即用。

> ⚠️ 安全须知：本 repo 不提供任何 agent wrapper、不绕过任何权限确认。agent 的权限与密钥由你自己的 CLI 配置负责，详见下文"安全"与 docs/reviewer.md。

## 它解决什么问题

单个 agent 自己写代码、自己说“没问题”，等于同一套推理路径既出题又判卷——写得再仔细也会盲区。**coherd 把这两件事拆给不同 agent 做**：干活的人不用自证，审查的人不用先入为主。角色分离是核心设计，不是仪式。

## 工作原理

```
你 ──> coordinator（协调）──> executor（执行）──> reviewer（审查）──> coordinator（整合）──> 你
              │                                                          │
              └──────── approve: 交付  /  revise: 退回 executor 重做 ◀───┘
```

- **coordinator**（协调者）：接收你的意图，拆成带验收标准的任务。
- **executor**（执行者）：实现任务，产出可验证结果。
- **reviewer**（审查者）：跑验证 + 查正确性/安全/可维护性，给 `approve` 或 `revise`。
- **revise 上限 2 轮**，仍不通过则由 coordinator 仲裁（改判/拆任务/终止）。
- 三角色是**槽位**：具体 agent CLI 可配置，不绑定任何特定实现（见 docs/configuration.md）。

## 前置依赖

| 依赖 | 作用 | 安装 |
|------|------|------|
| herdr | 终端多路复用器；管理 workspace/pane/agent | https://github.com/…（占位） |
| jq | 解析 herdr JSON 输出 | `brew install jq` |
| 任意 agent CLI ×3 | 三个槽位各一个；必须是 herdr 内置识别的 21 种之一（见 docs/agents.md） | 各自官方安装方式 |

> 不需要 pi/omp/claude code 三件套——你手上的任何 herdr 可识别 agent 都能填进槽位。也**不需要** coherd 替你配置模型/密钥：各 CLI 的认证配置由你自己维护。

## 安装

```bash
# 手动安装（install.sh 亦可用）
cp bin/coherd ~/.local/bin/                 # 或 /usr/local/bin，确保在 PATH
mkdir -p ~/.config/coherd
cp roles/ROLES.md ~/.config/coherd/ROLES.md
# 一键版:
./install.sh                                # 拷贝+备份+依赖提示
```

## 配置

coherd 只问三件事：三个角色各用什么命令启动。设置 `COHERD_*_CMD` 环境变量，或写 `~/.config/coherd/coherd.conf`：

```bash
export COHERD_COORDINATOR_CMD=~/bin/my-coordinator-cli
export COHERD_EXECUTOR_CMD=~/bin/my-executor-cli
export COHERD_REVIEWER_CMD=~/bin/my-reviewer-cli
```

都不设置时，回退找 PATH 中的 `pi` / `omp` / `cc`（旧集群的 CLI 名；其中 `cc` 有双重含义——既是旧集群 CLI 名，通常也是指你的 Claude Code）；再找不到就报错并指向 docs/configuration.md。

## 用法

```bash
coherd [REPO] [LABEL]
# REPO 仓库目录（默认当前目录）；LABEL workspace 标签（默认仓库名）
```

- 横屏（默认检测）：reviewer 左上 / executor 右上 / coordinator 下全宽
- 竖屏：coordinator 上 / reviewer 中 / executor 下
- 手动指定：`COHERD_LAYOUT=portrait|landscape|auto coherd …`

```bash
coherd                              # 在当前目录起集群
coherd ~/code/myapp                 # 指定仓库
COHERD_LAYOUT=portrait coherd ~/code/myapp mylabel  # 竖屏 + 自定义标签
```

重复运行同一 label 不会重建：已存在则聚焦打开。任一路径不通（缺 jq、缺命令行配置）会直接报错退出。

## 三 agent 协作契约

完整契约见 `roles/ROLES.md`（安装到 `~/.config/coherd/ROLES.md`），要点：

- **分派契约**：coordinator→executor 每条任务必带 4 字段——objective / DoD 验收标准 / 输出格式 / 工具边界。字段缺了先补，模糊不干活。
- **审查循环**：reviewer 每次必跑验证命令 + 三查（正确性/安全/可维护性）+ 给双向结论；revise 上限 2 轮。
- **工具白名单**：coordinator 只读/检索，executor 完整编辑，reviewer 只读审查；任务级边界与白名单取交集。
- **规模缩放**：低风险小任务可省掉审查环节，高风险任务必走全链路。

## 安全

- coherd 只做一件事：建 workspace+pane → 跑你给的命令 → 识别改名 → 发 brief。**它不提供任何 agent wrapper，不注入 env，不背 `--dangerously-skip-permissions` 这类权限责任**。
- **agent 的权限与密钥是你自己 CLI 配置的事，自负**。默认不绕过任何确认。
- reviewer 槽位建议最小权限（只读 + 跑验证），具体做法参考 docs/reviewer.md——是建议，不强制。
- 若你的 reviewer CLI 配置了跳过权限确认，那是在你自己的沙箱环境里做的决定，与 coherd 无关。

## 局限与扩展

- 冷门 agent CLI 不在 herdr 内置识别的 21 种之内就无法用（见 docs/agents.md）——诚实说，不是所有 CLI 都被识别。
- **有界不一致（bounded incoherence）**：reviewer 审查的可能是 executor 编辑**进行中**的树，不是原子快照——"fresh-eyes"（独立干净树审查）本轮不可达，完整树隔离列入 v2 待办（独立于跨集群隔离议题）。缓解：reviewer 验证前以 `git status`/`diff` 感知进行中改动，DoD 尽量定义在可复现状态。
- 当前固定 coordinator/executor/reviewer 三角色。未来可扩展更多角色/agent：多个执行者并行、专职测试 agent——架构上只是加 pane + spawn 的事。

https://github.com/org/repo  ← 占位 repo 链接