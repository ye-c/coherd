#!/usr/bin/env bash
# coherd 安装脚本
#   bin/coherd        → ~/.local/bin/coherd   (已有则备份为 coherd.bak.*)
#   roles/ROLES.md    → ~/.config/coherd/ROLES.md (已有则备份)
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

# ── 拷贝 roles/ROLES.md ──
[ -f "$HERE/roles/ROLES.md" ] || die "缺失 $HERE/roles/ROLES.md"
mkdir -p "$CFG_DIR"
if [ -e "$CFG_DIR/ROLES.md" ]; then
  cp "$CFG_DIR/ROLES.md" "$CFG_DIR/ROLES.md.bak.$(date +%s)"
  info "已备份原有 $CFG_DIR/ROLES.md → ROLES.md.bak.*"
fi
cp "$HERE/roles/ROLES.md" "$CFG_DIR/ROLES.md"
info "已安装 $CFG_DIR/ROLES.md"

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