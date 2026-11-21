"""coherd.diff — 分域改动机械核验（纯事实提取，零判定）。

职责边界（滑坡护栏，spec FR2）：
  只做「方案白名单解析 → 执行者归属推导 → git 改动采集 → 三组路径分类 → 报表渲染」，
  绝不输出任何审查判定（通过/退回/警告），退出码只反映命令是否执行成功（视野内是否有越界文件不影响退出码，D1）。
  只读：git 查询不写工作树、不改索引、不切分支。

三组事实（FR1）：
  白名单内 = 命中本任务/执行者归属；他人域内 = 命中同方案其他执行者归属；白名单外 = 都不命中。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from . import tracker as T

# 归属标签规范词法 exec-<n>；紧凑复合形 exec-2/3 按前缀展开为独立标签（FR4）
_TAG_RE = re.compile(r"exec-(\d+(?:/\d+)*)")
# markdown 表格分隔行单元格：GFM 允许单连字符（`| - |`），故不用 {3,}
_SEP_CELL_RE = re.compile(r"^:?-+:?$")
# 白名单表头精确匹配（高度可辨列）：`文件` / `改动文件`；不做子串匹配，
# 否则「参考文件」「变更文件列表」等前置描述表会被误当白名单吞掉
_FILE_HEADERS = ("文件", "改动文件")

_EMPTY_CELLS = {"", "-", "—", "|"}


class DiffError(ValueError):
    """输入/数据异常（CLI 转非零退出，FR5）。"""


# ── 方案白名单解析 ───────────────────────────────────────────────


def _cells(line: str) -> list[str]:
    """切一行 markdown 表格为单元格（去首尾竖线与空白）。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _tables(lines: list[str]):
    """产出连续 markdown 表格块 `(header_cells, row_cells_list)`（要求第 2 行为分隔行）。"""
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].strip().startswith("|"):
            i += 1
            continue
        j = i
        while j < n and lines[j].strip().startswith("|"):
            j += 1
        block = lines[i:j]
        i = j
        if len(block) < 3:  # 表头 + 分隔行 + 至少一行数据
            continue
        sep = [c for c in _cells(block[1]) if c]
        if not sep or not all(_SEP_CELL_RE.match(c) for c in sep):
            continue
        yield _cells(block[0]), [_cells(r) for r in block[2:]]


def expand_tags(cell: str) -> set[str]:
    """单元格 → 归属标签集合：规范形 + 复合形展开，修饰散文一律丢弃（FR4）。"""
    tags: set[str] = set()
    for m in _TAG_RE.finditer(cell):
        for part in m.group(1).split("/"):
            tags.add(f"exec-{part}")
    return tags


def _norm_path(p: str) -> str:
    """路径规范化：剥行内代码包裹符号与首尾空白，去 './' 前缀。"""
    p = p.strip().strip("`").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def parse_plan_whitelist(plan_text: str) -> tuple[dict[str, set[str]], set[str]]:
    """解析方案白名单表格 → (路径→归属标签并集, 全表标签集合)。

    自适应列序：定位首个含「文件」列的表格（「归属」列可选）；非表格散文声明不在解析范围（spec §4）。
    同一路径跨行多次出现时归属取并集（FR4/AC4）。
    """
    path_to_owners: dict[str, set[str]] = {}
    all_tags: set[str] = set()
    for header, rows in _tables(plan_text.splitlines()):
        file_col = next(
            (i for i, c in enumerate(header) if c.strip(" `") in _FILE_HEADERS), None
        )
        if file_col is None:
            continue  # 非白名单表（如现状差异分析表）
        owner_col = next((i for i, c in enumerate(header) if "归属" in c), None)
        for cells in rows:
            if file_col >= len(cells):
                continue
            path = _norm_path(cells[file_col])
            if path in _EMPTY_CELLS:
                continue
            owners = (
                expand_tags(cells[owner_col])
                if owner_col is not None and owner_col < len(cells)
                else set()
            )
            path_to_owners.setdefault(path, set()).update(owners)
            all_tags |= owners
        if path_to_owners:
            break
    if not path_to_owners:
        raise DiffError("方案中未找到有效白名单表格（需含「文件」列的 markdown 表格）")
    return path_to_owners, all_tags


def _tag_key(tag: str) -> tuple[int, str]:
    m = re.fullmatch(r"exec-(\d+)", tag)
    return (int(m.group(1)), tag) if m else (10**9, tag)


def _tag_list(tags: set[str]) -> str:
    return ", ".join(sorted(tags, key=_tag_key)) if tags else "(无归属标签)"


def resolve_target_executor(all_tags: set[str], explicit: str | None) -> str | None:
    """执行者归属两级确定（D2/D3）：显式参数 > 整表唯一标签；其余一律报错，禁隐式猜测。

    返回 None 表示「整表归属当前任务」（无归属列或标签集合大小为 1），此时他人域内恒空。
    """
    if explicit:
        if explicit not in all_tags:
            raise DiffError(
                f"指定的执行者标签不在方案白名单内: {explicit}"
                f"（方案实际存在的标签: {_tag_list(all_tags)}）"
            )
        return explicit
    if len(all_tags) <= 1:
        return None
    raise DiffError(
        f"方案含多个执行者标签（{_tag_list(all_tags)}），需显式指定 --executor"
    )


# ── git 改动采集（FR3）───────────────────────────────────────────


def _run_git(args: list[str], cwd: str | Path | None = None) -> bytes:
    # GIT_OPTIONAL_LOCKS=0：只读核验不得因刷新索引去抢 index.lock——与并发 git commit 相撞会让
    # **对方** 取锁失败（CONTRACT §5 实测 git status vs commit 失败 64/69 轮，加该变量后 0 轮）
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=env)
    except FileNotFoundError:
        raise DiffError("未找到 git 命令（PATH 中不存在）")
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise DiffError(f"git {' '.join(args)} 失败: {detail or '(无输出)'}")
    return proc.stdout


def _nul_fields(out: bytes) -> list[str]:
    return [os.fsdecode(f) for f in out.split(b"\0") if f]


def parse_status_z(out: bytes) -> list[tuple[str, str]]:
    """解析 `git status --porcelain -z`。

    -z 定界彻底免疫 C-style 引号与八进制转义（含空格/非英文字符路径不失真，FR3/AC6）；
    重命名/复制条目在 -z 下顺序为 `<XY> to` 后接 `from`，两条路径均计入变更集（FR1）。
    """
    fields = _nul_fields(out)
    changes: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        status, path = entry[:2], entry[3:] if len(entry) > 3 else ""
        if status[:1] in ("R", "C") and i < len(fields):
            old = fields[i]
            i += 1
            if old:
                changes.append((status, old))
        if path:
            changes.append((status, path))
    return changes


def parse_name_status_z(out: bytes) -> list[tuple[str, str]]:
    """解析 `git diff --name-status -z`：状态与路径均为独立 NUL 字段，重命名给 old→new 双路径。"""
    fields = _nul_fields(out)
    changes: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        i += 1
        if i >= len(fields):
            break
        changes.append((status, fields[i]))
        i += 1
        if status[:1] in ("R", "C") and i < len(fields):
            changes.append((status, fields[i]))
            i += 1
    return changes


def get_git_changes(
    base: str | None = None, cwd: str | Path | None = None
) -> list[tuple[str, str]]:
    """采集改动（FR3）：缺省工作区未提交改动（-uall 穿透未跟踪目录至叶子文件）；指定基准则基准→工作树。"""
    if base:
        return parse_name_status_z(
            _run_git(["diff", "--name-status", "-z", base], cwd)
        )
    return parse_status_z(_run_git(["status", "--porcelain", "-z", "-uall"], cwd))


# ── 分类与渲染 ──────────────────────────────────────────────────


def classify_paths(
    changes: list[tuple[str, str]],
    path_to_owners: dict[str, set[str]],
    target_executor: str | None,
) -> dict[str, list[dict]]:
    """改动路径三分类：命中本域 / 命中他人域 / 都不命中（FR1，D3）。"""
    in_whitelist: list[dict] = []
    other_domain: list[dict] = []
    out_of_whitelist: list[dict] = []
    for status, path in changes:
        owners = path_to_owners.get(_norm_path(path))
        item = {"status": status.strip() or "?", "path": path}
        if owners is None:
            out_of_whitelist.append(item)
        elif target_executor is None or target_executor in owners:
            # 归属并集含本执行者即归本域，不重复计入他人域（AC4）
            in_whitelist.append(item)
        else:
            item["owners"] = owners
            other_domain.append(item)
    return {
        "in_whitelist": in_whitelist,
        "other_domain": other_domain,
        "out_of_whitelist": out_of_whitelist,
    }


def find_plan_file(task_data: dict) -> Path:
    """由 tracker 的 parent_spec 定位 `<spec>.plan.md`：先本 session 目录，再跨 session 目录。"""
    spec = str(task_data.get("parent_spec", "")).strip()
    task_id = str(task_data.get("id", "?"))
    if not spec:
        raise DiffError(f"任务 {task_id} 未关联上游方案（parent_spec 为空）")
    if not T.ID_RE.match(spec):
        raise DiffError(f"parent_spec 含非法字符: {spec!r}（需 [a-zA-Z0-9_-]）")
    name = f"{spec}.plan.md"
    task_path = Path(str(task_data.get("_path", "")))
    candidates = [task_path.parent / name]
    if T.SESSIONS_DIR.is_dir():
        candidates += sorted(T.SESSIONS_DIR.glob(f"*/{name}"))
    for c in candidates:
        if c.is_file():
            return c
    raise DiffError(f"方案文件不存在: {name}（在 {task_path.parent} 与会话目录中均未找到）")


def render_report(task_id: str, result: dict) -> str:
    """渲染纯事实报表（无任何判定词汇，FR2）。"""
    base = result.get("base")
    lines = [
        f"# 任务: {task_id} (执行者: {result.get('executor') or 'default'})",
        f"# 方案: {result.get('plan_path', '')}",
        f"# 基准: {'git diff ' + base if base else '工作区未提交改动'}",
        "",
    ]
    for label, key in (
        ("白名单内", "in_whitelist"),
        ("他人域内", "other_domain"),
        ("白名单外", "out_of_whitelist"),
    ):
        items = result.get(key, [])
        lines.append(f"[{label}] ({len(items)})")
        for it in items:
            owners = it.get("owners")
            suffix = f" (归属: {_tag_list(owners)})" if owners else ""
            lines.append(f"  {it['status']}  {it['path']}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def collect(
    task_id: str,
    base: str | None = None,
    executor: str | None = None,
    cwd: str | Path | None = None,
) -> dict:
    """一次核验的完整数据流：tracker → 方案白名单 → 归属推导 → git 改动 → 三分类事实。"""
    try:
        task_data = T.find_tracker(task_id)
    except (FileNotFoundError, ValueError) as e:
        raise DiffError(str(e))
    plan_path = find_plan_file(task_data)
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except OSError as e:
        raise DiffError(f"读方案文件失败: {plan_path}: {e}")
    path_to_owners, all_tags = parse_plan_whitelist(plan_text)
    target = resolve_target_executor(all_tags, executor)
    result = classify_paths(get_git_changes(base, cwd=cwd), path_to_owners, target)
    result.update(
        {
            "task_id": task_id,
            "plan_path": str(plan_path),
            "base": base,
            "executor": target,
        }
    )
    return result
