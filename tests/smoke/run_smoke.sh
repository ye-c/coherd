#!/usr/bin/env bash
# coherd 双角色 simple 模式端到端冒烟 T2–T7 (spec w5f-20261010141636 §5)
#
#   · fake herdr / fake sleep 前置 PATH → 不依赖真 herdr 与真 agent CLI, 可 CI
#   · HOME 指向临时目录 → 契约文档与 session 目录都落临时区, 不碰真实 ~/.config 与用户 session
#   · trap 清理 → 可重复跑不残留
#
# 用法: bash tests/smoke/run_smoke.sh      # 退出码 0 = T2–T7 全过
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BIN="$ROOT/bin/coherd"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/coherd-smoke.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

export HOME="$WORK/home"                 # 隔离: 契约文档/conf/session 全在临时 HOME
export PATH="$HERE/bin:$PATH"            # fake herdr + fake sleep 前置
export COHERD_CONF=/dev/null             # 不吃用户 coherd.conf
export COHERD_COORDINATOR_CMD=coord-cli COHERD_EXECUTOR_CMD=exec-cli COHERD_REVIEWER_CMD=rev-cli
export COHERD_LED_CMD=led-cli COHERD_DEV_CMD=dev-cli
mkdir -p "$HOME/.config/coherd" "$WORK/repo"
cp "$ROOT"/roles/*.md "$HOME/.config/coherd/"   # coherd 启动会检查契约文件存在

FAILED=0
ok() { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; FAILED=1; }
eq() { # desc expected actual
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 — expected [$2] got [$3]"; fi
}
contains() { # desc needle file
  if [ -f "$3" ] && grep -qF -- "$2" "$3"; then ok "$1"; else bad "$1 — [$2] 未出现在 $3"; fi
}
cnt() { cat "$2" 2>/dev/null || echo 0; }
state() { # 每个 case 一个干净 state 目录 (同一 case 内多次启动共用)
  export COHERD_SMOKE_STATE="$WORK/st-$1"
  mkdir -p "$COHERD_SMOKE_STATE"
}
run_coherd() { # tag arg... — 退出码非 0 由调用方判
  local tag="$1"; shift
  "$BIN" "$@" >"$COHERD_SMOKE_STATE/out-$tag" 2>&1
}
slug_of() { printf 'w%s' "$1"; }   # label → agent 名前缀 (ws id = w<LABEL 大写>, slug = 小写)

case_t2() {
  printf '\n== T2: coherd -s 起 2 tab (1 led / 2 dev) + 2 agent + brief 送达锚\n'
  state t2; local st="$COHERD_SMOKE_STATE"
  run_coherd t2 -s "$WORK/repo" sm1 || { bad "coherd -s 退出非 0: $(cat "$st/out-t2")"; return; }

  eq "pane run 恰好 2 条" "2" "$(wc -l <"$st/runs" | tr -d ' ')"
  eq "tab create 恰好 1 次 (led tab + dev tab)" "1" "$(cnt x "$st/tabcnt")"
  eq "split 恰好 0 次 (simple 恒 tabs)" "0" "$(cnt x "$st/splitcnt")"
  eq "led 占 root pane (tab#1)" "pane-root-1|led-cli" "$(grep -F -- 'led-cli' "$st/runs")"
  eq "dev 占 tab pane (tab#2)" "pane-tab-1|dev-cli" "$(grep -F -- 'dev-cli' "$st/runs")"
  eq "rename → wsm1-led" "pane-root-1|wsm1-led" "$(grep -F -- '|wsm1-led' "$st/renames")"
  eq "rename → wsm1-dev" "pane-tab-1|wsm1-dev" "$(grep -F -- '|wsm1-dev' "$st/renames")"

  # 送达锚: prompt 点名 dev + 全 kind 先 Enter 提交, 再验 seq 较基线变化 (不用 agent_status != blocked)
  # herdr 升级后 agent prompt 对全 kind 只 paste 不提交, seq 在文本到达即涨(非消费); 需 Enter 后重读确认。
  eq "dev prompt 恰好送达 1 次" "1" "$(grep -cF -- 'agent prompt wsm1-dev' "$st/herdr.log")"
  eq "dev seq 基线=1 → 消费后=2" "1 2" \
    "$(awk -F'|' '$1=="wsm1-dev"{print $2}' "$st/seqs" | sort -u | tr '\n' ' ' | sed 's/ $//')"
  contains "dev brief 点名自身 agent 名" "agent 名 wsm1-dev" "$st/brief_wsm1-dev"
  contains "dev brief 指 CONTRACT-simple.md" "CONTRACT-simple.md" "$st/brief_wsm1-dev"
  contains "dev brief 指 dev.md" "dev.md" "$st/brief_wsm1-dev"
  contains "dev brief 单 standby 指令 (指向 led)" 'coherd notify wsm1-led "standby"' "$st/brief_wsm1-dev"
  contains "led brief 指 led.md" "led.md" "$st/brief_wsm1-led"
  contains "led brief 待机=被动接收" "被动接收不回执" "$st/brief_wsm1-led"
}

case_t3() {
  printf '\n== T3: 同 label 重复启动 → focus 不重建; init → 先 close 再重建\n'
  state t3; local st="$COHERD_SMOKE_STATE"
  run_coherd t3a -s "$WORK/repo" sm3 || { bad "首次启动非 0: $(cat "$st/out-t3a")"; return; }
  eq "首次: create 1 次" "1" "$(cnt x "$st/createcnt")"

  local f0; f0="$(cnt x "$st/focuscnt")"
  run_coherd t3b -s "$WORK/repo" sm3 || { bad "重复启动非 0: $(cat "$st/out-t3b")"; return; }
  eq "重复: create 仍 1 次 (未重建)" "1" "$(cnt x "$st/createcnt")"
  eq "重复: 该轮 focus 1 次" "1" "$(( $(cnt x "$st/focuscnt") - f0 ))"
  eq "重复: 未再 pane run" "2" "$(wc -l <"$st/runs" | tr -d ' ')"
  contains "重复: 提示已存在并聚焦" "已存在" "$st/out-t3b"

  run_coherd t3c -s init "$WORK/repo" sm3 || { bad "init 非 0: $(cat "$st/out-t3c")"; return; }
  eq "init: 先 close 1 次" "1" "$(cnt x "$st/closecnt")"
  eq "init: create 2 次 (重建)" "2" "$(cnt x "$st/createcnt")"
}

case_t4() {
  printf '\n== T4: 三角色默认路径回归 + simple 无 coordinator/reviewer 残留 + 跨 label 不串\n'
  state t4tri; local st="$COHERD_SMOKE_STATE"
  run_coherd tri "$WORK/repo" tri1 || { bad "三角色启动非 0: $(cat "$st/out-tri")"; return; }
  eq "三角色: 3 pane run" "3" "$(wc -l <"$st/runs" | tr -d ' ')"
  eq "三角色: 2 split (横屏)" "2" "$(cnt x "$st/splitcnt")"
  eq "三角色: coordinator 下 pane" "pane-split-1|coord-cli" "$(grep -F -- 'coord-cli' "$st/runs")"
  eq "三角色: executor 右上 pane" "pane-split-2|exec-cli" "$(grep -F -- 'exec-cli' "$st/runs")"
  eq "三角色: reviewer root pane" "pane-root-1|rev-cli" "$(grep -F -- 'rev-cli' "$st/runs")"
  eq "三角色: renames 3 条" "3" "$(wc -l <"$st/renames" | tr -d ' ')"
  contains "三角色 brief 指 CONTRACT.md" "CONTRACT.md" "$st/brief_wtri1-coordinator"
  eq "三角色 brief 不含 CONTRACT-simple" "0" "$(grep -cF -- 'CONTRACT-simple' "$st/brief_wtri1-coordinator")"
  contains "三角色 brief 回执指 §7 D10" "CONTRACT §7 D10" "$st/brief_wtri1-coordinator"
  eq "跨 label: tri1 rename 全用自身 ws slug" "0" "$(awk -F'|' '{print $2}' "$st/renames" | grep -cv '^wtri1-')"

  state t4sim; st="$COHERD_SMOKE_STATE"
  run_coherd sim -s "$WORK/repo" sim1 || { bad "simple 启动非 0: $(cat "$st/out-sim")"; return; }
  eq "simple: 2 pane run (共 3 pane 不变)" "2" "$(wc -l <"$st/runs" | tr -d ' ')"
  eq "simple: 恒 tabs (tabcnt=1 splitcnt=0)" "1 0" "$(cnt x "$st/tabcnt") $(cnt x "$st/splitcnt")"
  eq "simple: renames 2 条" "2" "$(wc -l <"$st/renames" | tr -d ' ')"
  eq "simple: 无 coordinator 残留" "0" "$(grep -cF -- 'coordinator' "$st/renames")"
  eq "simple: 无 reviewer 残留" "0" "$(grep -cF -- 'reviewer' "$st/renames")"
  eq "跨 label: sim1 rename 全用自身 ws slug" "0" "$(awk -F'|' '{print $2}' "$st/renames" | grep -cv '^wsim1-')"
}

case_t5() {
  printf '\n== T5: simple 集群内 led → dev 送达 (标记注入)\n'
  state t5; local st="$COHERD_SMOKE_STATE"
  if [ ! -x "$ROOT/.venv/bin/coherd" ]; then
    bad "T5 需要 $ROOT/.venv/bin/coherd (coherd notify CLI) — 先跑 ./install.sh"
    return
  fi
  run_coherd t5s -s "$WORK/repo" sm5 || { bad "启动 simple 集群非 0: $(cat "$st/out-t5s")"; return; }

  HERDR_WORKSPACE_ID=wSM5 COHERD_ROLE=led "$BIN" notify wsm5-dev "test" \
    >"$st/notify1" 2>&1 || bad "led notify dev 退出非 0: $(cat "$st/notify1")"
  eq "led→dev 送达文本带发送方标记" "wsm5-dev|[led|notify]: test" "$(tail -1 "$st/prompts")"

  # dev 作为发送方时标记为 [dev|notify]: (标记 = 发送方 role; DoD 字面 '[dev|notify]' 只在此方向成立)
  HERDR_WORKSPACE_ID=wSM5 COHERD_ROLE=dev "$BIN" notify wsm5-led "test2" \
    >"$st/notify2" 2>&1 || bad "dev notify led 退出非 0: $(cat "$st/notify2")"
  eq "dev→led 送达文本带 [dev|notify] 标记" "wsm5-led|[dev|notify]: test2" "$(tail -1 "$st/prompts")"
}

case_t6() {
  printf '\n== T6: -s 恒两 tab / -s -t 冗余等价 / -s -p 忽略并告警\n'
  state t6a; local st="$COHERD_SMOKE_STATE"
  run_coherd a -s "$WORK/repo" sm6 || { bad "-s 非 0: $(cat "$st/out-a")"; return; }
  eq "-s: tabs=1 splits=0" "1 0" "$(cnt x "$st/tabcnt") $(cnt x "$st/splitcnt")"
  eq "-s: dev 在 tab pane" "1" "$(grep -cF -- 'pane-tab-1|dev-cli' "$st/runs")"

  state t6b; st="$COHERD_SMOKE_STATE"
  run_coherd b -s -t "$WORK/repo" sm7 || { bad "-s -t 非 0: $(cat "$st/out-b")"; return; }
  eq "-s -t: splits=0 tabs=1" "0 1" "$(cnt x "$st/splitcnt") $(cnt x "$st/tabcnt")"
  eq "-s -t: pane run 仍 2 (两 tab 各一)" "2" "$(wc -l <"$st/runs" | tr -d ' ')"
  eq "-s -t: dev 在 tab pane" "1" "$(grep -cF -- 'pane-tab-1|dev-cli' "$st/runs")"

  state t6c; st="$COHERD_SMOKE_STATE"
  run_coherd c -s -p "$WORK/repo" sm8 || { bad "-s -p 非 0: $(cat "$st/out-c")"; return; }
  contains "-s -p: 告警已忽略" "-p 无意义" "$st/out-c"
  eq "-s -p: 仍走 tabs (tabs=1 splits=0)" "1 0" "$(cnt x "$st/tabcnt") $(cnt x "$st/splitcnt")"
}

case_t7() {
  printf '\n== T7: --agent 按角色覆盖启动命令 (per-run, 优先于 COHERD_*_CMD) + 非法输入早退\n'
  state t7a; local st="$COHERD_SMOKE_STATE"
  run_coherd a -s --agent led=codex-x,dev=opencode-y "$WORK/repo" sm11 \
    || { bad "--agent 启动非 0: $(cat "$st/out-a")"; return; }
  eq "simple: led 命令被覆盖" "pane-root-1|codex-x" "$(grep -F -- 'codex-x' "$st/runs")"
  eq "simple: dev 命令被覆盖" "pane-tab-1|opencode-y" "$(grep -F -- 'opencode-y' "$st/runs")"
  eq "simple: env 的 COHERD_LED_CMD 未生效" "0" "$(grep -cF -- 'led-cli' "$st/runs")"
  eq "simple: rename 不受影响 (仍按 ws slug)" "2" "$(wc -l <"$st/renames" | tr -d ' ')"

  state t7b; st="$COHERD_SMOKE_STATE"    # 三角色: 只覆盖 executor, 其余仍走 env
  run_coherd b --agent executor=codex-z "$WORK/repo" sm12 \
    || { bad "--agent 三角色启动非 0: $(cat "$st/out-b")"; return; }
  eq "三角色: 指定 executor 被覆盖" "pane-split-2|codex-z" "$(grep -F -- 'codex-z' "$st/runs")"
  eq "三角色: 未指定的 coordinator 保持 env 值" "pane-split-1|coord-cli" "$(grep -F -- 'coord-cli' "$st/runs")"
  eq "三角色: 未指定的 reviewer 保持 env 值" "pane-root-1|rev-cli" "$(grep -F -- 'rev-cli' "$st/runs")"

  # 非法输入一律早退且不建集群 (校验在 herdr server/布局之前)
  # tag 用显式序号: arg 归一化会撞名 (led 与 led= 都成 bad-led), 撞名 → 共用 state 目录/输出文件, 隔离被打破
  local i=0 case_spec arg needle tag
  for case_spec in "leed=codex-x|未知角色" "led|缺 '='" "led=|缺命令"; do
    i=$((i+1)); tag="bad-$i"
    arg="${case_spec%%|*}"; needle="${case_spec##*|}"
    state "t7-$tag"; st="$COHERD_SMOKE_STATE"
    if run_coherd "$tag" -s --agent "$arg" "$WORK/repo" sm13; then
      bad "--agent '$arg' 应报错退出"
    else
      ok "--agent '$arg' 报错退出 (exit≠0)"
    fi
    contains "--agent '$arg' 报错含 '$needle'" "$needle" "$st/out-$tag"
    eq "--agent '$arg': 未 pane run (未建集群)" "0" "$(cnt x "$st/runs")"
  done
}

printf 'coherd simple 模式冒烟 T2–T7 (fake herdr, HOME 隔离, work=%s)\n' "$WORK"
case_t2
case_t3
case_t4
case_t5
case_t6
case_t7

if [ "$FAILED" = 0 ]; then
  printf '\nALL PASS (T2–T7)\n'
else
  printf '\nFAILED — 见上方 FAIL 行\n'
fi
exit "$FAILED"