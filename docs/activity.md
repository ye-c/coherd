# 活性观测与断链排查（人工按需，不进 brief）

> 用途：集群是**事件驱动 + 沉默即故障**（`CONTRACT.md` §7），没有任何守护进程监控活性。
> 需要判断"卡住了还是在干活"时，用下面几条配方看 session 审计日志。
> **这些配方不注入 agent context、不进 brief、不产生任何消息**——纯本地读文件。

## 0. 找到要看哪个 session

session 目录形如 `~/.config/coherd/sessions/<ws>-<YYYYMMDDHHMMSS>-<pid>/`，每次启动一个（`bin/coherd` 建）。

```bash
ls -t ~/.config/coherd/sessions | head -5          # 最新 5 个（按修改时间倒序）
SESSION=~/.config/coherd/sessions/$(ls -t ~/.config/coherd/sessions | head -1)
```

也可以从 pane 里问 agent 自己（brief 里给了 `session <路径>`），或按 ws 短号筛：`ls -d ~/.config/coherd/sessions/w2p-*`。

## 1. 时间线：最近 20 条消息

事件行 schema：`{ws,from,to,type,msg_id,ts,body}`（`ts` 为 UTC ISO8601，`body` 为未带标记前缀的原始正文）。

```bash
jq -r '"\(.ts[11:19]) \(.from)→\(.to) [\(.type)] \(.body[0:50])"' "$SESSION/events.log" | tail -20
```

输出每行形如 `07:50:51 coordinator→executor [feedback] 分派 T-4a SIGUSR1 注册 + dump 函数 + fault 文件白名单`。
看"谁最后说话、说的是哪一环"，对 §7 D10 映射表即可判断下一环该谁动。

## 2. 静默时长：最后一条消息距今多少分钟

```bash
last_ts=$(jq -r '.ts' "$SESSION/events.log" | tail -1)
last_epoch=$(date -u -d "$last_ts" +%s 2>/dev/null \
  || date -u -j -f "%Y-%m-%dT%H:%M:%S" "${last_ts%%.*}" +%s)
echo "$(( ( $(date -u +%s) - last_epoch ) / 60 )) 分钟无新消息"
```

判据（软，依任务规模自定）：**>120 分钟无任何消息**且时间线尾部不是 `approve:`/交付 → 断链候选。
典型断链形态：交审 `feedback` 已发但 reviewer 无结论；分派已发但 executor 连开工 ack 都没有。
此时按 `CONTRACT.md` §2「防重复成环」先 `herdr agent read <peer>` 查证据，**不建议直接重发**。

## 3. 各角色最后活动：谁还活着

```bash
jq -r 'select(.from) | [.ts[11:19], .from, .to, (.body[0:40])] | @tsv' "$SESSION/events.log" \
  | awk -F'\t' '{last[$2]=$0} END {for (k in last) print last[k]}' | sort
```

某角色整场没有记录 = 它要么没被唤醒过，要么 pane 已挂——去对应 pane 看提示符。

## 4. 计数：feedback / notify 各多少条（判断是否被话痨拖慢）

```bash
jq -r '.type' "$SESSION/events.log" | sort | uniq -c
```

健康 session 的每票往返应为 **4 条**（分派 feedback → 交审 feedback → approve/revise 回流 notify → 必要的开工 ack），
见 `CONTRACT.md` §7 批处理纪律。显著高于此值 = 有冗余广播或重发，按契约查哪一环多发了。

## 注意

- `events.log` 只有**发送侧审计**，不含送达结果（`accepted` 也不落盘）。"日志里有" ≠ "对端消费了"——见 `push.send_prompt` 的 docstring。
- 冷启动（还没有 session 目录）时事件落到全局兜底 `~/.config/coherd/events.log`，配方把 `$SESSION/events.log` 换成它即可。
- 旧 session 目录不会自动清理，历史排查够用；要清自己挑老的删（无归档命令，`CONTRACT.md` §4）。