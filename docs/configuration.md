# 配置

coherd 的配置面很小：三个槽位的启动命令 + 布局。所有配置走 `COHERD_` 前缀环境变量，可选配置文件为 `~/.config/coherd/coherd.conf`。

## 三槽位启动命令（契约）

| 变量 | 角色 | 说明 |
|------|------|------|
| `COHERD_COORDINATOR_CMD` | coordinator | 启动协调者 agent 的命令（可带参数） |
| `COHERD_EXECUTOR_CMD` | executor | 启动执行者 agent 的命令（可带参数） |
| `COHERD_REVIEWER_CMD` | reviewer | 启动审查者 agent 的命令（可带参数） |

契约：
- 值是**完整命令字符串**（路径 + 参数），经 `pane run` 原样执行，例如 `~/bin/executor-cli --cwd .`。含空格需自行引号；coherd 不解析不加工。
- 命令启动的进程必须能被 herdr 识别成 agent（herdr 内置 21 种 agent 探测，见 docs/agents.md），否则 coherd 会在识别阶段超时报错。
- **coherd 不注入任何环境变量、不加载 ~/.agents/env、不传 flag**。如果命令需要密钥/模型配置，写在你自己 wrapper 里面（比如 `export` + exec 你的 CLI）。

## 默认回退（未设置 CMD 时）

| 变量未设置 → | 回退查找 PATH | 仍缺失 → |
|--------------|--------------|-----------|
| `COHERD_COORDINATOR_CMD` | `pi` | die，提示 docs/configuration.md |
| `COHERD_EXECUTOR_CMD` | `omp` | 同上 |
| `COHERD_REVIEWER_CMD` | `cc` | 同上 |

回退是兼容旧集群 CLI 命名（pi/omp/cc）的便利，不是 coherd 对特定 CLI 的依赖。

## coherd.conf

可选，`~/.config/coherd/coherd.conf`，被 `source` 执行（bash 语法，非解析 key=value）：

```bash
# 示例: ~/.config/coherd/coherd.conf
COHERD_COORDINATOR_CMD=~/bin/my-coordinator
COHERD_EXECUTOR_CMD=~/bin/my-executor
COHERD_REVIEWER_CMD=~/bin/my-reviewer
COHERD_LAYOUT=auto
```

优先级：**已显式设置的 `COHERD_*` 环境变量 > conf**。conf 先加载，再被环境中已存在的同名变量覆盖——命令行 `COHERD_X=… coherd` 永远压过 conf。

仅 `COHERD_` 前缀变量会被 conf 影响；其他变量照常随 pane shell 继承，coherd 不干预。

## 其他变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `COHERD_LAYOUT` | `auto` | `portrait` / `landscape` / `auto`（auto = xrandr 像素 → cell 近似） |
| `COHERD_CONF` | `~/.config/coherd/coherd.conf` | conf 路径；可在运行前覆盖 |

## FAQ：coherd 报"未找到 xx 的启动命令"

1. 设置对应 `COHERD_*_CMD` 指向你的 agent CLI（推荐），或
2. 把旧名 `pi`/`omp`/`cc` 放进 PATH，或
3. 确认你的 CLI 在 herdr 21 种可识别列表内（docs/agents.md），否则改用列表内的。

## herdr 相关

- coherd 需要 herdr CLI 在 PATH；server 未运行时自动后台拉起 headless server。
- agent 识别靠 herdr 内置 21 种 kind 探测进程（不经 `--kind` 指定）：coherd 一律 `pane run <CMD>` 再探测。列表与机制见 docs/agents.md。