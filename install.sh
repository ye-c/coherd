#!/usr/bin/env bash
# coherd 安装脚本
#   bin/coherd        → ~/.local/bin/coherd   (已有则备份为 coherd.bak.*)
#   roles/CONTRACT.md + 4 per-role → ~/.config/coherd/ (已有则各自备份)
#   不安装 agent CLI / relay backend —— 那是用户自己的事
set -euo pipefail

BIN_DIR="${HOME}/.local/bin"
CFG_DIR="${HOME}/.config/coherd"
HERE="$(cd "$(dirname "$0")" && pwd)"

die()  { echo "install.sh: $*" >&2; exit 1; }
info() { echo "install.sh: $*"; }

# ── 前置依赖检查 (硬阻断: 缺则 die + 安装指引, 不自动装不碰 brew) ──
command -v herdr >/dev/null || die "未找到 herdr — coherd 的运行时依赖。安装: brew install herdr (或见 herdr.dev); 配置见 docs/configuration.md"
command -v jq    >/dev/null || die "未找到 jq — 安装: brew install jq / apt install jq; 配置见 docs/configuration.md"

# ── 安装 bin/coherd (symlink → repo; repo 更新即时反映, 免重跑) ──
[ -f "$HERE/bin/coherd" ] || die "缺失 $HERE/bin/coherd (请在 repo 内运行 install.sh)"
mkdir -p "$BIN_DIR"
# 迁移: 旧 cp 副本是普通文件(非 symlink) → 先备份保用户旧二进制, 再 ln
if [ -e "$BIN_DIR/coherd" ] && [ ! -L "$BIN_DIR/coherd" ]; then
  cp "$BIN_DIR/coherd" "$BIN_DIR/coherd.bak.$(date +%s)"
  info "已备份原有 $BIN_DIR/coherd → coherd.bak.*"
fi
# target 用绝对路径(symlink 以 link 所在目录解析, 相对路径会断); 已是 symlink 直接重指不备份
ln -sf "$HERE/bin/coherd" "$BIN_DIR/coherd"
chmod +x "$HERE/bin/coherd"   # 幂等: 确保 target 可执行(不 chmod symlink 本身)
info "已安装 $BIN_DIR/coherd → $HERE/bin/coherd (symlink)"

# ── 拷贝契约文件 (CONTRACT.md + 4 per-role) ──
# 旧版单文件 roles/ROLES.md 已拆分为 5 文件; 用户已有 ROLES.md 时备份保留 (旧档不删, 给用户手动迁移窗口)
ROLE_DOCS=("coordinator" "executor" "reviewer" "libero")
[ -f "$HERE/roles/CONTRACT.md" ] || die "缺失 $HERE/roles/CONTRACT.md"
mkdir -p "$CFG_DIR"
if [ -e "$CFG_DIR/ROLES.md" ]; then
  cp "$CFG_DIR/ROLES.md" "$CFG_DIR/ROLES.md.bak.$(date +%s)"
  info "已备份原有 $CFG_DIR/ROLES.md → ROLES.md.bak.* (旧版单文件, 内容已并入 CONTRACT.md + per-role)"
fi
_install_doc() { # 文件名 → 装到 $CFG_DIR (已有则备份后覆盖)
  local f="$1"
  [ -f "$HERE/roles/$f" ] || die "缺失 $HERE/roles/$f"
  if [ -e "$CFG_DIR/$f" ]; then
    cp "$CFG_DIR/$f" "$CFG_DIR/$f.bak.$(date +%s)"
    info "已备份原有 $CFG_DIR/$f → $f.bak.*"
  fi
  cp "$HERE/roles/$f" "$CFG_DIR/$f"
  info "已安装 $CFG_DIR/$f"
}
_install_doc "CONTRACT.md"
for _rd in "${ROLE_DOCS[@]}"; do
  _install_doc "$_rd.md"
done
unset _rd _install_doc ROLE_DOCS

# ── 安装 role skills 到共享目录 + Claude Code 软链 ──
#   源: roles/skills/<name>/SKILL.md → ~/.agents/skills/<name>/(pi 等从此读)
#   Claude Code 读 ~/.claude/skills/<name> → 软链到上面的共享目录 (对等 herdr 做法)
AGENT_SKILLS="${HOME}/.agents/skills"
CLAUDE_SKILLS="${HOME}/.claude/skills"
if [ -d "$HERE/roles/skills" ]; then
  mkdir -p "$AGENT_SKILLS" "$CLAUDE_SKILLS"
  for sk in "$HERE"/roles/skills/*; do
    [ -f "$sk/SKILL.md" ] || continue
    name="$(basename "$sk")"
    # 已有真实文件(非 symlink)先备份, 再重指 (幂等)
    if [ -e "$CLAUDE_SKILLS/$name" ] && [ ! -L "$CLAUDE_SKILLS/$name" ]; then
      mv "$CLAUDE_SKILLS/$name" "$CLAUDE_SKILLS/$name.bak.$(date +%s)"
      info "已备份原 $CLAUDE_SKILLS/$name"
    fi
    rm -rf "$AGENT_SKILLS/$name"
    cp -R "$sk" "$AGENT_SKILLS/$name"
    ln -sfn "../../.agents/skills/$name" "$CLAUDE_SKILLS/$name"
    info "已安装 skill $name → $AGENT_SKILLS/$name, 软链 $CLAUDE_SKILLS/$name"
  done
else
  info "无 roles/skills/, 跳过 skill 安装"
fi

# ── 下一步 ──
cat <<'EOF'

下一步:
  1. 确认三个 agent CLI 可用 (herdr 内置识别 21 种, 见 docs/agents.md)
  2. 可选: 每个角色配置启动命令, 见 docs/configuration.md
     export COHERD_COORDINATOR_CMD=...   (或写 ~/.config/coherd/coherd.conf)
     export COHERD_EXECUTOR_CMD=...
     export COHERD_REVIEWER_CMD=...
     都未设置时, coherd 回退找 PATH 中的 pi / omp / cc
  3. 起飞: coherd [REPO] [LABEL]
EOF