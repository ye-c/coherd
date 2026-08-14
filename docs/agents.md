# Agent 槽位与 herdr 识别

coherd 的三个角色（coordinator / executor / reviewer）是**槽位**。它们装什么 agent 由你决定——唯一硬约束：**该 agent 的 CLI 进程能被 herdr 识别**。

## herdr 内置识别 21 种 agent

herdr 通过探测进程特征识别 agent，内置支持以下 21 种（`herdr agent` 的 kinds 列表）：

```
pi  claude  codex  gemini  cursor  devin  agy  cline  omp
mastracode  opencode  copilot  kimi  kiro  droid  amp  grok  hermes  kilo  qodercli  maki
```

对应常见 CLI：

| kind | CLI | 备注 |
|------|-----|------|
| `pi` | pi-coding-agent | 协调型 agent |
| `omp` | oh-my-pi | 执行型 agent |
| `claude` | Claude Code | 通用 agent |
| `codex` / `gemini` / `cursor` / `opencode` … | 各家 CLI | 列表内皆可用 |

诚实边界：**冷门 CLI 不在上述 21 种内 = herdr 识别不了 = coherd 用不了**（识别阶段会超时）。这不是 coherd 的 bug；herdr 未内置该探测能力。对策：换用列表内 CLI，或等 herdr 扩展。

coherd 启动时**不使用 `--kind` 指定**（历史上 `agent start --kind pi/omp` 是硬编码；现在三角色统一 `pane run <CMD>` 再由 herdr 自动识别进程）。

## 三角色 = 三独立实例（硬边界）

- 三个槽位必须由**三个独立 agent 实例**填充。
- 同一个 agent 实例兼任两角 = 自己写、自己审 = 单 agent 自评，直接违背角色分离设计（ROLES.md §1 注记）。coherd 不禁止你这么配，但后果自负，reviewer 也会拒审自审产出。

## 怎么把你的 agent 填进槽位

```bash
# 方式一: 环境变量（临时）
export COHERD_COORDINATOR_CMD=codex        # 用 codex 当 coordinator
export COHERD_EXECUTOR_CMD=~/bin/my-omp    # 用你的自定义 wrapper
export COHERD_REVIEWER_CMD=claude          # 用 claude code 当 reviewer
coherd ~/code/myapp

# 方式二: conf 文件（持久）— 见 docs/configuration.md
# ~/.config/coherd/coherd.conf
```

wrapper 示例（agent 私有配置自备，coherd 不碰）：

```bash
#!/usr/bin/env bash
# ~/bin/my-reviewer —— 自带认证/模型配置的 reviewer wrapper
set -a; source ~/.agents/env; set +a
exec claude "$@"            # 你自己的 CLI + 你自己的 flag
```

要点：`COHERD_*_CMD` 就是"怎么启动这个角色的 agent"的完整答案，coherd 原样执行、不做任何加工。