# coherd

coherd 把多个 AI agent 组织成一个小团队：一个规划、一个干活、一个审查。编排逻辑已内置，配好 backend 即用。

> ⚠️ 安全须知：本 repo 不提供任何 agent wrapper、不绕过任何权限确认。agent 的权限与密钥由你自己的 CLI 配置负责，详见下文"安全"与 roles/reviewer.md。

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
| ------ | ------ | ------ |
| herdr | 终端多路复用器；管理 workspace/pane/agent | <https://github.com/…> |
| jq | 解析 herdr JSON 输出 | `brew install jq` |
| 任意 agent CLI ×3 | 三个槽位各一个；必须是 herdr 内置识别的 21 种之一（见 docs/agents.md） | 各自官方安装方式 |

> 不需要 pi/omp/claude code 三件套——你手上的任何 herdr 可识别 agent 都能填进槽位。也**不需要** coherd 替你配置模型/密钥：各 CLI 的认证配置由你自己维护。

## 安装

```bash
# 手动安装（install.sh 亦可用）
cp bin/coherd ~/.local/bin/                 # 或 /usr/local/bin，确保在 PATH
mkdir -p ~/.config/coherd
cp roles/CONTRACT.md roles/coordinator.md roles/executor.md roles/reviewer.md roles/libero.md ~/.config/coherd/
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

都不设置时，回退查找 PATH 中的 `pi` / `omp` / `cc`（其中 `cc` 有双重含义——既是回退命令名，通常也指你的 Claude Code）；再找不到就报错并指向 docs/configuration.md。

## 用法

```bash
coherd [init] [-p|--portrait] [-t|--tabs] [REPO] [LABEL]
# REPO 仓库目录（默认当前目录）；LABEL workspace 标签（默认仓库名）
# init 强制(重)建：同 label 已存在时先关闭再重建（CONTRACT.md/brief/agent 配置改动后重启用）；不存在则等同普通创建
# -p / --portrait 竖屏布局（默认横屏，无需赋值，存在即启用）
# -t / --tabs     每角色独立 tab：1 coord / 2 rev / 3 exec / 4 libero(手动, 不 spawn)；与 -p 互斥，tabs 优先
```

- 横屏（默认）：reviewer 左上 / executor 右上 / coordinator 下全宽
- 竖屏：`-p` / `--portrait` 触发 — coordinator 上 / reviewer 中 / executor 下
- tabs：`-t` / `--tabs` 触发 — 每角色独立 tab（1 coord / 2 rev / 3 exec），另备 4-libero 自由 tab 供手动加载

```bash
coherd                              # 在当前目录起集群（横屏）
coherd ~/code/myapp                 # 指定仓库
coherd -p ~/code/myapp mylabel      # 竖屏 + 自定义标签
coherd -t ~/code/myapp              # 每角色独立 tab（含手动 libero tab）
coherd init ~/code/myapp            # 强制重建同 label 集群（已存在先关闭）
```

重复运行同一 label 不会重建：已存在则聚焦打开（`init` 子命令除外，它会先关闭再重建）。任一路径不通（缺 jq、缺命令行配置）会直接报错退出。

## 三 agent 协作契约

完整契约见 `roles/CONTRACT.md`（公共，安装到 `~/.config/coherd/CONTRACT.md`）+ 四份 per-role（`roles/{coordinator,executor,reviewer,libero}.md`），要点：

- **分派契约**：coordinator→executor 每条任务必带 4 字段——objective / DoD 验收标准 / 输出格式 / 工具边界。字段缺了先补，模糊不干活。
- **审查循环**：reviewer 每次必跑验证命令 + 三查（正确性/安全/可维护性）+ 给双向结论；revise 上限 2 轮。
- **工具白名单**：coordinator 只读/检索，executor 完整编辑，reviewer 只读审查；任务级边界与白名单取交集。
- **规模缩放**：低风险小任务可省掉审查环节，高风险任务必走全链路。

## 安全

- coherd 只做一件事：建 workspace+pane → 跑你给的命令 → 识别改名 → 发 brief。**它不提供任何 agent wrapper，不注入 env，不背 `--dangerously-skip-permissions` 这类权限责任**。
- **agent 的权限与密钥是你自己 CLI 配置的事，自负**。默认不绕过任何确认。
- reviewer 槽位建议最小权限（只读 + 跑验证），具体做法参考 roles/reviewer.md——是建议，不强制。
- 若你的 reviewer CLI 配置了跳过权限确认，那是在你自己的沙箱环境里做的决定，与 coherd 无关。

## 局限

- 冷门 agent CLI 不在 herdr 内置识别的 21 种之内就无法用（见 docs/agents.md）。
- **有界不一致（bounded incoherence）**：reviewer 审查的可能是 executor 编辑**进行中**的树，不是原子快照。缓解：reviewer 验证前以 `git status`/`diff` 感知进行中改动，DoD 尽量定义在可复现状态。
