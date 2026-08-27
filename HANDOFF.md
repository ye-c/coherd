# HANDOFF.md — coherd 现状盘点 + 归档闭环

> **定位**：本文取代旧「v5 重构交接」文档（其方案已全部落地并经吃狗粮验证，历史保留在 git）。本文件是当前及后续集群的**清晰起点**：当前能力、格式约定、已知 issue、待办。**重点待办 = 归档闭环（见 §3）**。

---

## §1 当前状态（2026-08-27 · 基于 `feat/v5-handoff`）

### 已实现并经「吃狗粮」验证

| 能力 | 说明 | 状态 |
| --- | --- | --- |
| `coherd task` CLI | 5 子命令 `new / list / show / archive / status`；bash launcher re-exec 收编 | ✅ 验证 |
| task id | `<ws>-<14位UTC秒戳>`（单 dash，去序号/hash）；ws `ID_RE` 防注入，秒段 `\d{14}` | ✅ 改并验证 |
| list 容错 | 遇 malformed/旧格式 tracker `try/except ValueError` → warning 跳过不崩（`cli.py`） | ✅ |
| id 去重兜底 | 同 id 已存在 → `write_new` 抛 `FileExistsError`，不覆盖 | ✅ |
| 事件驱动契约 | CONTRACT §2 三铁律（事件驱动 / 内容·信号分离 / push 格式）；内容落文件、prompt 只送信号+路径 | ✅ R1 |
| tracker 权威副本 | 协调者侧 `~/.config/coherd/tasks/<ws>/`，executor 契约上不可写 | ✅ R1 |
| 归档命名规范 | 见 §2，已全量统一 | ✅ |

### 已知 issue（未修，明确记录）

1. **`show` / `archive` / `status` 对 malformed tracker 抛未捕获 `ValueError` traceback**（仅 `list` 有容错）。定向访问+命中概率低，故不阻塞；要优雅化可另开一轮（reviewer 注记）。
2. **归档内容贫瘠** → 即 §3 归档闭环的核心痛点，待落地。

### 技术栈/布局

- 两入口刻意分离：`bin/coherd`（bash，拉起）= 集群拉起；`coherd task`（python/typer）= 数据管理，只做文件 CRUD + 格式校验，**永不做角色决策**（滑坡护栏，见 CONTRACT「CLI 集成」节）。
- 依赖：python + typer + uv，editable install（改 `src/` 即时生效，无需重装）。
- 目录：`~/.config/coherd/{tasks,reviews,archive}/<ws>/`。

---

## §2 格式约定（当前生效，直接照做）

| 桶 | 放什么 | 命名 |
| --- | --- | --- |
| `tasks/<ws>/` | 活动 tracker | 文件名 = id = `<ws>-<YYYYMMDDHHMMSS>` |
| `archive/<ws>/` | 已完成 tracker | `coherd task archive` 原样 rename（文件名=id 不变），**只放 tracker，不放 review** |
| `reviews/<ws>/` | 审查/讨论结论 | `<approve | revise | discuss>-<taskid>.md`（前缀保留态，后缀关联任务 id；同任务 approve+revise 靠前缀区分不撞名） |

- 归档 tracker 重命名 = 同步改 frontmatter `id`（须=文件名）+ 补 `created_at`。
- 已归档历史（w2a/w2c/w2e）已全量统一成此规范（语义名如 `r2-task-cli`/`R1` 已弃，改秒戳）。

---

## §3 归档闭环（重点待办）

### 3.1 问题（用户提出：归档意义在哪？难道只能用户点名才有人看？）

**诊断（coordinator × reviewer 收敛）：根因是"归档内容贫瘠 + 无自动消费路径"，二缺一律救不回。**

- 当前 archive 存的是**"要做什么"**（objective / dod / output_path），不是**"做了什么 / 怎么做的 / 踩了什么坑 / 怎么解的"**。
- 旧 HANDOFF 记录的思考、报错、返工原因**全留在跟踪记录之外**，归档后沉没。哪怕有人回读、grep，也 grep 不到经验教训。
- 结果是 archive 成了"死终点"：只进不出，唯一消费入口是用户大脑点名。

**方向逐条裁（reviewer 定界）**：

| 方向 | 裁决 | 理由 |
| --- | --- | --- |
| 归档时强制写**复盘段**（决策理由/踩坑/教训） | ✅ **最有价值，优先做** | 让 archive 从"任务定义仓"→"可检索经验仓"，内容先有价值 |
| ①② CLI 可查 / 集群记忆扫描机制 | ⏸ YAGNI 暂缓 | 当前才个位数文件，`grep -r` 够用；先有可消费内容，再谈扫描机制 |
| ③ 评审结论回流 | ✅ 轻量可做 | 提炼 revise 的错误模式，非原样回流结论 |
| ④ 统计复盘（任务数/approve率/耗时） | ❌ 削掉 | 任务量太少无统计信号，给没跑起来的系统造仪表盘 |

### 3.2 待落地（下一步集群做，走 executor→reviewer→coordinator）

1. **tracker schema 增复盘段**：frontmatter/body 增加约定字段（如 `retro` / `lessons` / `decision`），记录"关键决策理由 / 踩坑 / 教训 / 返工原因"。
2. **写入时机**：归档时（或任务完成时）强制补全复盘段，而不是只写 objective/dod。
3. **可检索**：凭字段能 grep 到经验（检索用 grep 即够，暂不做 CLI 查询）。
4. （可选，轻量）reviewer 从历史 `revise` 结论提炼错误模式，沉淀到一处可复用清单。

> 前提纪律：**先做内容模板让档案值钱，再造读取机制**。别倒过来。

---

## §4 待办速览（非本期）

- 已知 issue #1：show/archive/status 对 malformed 的 traceback 优雅化。
- §3.2 归档复盘段落地。
- （YAGNI 长期挂起）parent_id revise 链、跨 ws 关联、统计复盘仪表盘、CLI 归档查询。

---

## §5 历史

- v5 重构（事件驱动契约 + coherd task CLI + 持久锚点 + 两入口接线）：R1–R4 已完成并吃狗粮验证，设计/轮次/讨论历程见 git 历史（旧 HANDOFF）。
- 本 session 落地：list 容错修复 → 版本 0.1.1 → id 秒戳格式（去序号/hash）→ 归档命名全量统一 → 归档闭环定界。
