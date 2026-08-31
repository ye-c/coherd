"""coherd.cli — coherd task CLI 入口（new / list / show / status）。

滑坡护栏：CLI 只做文件 CRUD + 格式校验，永不做角色决策（无 dispatch/review）。
不绑特定 agent CLI（pi/omp/claude）——coherd typer 是数据管理工具，不是 agent 编排引擎。
"""

from __future__ import annotations

from datetime import datetime, timezone

import typer

from . import push as _push
from . import tracker as T
from .id_gen import next_id

app = typer.Typer(
    name="coherd", help="coherd 多 agent 协作集群：任务管理 CLI", no_args_is_help=True
)

task_app = typer.Typer(
    help="任务管理（tracker CRUD，不做角色决策）", no_args_is_help=True
)
app.add_typer(task_app, name="task")


def _fatal(msg: str) -> None:
    typer.echo(f"错误: {msg}", err=True)
    raise typer.Exit(code=1)


@app.command(name="feedback")
def feedback(
    peer_agent: str = typer.Argument(
        ..., help="对端 herdr agent 全名，如 w2p-reviewer"
    ),
    msg: str = typer.Argument(..., help="消息，须带 [role]: 前缀（契约 §2）"),
    ws: str = typer.Option(
        None, "--ws", help="自身 ws 短号（缺省取 HERDR_WORKSPACE_ID 小写）"
    ),
    role: str = typer.Option(
        None, "--role", help="自身 role（缺省从 COHERD_ROLE / agent 名派生）"
    ),
) -> None:
    """feedback 类型标记：CLI 注入 `[<role>|feedback]: <body>`，收方据标记需回执。

    命令名即语义（=标记名），无缺省值陷阱；送达失败不丢审计行。
    """
    try:
        r = _push.run(peer_agent, msg, ws=ws, role=role, msg_type="feedback")
    except ValueError as e:
        _fatal(str(e))
    else:
        if r["delivered"]:
            typer.echo(
                f"[feedback] 已送达 {r['from']} -> {r['to']} ({r['msg_id']}) 记于 {r['log_path']}"
            )
        else:
            typer.echo(
                f"[feedback] 送达失败 {r['from']} -> {r['to']} ({r['msg_id']}) "
                f"- 已写 events.log（type=feedback），请用 `coherd feedback` 重发",
                err=True,
            )


@app.command(name="notify")
def notify(
    peer_agent: str = typer.Argument(
        ..., help="对端 herdr agent 全名，如 w2p-reviewer"
    ),
    msg: str = typer.Argument(..., help="消息，须带 [role]: 前缀（契约 §2）"),
    ws: str = typer.Option(
        None, "--ws", help="自身 ws 短号（缺省取 HERDR_WORKSPACE_ID 小写）"
    ),
    role: str = typer.Option(
        None, "--role", help="自身 role（缺省从 COHERD_ROLE / agent 名派生）"
    ),
) -> None:
    """notify 类型标记：CLI 注入 `[<role>|notify]: <body>`，单向无需回执。

    命令名即语义；丢包自兜：delivered 假 → 非零退出提示转 feedback 重发。
    """
    try:
        r = _push.run(peer_agent, msg, ws=ws, role=role, msg_type="notify")
    except ValueError as e:
        _fatal(str(e))
    else:
        if r["delivered"]:
            typer.echo(
                f"[notify] 已送达 {r['from']} -> {r['to']} ({r['msg_id']}) 记于 {r['log_path']}"
            )
        else:
            typer.echo(
                f"[notify] 送达失败 {r['from']} -> {r['to']} ({r['msg_id']}) "
                f"- 已写 events.log（type=notify）无回执义务，改用 `coherd feedback` 重发",
                err=True,
            )
            raise typer.Exit(code=1)


@task_app.command()
def new(
    task_name: str = typer.Option(
        ..., "--task-name", "-t", help="任务名（只入 struct，不作文件名）"
    ),
    objective: str = typer.Option(
        ..., "--objective", "-o", help="目标：做什么 + 为什么"
    ),
    dod: str = typer.Option(..., "--dod", "-d", help="可验证的完成定义，逐条"),
    output: str = typer.Option(
        ..., "--output", "--output-path", help="产出物路径/结构"
    ),
    ws: str = typer.Option(
        ..., "--ws", help="herdr workspace 短号（作 id 前缀 + frontmatter ws 字段）"
    ),
    status: str = typer.Option("pending", "--status", help=f"初始状态（{T.STATUSES}）"),
    body: str = typer.Option("", "--body", help="可选 markdown 正文（缺省留空）"),
    parent_spec: str = typer.Option(
        "", "--parent-spec", help="上游 spec id（FK 追溯，见 CONTRACT §3；缺省空串）"
    ),
) -> None:
    """生成新 tracker 到 session 目录平铺 ~/.config/coherd/sessions/<session>/<id>.task.md（无 session 目录自动自建），打印路径。"""
    if status not in T.STATUSES:
        _fatal(f"status 非法: {status!r}（需 {T.STATUSES}）")
    now = datetime.now(timezone.utc)
    try:
        task_id = next_id(ws, now)
        data = {
            "id": task_id,
            "ws": ws,
            "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "task_name": task_name,
            "status": status,
            "parent_id": "",
            "parent_spec": parent_spec,
            "objective": objective,
            "dod": dod,
            "output_path": output,
        }
        p = T.write_new(data, body)
    except (ValueError, FileExistsError) as e:
        _fatal(str(e))
    else:
        typer.echo(f"已创建 tracker: {p}")


@task_app.command(name="list")
def list_cmd(
    ws: str = typer.Option(None, "--ws", help="按 workspace 过滤（缺省全 ws）"),
    status: str = typer.Option(None, "--status", help=f"按状态过滤（{T.STATUSES}）"),
) -> None:
    """列 tracker 摘要（id / status / 建日 / task_name）。"""
    if status is not None and status not in T.STATUSES:
        _fatal(f"status 非法: {status!r}（需 {T.STATUSES}）")
    if not T.SESSIONS_DIR.is_dir():
        typer.echo("无 tracker（sessions 目录不存在）")
        return
    rows: list[dict] = []
    for p in sorted(T.SESSIONS_DIR.glob("*/*.task.md")):
        try:
            data = T.load(p)
        except ValueError as e:
            # 容错:枚举列表遇 malformed/旧格式 tracker 跳过并告警,不拖垮整体
            typer.echo(f"警告: 跳过非法 tracker {p}: {e}", err=True)
            continue
        if ws is not None and data.get("ws") != ws:
            continue
        if status is not None and data.get("status") != status:
            continue
        rows.append(data)
    if not rows:
        typer.echo("无匹配 tracker")
        return
    # 按 id（ws-YYYYMMDD-序号）字典序 = 按日期 + 序号
    for d in sorted(rows, key=lambda x: x.get("id", "")):
        typer.echo(
            f"{d.get('id', '?'):<22} {d.get('status', '?'):<8} "
            f"{str(d.get('created_at', ''))[:10]}  {d.get('task_name', '')}"
        )


@task_app.command(name="show")
def show(
    task_id: str = typer.Argument(..., help="tracker id，如 w2c-20260826-001"),
) -> None:
    """打印完整 tracker（含 frontmatter 与正文 body）。"""
    try:
        data = T.find_tracker(task_id)
    except FileNotFoundError as e:
        _fatal(str(e))
    else:
        typer.echo(T.render_frontmatter(data, data.get("_body", "")))
        typer.echo(f"# 文件: {data['_path']}")


@task_app.command(name="status")
def status(
    task_id: str = typer.Argument(..., help="tracker id，如 w2c-20260826-001"),
    new_status: str = typer.Option(..., "--set", "-s", help=f"新状态（{T.STATUSES}）"),
) -> None:
    """更新 tracker 状态并落回 frontmatter（非法值拒绝，ID 不存在报错）。"""
    if new_status not in T.STATUSES:
        _fatal(f"status 非法: {new_status!r}（需 {T.STATUSES}）")
    try:
        T.set_status(task_id, new_status)
    except (FileNotFoundError, ValueError) as e:
        _fatal(str(e))
    typer.echo(f"{task_id} -> {new_status}")


if __name__ == "__main__":
    app()
