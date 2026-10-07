"""mb — minimal message board for agents. Pull-based, email-like.

Storage: single SQLite file (WAL mode). Location: $MB_DB, else `board` in ~/.config/mb/config.json
(`mb config set board <path>`), else ~/.mb/board.db.
No daemon: every invocation opens the DB, does one operation, exits.
Projects and jobs: a manager posts a project, then one job per engineer (any kind, e.g. code or build);
engineers apply; the manager hires the first applicant of each job.
Channels: job/<id> (manager + that engineer), project/<id> (manager + every engineer), agent/<id> (direct).
Locks: `mb lock` runs lock.sh (next to this file) on the lock dir named in the project or job posting.
Stats: every agent action bumps a counter; `mb stats` reports them with timelines.
Logging: `mb log on|off` writes events to a file at error/warn/info/debug level.
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import secrets
import sqlite3
import subprocess
import sys
import time

from mb import __version__

CONFIG_FILE = pathlib.Path(os.environ.get("MB_CONFIG") or pathlib.Path.home() / ".config" / "mb" / "config.json")
DEFAULT_BOARD = pathlib.Path.home() / ".mb" / "board.db"


def _read_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"mb: error: cannot read config file {CONFIG_FILE}: {e}", file=sys.stderr)
        sys.exit(1)


def _resolve_board():
    if os.environ.get("MB_DB"):
        return pathlib.Path(os.environ["MB_DB"]).expanduser().absolute(), "MB_DB environment variable"
    board = _read_config().get("board")
    if board:
        return pathlib.Path(board), f"config file {CONFIG_FILE}"
    return DEFAULT_BOARD, "default"


DB_PATH, DB_SOURCE = _resolve_board()
DEFAULT_LOG = DB_PATH.parent / "mb.log"
LOBBY = "lobby"
LOCK_SH = pathlib.Path(__file__).resolve().parent / "lock.sh"
OWNER_CMDS = {"acquire", "wait", "release", "release-all", "alive"}
LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}
ACTIVE = ("open", "filled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  topic      TEXT NOT NULL,
  sender     TEXT NOT NULL,
  body       TEXT NOT NULL,
  reply_to   INTEGER REFERENCES messages(seq),
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
  agent TEXT NOT NULL,
  topic TEXT NOT NULL,
  PRIMARY KEY (agent, topic)
);
CREATE TABLE IF NOT EXISTS cursors (
  agent    TEXT PRIMARY KEY,
  last_seq INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS projects (
  id         TEXT PRIMARY KEY,
  label      TEXT,
  title      TEXT NOT NULL,
  posting    TEXT NOT NULL,
  manager    TEXT NOT NULL UNIQUE,
  status     TEXT NOT NULL,
  start_seq  INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  closed_at  INTEGER
);
CREATE TABLE IF NOT EXISTS jobs (
  id         TEXT PRIMARY KEY,
  label      TEXT,
  title      TEXT NOT NULL,
  posting    TEXT NOT NULL,
  manager    TEXT NOT NULL,
  engineer   TEXT,
  status     TEXT NOT NULL,
  start_seq  INTEGER NOT NULL,
  ttl_min    INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  hired_at   INTEGER,
  closed_at  INTEGER,
  project    TEXT,
  kind       TEXT,
  views      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS applications (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  job        TEXT NOT NULL,
  agent      TEXT NOT NULL UNIQUE,
  reply      TEXT NOT NULL,
  status     TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
  scope     TEXT NOT NULL,
  agent     TEXT NOT NULL,
  role      TEXT NOT NULL,
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (scope, agent)
);
CREATE TABLE IF NOT EXISTS counters (
  agent   TEXT NOT NULL,
  name    TEXT NOT NULL,
  count   INTEGER NOT NULL DEFAULT 0,
  total   REAL NOT NULL DEFAULT 0,
  last_at INTEGER,
  PRIMARY KEY (agent, name)
);
CREATE TABLE IF NOT EXISTS config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_log_cfg = None  # (path, min level) while logging is on


def now_ms():
    return int(time.time() * 1000)


# ---- logging -----------------------------------------------------------------------------------

def _load_log(con):
    global _log_cfg
    cfg = dict(con.execute("SELECT key, value FROM config WHERE key LIKE 'log.%'").fetchall())
    _log_cfg = (cfg["log.file"], LEVELS[cfg.get("log.level", "info")]) if cfg.get("log.enabled") == "1" else None


def _fmt(value):
    s = str(value)
    return json.dumps(s) if (not s or re.search(r'[\s"=]', s)) else s


def _log(level, event, agent=None, **fields):
    if not _log_cfg or LEVELS[level] < _log_cfg[1]:
        return
    stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
    parts = [stamp, level.upper().ljust(5), f"event={event}"]
    if agent:
        parts.append(f"agent={_fmt(agent)}")
    parts += [f"{k}={_fmt(v)}" for k, v in fields.items() if v is not None]
    try:
        with open(_log_cfg[0], "a", encoding="utf-8") as f:
            f.write(" ".join(parts) + "\n")
    except OSError as e:
        print(f"mb: warning: cannot write log file {_log_cfg[0]}: {e}", file=sys.stderr)


def die(msg):
    _log("error", "error", msg=msg, argv=" ".join(sys.argv[1:]))
    print(f"mb: error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---- storage -----------------------------------------------------------------------------------

def _open_board(path):
    """Open (creating if needed) the board at path; raises OSError / sqlite3.Error when that is impossible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    return con


def _on_windows_drive(path):
    try:
        wsl = "microsoft" in pathlib.Path("/proc/version").read_text().lower()
    except OSError:
        wsl = False
    return wsl and str(path).startswith("/mnt/")


def connect():
    try:
        con = _open_board(DB_PATH)
    except (OSError, sqlite3.Error) as e:
        die(f"cannot open the board {DB_PATH} (set by: {DB_SOURCE}): {e}\n"
            f"  SQLite must be able to create files in {DB_PATH.parent}. Usual causes:\n"
            f"  - a sandbox (e.g. Codex workspace-write) blocks writing there: give the session write access to\n"
            f"    that directory, or have the user pick a writable board with `mb config set board <path>`;\n"
            f"  - the path is on a Windows drive under WSL (/mnt/c/...), where SQLite is unreliable;\n"
            f"  - file or directory permissions.\n"
            f"  Agents: do not pick another board yourself; stop and report this message.")
    cols = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
    for col, typ in (("hired_at", "INTEGER"), ("closed_at", "INTEGER"), ("project", "TEXT"), ("kind", "TEXT"),
                     ("views", "INTEGER NOT NULL DEFAULT 0")):
        if col not in cols:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typ}")
    legacy = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='members'").fetchone()
    if legacy and not con.execute("SELECT 1 FROM memberships LIMIT 1").fetchone():
        con.execute("INSERT OR IGNORE INTO memberships (scope, agent, role, joined_at) "
                    "SELECT team, agent, role, joined_at FROM members")
    _load_log(con)
    return con


def _count(con, agent, name, total=0.0, n=1):
    con.execute(
        "INSERT INTO counters (agent, name, count, total, last_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(agent, name) DO UPDATE SET count=count+excluded.count, total=total+excluded.total, "
        "last_at=excluded.last_at",
        (agent, name, n, total, now_ms()),
    )


def _msg_type(body):
    m = re.match(r"\s*([A-Z][A-Z_]+)\b", body)
    return m.group(1) if m else "-"


def _post(con, topic, sender, body, reply_to=None):
    seq = con.execute(
        "INSERT INTO messages (topic, sender, body, reply_to, created_at) VALUES (?, ?, ?, ?, ?)",
        (topic, sender, body, reply_to, now_ms()),
    ).lastrowid
    kind, size = _msg_type(body), len(body.encode())
    _count(con, sender, "msg.sent", size)
    _count(con, sender, f"msg.sent.{kind}", size)
    _log("info", "msg.sent", sender, seq=seq, topic=topic, type=kind, bytes=size, reply_to=reply_to)
    _log("debug", "msg.body", sender, seq=seq, body=body)
    return seq


def _max_seq(con):
    return con.execute("SELECT COALESCE(MAX(seq), 0) FROM messages").fetchone()[0]


def _set_cursor(con, agent, seq):
    con.execute(
        "INSERT INTO cursors (agent, last_seq) VALUES (?, ?) "
        "ON CONFLICT(agent) DO UPDATE SET last_seq=excluded.last_seq",
        (agent, seq),
    )


def _join(con, scope, agent, role, topic):
    con.execute("INSERT OR IGNORE INTO memberships (scope, agent, role, joined_at) VALUES (?, ?, ?, ?)",
                (scope, agent, role, now_ms()))
    con.execute("INSERT OR IGNORE INTO subscriptions (agent, topic) VALUES (?, ?)", (agent, topic))


def _is_member(con, scope, agent):
    return con.execute("SELECT 1 FROM memberships WHERE scope=? AND agent=?", (scope, agent)).fetchone() is not None


def _engineer_job(con, agent):
    row = con.execute(
        "SELECT m.scope FROM memberships m JOIN jobs j ON j.id = m.scope WHERE m.agent=? AND m.role='engineer'",
        (agent,),
    ).fetchone()
    return row[0] if row else None


def _managed_project(con, agent):
    row = con.execute("SELECT id FROM projects WHERE manager=?", (agent,)).fetchone()
    return row[0] if row else None


def _managed_jobs(con, agent):
    return [r[0] for r in con.execute(
        "SELECT id FROM jobs WHERE manager=? AND status IN ('open', 'filled') ORDER BY created_at", (agent,))]


def _project_of(con, agent):
    project = _managed_project(con, agent)
    if project:
        return project
    job = _engineer_job(con, agent)
    return con.execute("SELECT project FROM jobs WHERE id=?", (job,)).fetchone()[0] if job else None


def _scope_of_topic(topic):
    for prefix in ("job/", "project/"):
        if topic.startswith(prefix):
            return topic[len(prefix):]
    return None


def _board_line():
    return (f"board: {DB_PATH}   (from {DB_SOURCE}; every agent on this task must use this same board, "
            f"never change it yourself)")


# ---- messages ----------------------------------------------------------------------------------

def cmd_pub(args):
    con = connect()
    scope = _scope_of_topic(args.topic)
    if scope and not _is_member(con, scope, args.sender):
        die(f"'{args.sender}' is not on {args.topic}; job and project channels are private")
    seq = _post(con, args.topic, args.sender, args.body, args.reply_to)
    print(f"published seq={seq} topic={args.topic}")


def _say_topic(con, agent, job, everyone):
    if everyone:
        project = _project_of(con, agent)
        if not project:
            die(f"'{agent}' is not on a project, so there is no channel for everyone")
        return f"project/{project}"
    if job:
        if not _is_member(con, job, agent):
            die(f"'{agent}' is not on job {job}")
        return f"job/{job}"
    own = _engineer_job(con, agent)
    if own:
        return f"job/{own}"
    managed = _managed_jobs(con, agent)
    if len(managed) == 1:
        return f"job/{managed[0]}"
    if managed:
        die(f"you manage {len(managed)} jobs ({', '.join(managed)}): add --job <id> for one engineer, "
            "or --all for everyone")
    if _managed_project(con, agent):
        die("your project has no jobs yet; post one with `mb job post`, or use --all")
    die(f"'{agent}' is not on any job (post a project, or apply and get hired, first)")


def cmd_say(args):
    con = connect()
    topic = _say_topic(con, args.agent, args.job, args.all)
    seq = _post(con, topic, args.agent, args.body, args.reply_to)
    print(f"published seq={seq} topic={topic}")


def cmd_sub(args):
    con = connect()
    scope = _scope_of_topic(args.topic)
    if scope and not _is_member(con, scope, args.agent):
        die(f"'{args.agent}' is not on {args.topic}")
    con.execute("INSERT OR IGNORE INTO subscriptions (agent, topic) VALUES (?, ?)", (args.agent, args.topic))
    _log("info", "subscribe", args.agent, topic=args.topic)
    print(f"{args.agent} subscribed to {args.topic}")


def _unread(con, agent):
    row = con.execute("SELECT last_seq FROM cursors WHERE agent=?", (agent,)).fetchone()
    last_seq = row[0] if row else 0
    topics = [f"agent/{agent}", "all"]
    topics += [r[0] for r in con.execute("SELECT topic FROM subscriptions WHERE agent=?", (agent,))]
    placeholders = ",".join("?" * len(topics))
    return con.execute(
        f"SELECT seq, topic, sender, body, reply_to FROM messages "
        f"WHERE topic IN ({placeholders}) AND seq > ? AND sender != ? ORDER BY seq",
        (*topics, last_seq, agent),
    ).fetchall()


def _job_note(con, agent, empty):
    """What the agent must know about its job(s) on every poll."""
    job = _engineer_job(con, agent)
    if job:
        status, label = con.execute("SELECT status, label FROM jobs WHERE id=?", (job,)).fetchone()
        if status in ("closed", "expired"):
            return (f"JOB CLOSED: your job {job} is {status}. Release your locks "
                    f"(mb lock --agent {agent} release-all), then find your next job: "
                    f"mb job show --next" + (f" --label {label}" if label else "") + " --wait 300")
        return f"(your job {job} is still active: when you have nothing else to do, poll again)" if empty else None
    if not empty:
        return None
    managed = _managed_jobs(con, agent)
    if managed:
        statuses = dict(con.execute(
            f"SELECT id, status FROM jobs WHERE id IN ({','.join('?' * len(managed))})", managed).fetchall())
        filled = [j for j in managed if statuses[j] == "filled"]
        waiting = [j for j in managed if statuses[j] == "open"]
        return (f"({len(filled)} job(s) in progress" + (f": {', '.join(filled)}" if filled else "")
                + f"; {len(waiting)} waiting for an engineer" + (f": {', '.join(waiting)}" if waiting else "")
                + ". Hire when APPLY arrives; close each job when its goals are met.)")
    project = _managed_project(con, agent)
    if project and con.execute("SELECT status FROM projects WHERE id=?", (project,)).fetchone()[0] != "closed":
        return (f"(no active jobs in project {project}. Post more jobs if work remains, "
                f"or keep polling for a TASK from the user)")
    return None


def cmd_inbox(args):
    con = connect()
    started = time.time()
    deadline = started + args.wait
    rows = _unread(con, args.agent)
    while not rows and time.time() < deadline:
        time.sleep(2)
        rows = _unread(con, args.agent)
    waited = time.time() - started
    _count(con, args.agent, "inbox", waited)
    if rows:
        _count(con, args.agent, "inbox.delivered", len(rows))
    else:
        _count(con, args.agent, "inbox.empty", waited)
    _log("debug", "inbox", args.agent, delivered=len(rows), waited_s=round(waited, 1), peek=args.peek or None)
    if not rows:
        print("(no new messages)")
    for seq, topic, sender, body, reply_to in rows:
        _log("debug", "msg.read", args.agent, seq=seq, topic=topic, sender=sender, type=_msg_type(body))
        reply = f" (reply_to={reply_to})" if reply_to else ""
        print(f"[{seq}] {topic} <{sender}>{reply}: {body}")
    if rows and not args.peek:
        _set_cursor(con, args.agent, rows[-1][0])
    note = _job_note(con, args.agent, empty=not rows)
    if note:
        print(note)


def cmd_ack(args):
    con = connect()
    _set_cursor(con, args.agent, args.seq)
    _log("debug", "ack", args.agent, seq=args.seq)
    print(f"{args.agent} cursor set to {args.seq}")


def cmd_tail(args):
    con = connect()
    where, params = ("WHERE topic=?", (args.topic,)) if args.topic else ("", ())
    rows = con.execute(
        f"SELECT seq, topic, sender, body FROM messages {where} ORDER BY seq DESC LIMIT ?", (*params, args.n)
    ).fetchall()
    for seq, topic, sender, body in reversed(rows):
        print(f"[{seq}] {topic} <{sender}>: {body}")


# ---- projects ----------------------------------------------------------------------------------

def _id_line(agent):
    return f"YOUR AGENT ID: {agent}   <- use it as --agent / --sender in EVERY mb command"


def cmd_project_post(args):
    posting = args.posting.strip()
    if not posting:
        die("the posting is empty")
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    project = f"p-{secrets.token_hex(3)}"
    manager = f"manager@{project}"
    start = _max_seq(con)
    con.execute(
        "INSERT INTO projects (id, label, title, posting, manager, status, start_seq, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
        (project, args.label, args.title, posting, manager, start, now_ms()),
    )
    _join(con, project, manager, "manager", f"project/{project}")
    _set_cursor(con, manager, start)
    _post(con, LOBBY, "mb", f"PROJECT {project}" + (f" [label {args.label}]" if args.label else "") + f": {args.title}")
    _count(con, manager, "project.post")
    _log("info", "project.posted", manager, project=project, label=args.label, title=args.title)
    _log("debug", "project.posting", manager, project=project, posting=posting)
    con.execute("COMMIT")
    print(_id_line(manager))
    print(_board_line())
    print(f"posted project {project}")
    if not _posting_lock_dir(posting):
        print("note: the posting has no `locks: <absolute dir>` line, so `mb lock` will not work until you add it.")
    print(f"\nNext: post one job per engineer, e.g.\n"
          f"  mb job post --agent {manager} --kind code  --title \"<scope>\" \"<what this engineer owns and does>\"\n"
          f"  mb job post --agent {manager} --kind build --title \"build and run\" \"<commands, what to report>\"")


def _resolve_project(con, args):
    if args.project:
        if not con.execute("SELECT 1 FROM projects WHERE id=?", (args.project,)).fetchone():
            die(f"no project {args.project}")
        return args.project
    if args.agent:
        project = _project_of(con, args.agent)
        if not project:
            die(f"'{args.agent}' is not on a project")
        return project
    die("give a project id or --agent")


def cmd_project_show(args):
    con = connect()
    project = _resolve_project(con, args)
    pid, label, title, posting, manager, status = con.execute(
        "SELECT id, label, title, posting, manager, status FROM projects WHERE id=?", (project,)).fetchone()
    print(f"project:   {pid}" + (f" (label: {label})" if label else ""))
    print(f"title:     {title}")
    print(f"status:    {status}")
    print(f"manager:   {manager}")
    print(f"channel:   project/{pid}   (everyone: mb say --all ...)")
    print("posting:")
    print("\n".join("  " + line for line in posting.splitlines()))
    print("jobs:")
    rows = con.execute("SELECT id, kind, status, engineer, title FROM jobs WHERE project=? ORDER BY created_at",
                       (pid,)).fetchall()
    if not rows:
        print("  (none yet)")
    for jid, kind, jstatus, engineer, jtitle in rows:
        print(f"  {jid} [{kind or '-'}] {jstatus:7} {engineer or '(not hired)':26} {jtitle}")


def cmd_project_close(args):
    con = connect()
    project = _managed_project(con, args.agent)
    if not project:
        die(f"'{args.agent}' does not manage a project")
    active = [j for (j,) in con.execute(
        "SELECT id FROM jobs WHERE project=? AND status IN ('open', 'filled')", (project,))]
    if active:
        die(f"{len(active)} job(s) still active ({', '.join(active)}). Close each one when its goals are met "
            f"(`mb job close --agent {args.agent} --job <id>`), so its engineer can stop; then close the project.")
    note = f": {args.note}" if args.note else ""
    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE projects SET status='closed', closed_at=? WHERE id=?", (now_ms(), project))
    _post(con, f"project/{project}", "mb", f"CLOSED: project {project}{note}")
    _post(con, LOBBY, "mb", f"CLOSED: project {project}{note}")
    _count(con, args.agent, "project.close")
    _log("info", "project.closed", args.agent, project=project, note=args.note)
    con.execute("COMMIT")
    print(f"project {project} closed")


# ---- jobs --------------------------------------------------------------------------------------

def _expire(con):
    for (jid,) in con.execute(
        "SELECT id FROM jobs WHERE status='open' AND ttl_min > 0 AND created_at < ? - ttl_min * 60000", (now_ms(),)
    ).fetchall():
        con.execute("UPDATE jobs SET status='expired', closed_at=? WHERE id=?", (now_ms(), jid))
        con.execute("UPDATE applications SET status='rejected' WHERE job=? AND status='pending'", (jid,))
        _post(con, LOBBY, "mb", f"EXPIRED: job {jid} was never filled")
        _log("warn", "job.expired", job=jid)


def _pick_open(con, label, kind, reserve=False):
    """The open job with the fewest views + pending applications, then the oldest, so engineers that look
    at the same moment are shown different jobs. With reserve, the view is recorded (call inside a transaction)."""
    row = con.execute(
        "SELECT j.id FROM jobs j WHERE j.status='open' AND j.label IS ? AND (? IS NULL OR j.kind=?) "
        "ORDER BY j.views + (SELECT COUNT(*) FROM applications a WHERE a.job=j.id AND a.status='pending'), "
        "j.created_at LIMIT 1",
        (label, kind, kind),
    ).fetchone()
    if row and reserve:
        con.execute("UPDATE jobs SET views = views + 1 WHERE id=?", (row[0],))
    return row[0] if row else None


def _posting_lock_dir(posting):
    m = re.search(r"^\s*locks:\s*(\S.*?)\s*$", posting or "", re.MULTILINE)
    return os.path.expanduser(m.group(1)) if m else None


def _lock_dir(con, agent):
    postings = []
    project = _project_of(con, agent)
    if project:
        postings.append(con.execute("SELECT posting FROM projects WHERE id=?", (project,)).fetchone()[0])
    jobs = [_engineer_job(con, agent)] if _engineer_job(con, agent) else _managed_jobs(con, agent)
    postings += [con.execute("SELECT posting FROM jobs WHERE id=?", (j,)).fetchone()[0] for j in jobs]
    return next((d for d in map(_posting_lock_dir, postings) if d), None)


def _show_job(con, job):
    jid, label, title, posting, manager, engineer, status, project, kind = con.execute(
        "SELECT id, label, title, posting, manager, engineer, status, project, kind FROM jobs WHERE id=?", (job,)
    ).fetchone()
    pending = con.execute(
        "SELECT COUNT(*) FROM applications WHERE job=? AND status='pending'", (jid,)
    ).fetchone()[0]
    print(f"job:       {jid}" + (f" (label: {label})" if label else ""))
    print(f"kind:      {kind or '-'}")
    print(f"title:     {title}")
    print(f"status:    {status}" + (f" ({pending} application(s) pending)" if status == "open" else ""))
    print(f"manager:   {manager}")
    print(f"engineer:  {engineer or '(not hired yet)'}")
    print(f"channel:   job/{jid}" + (f"   (everyone on the project: project/{project})" if project else ""))
    if project:
        print(f"project {project} posting (shared by every job):")
        ppost = con.execute("SELECT posting FROM projects WHERE id=?", (project,)).fetchone()[0]
        print("\n".join("  " + line for line in ppost.splitlines()))
    print("job posting:")
    print("\n".join("  " + line for line in posting.splitlines()))


def cmd_job_post(args):
    posting = args.posting.strip()
    if not posting:
        die("the posting is empty")
    con = connect()
    project = _managed_project(con, args.agent)
    if not project:
        die(f"'{args.agent}' does not manage a project; post one first with `mb project post`")
    con.execute("BEGIN IMMEDIATE")
    _expire(con)
    label = con.execute("SELECT label FROM projects WHERE id=?", (project,)).fetchone()[0]
    job = f"j-{secrets.token_hex(3)}"
    con.execute(
        "INSERT INTO jobs (id, label, title, posting, manager, status, start_seq, ttl_min, created_at, project, kind) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)",
        (job, label, args.title, posting, args.agent, _max_seq(con), args.ttl, now_ms(), project, args.kind),
    )
    _join(con, job, args.agent, "manager", f"job/{job}")
    _post(con, LOBBY, "mb", f"JOB {job}" + (f" [label {label}]" if label else "") + f" ({args.kind}) in {project}: {args.title}")
    _count(con, args.agent, "job.post")
    _log("info", "job.posted", args.agent, job=job, project=project, kind=args.kind, title=args.title, ttl_min=args.ttl)
    _log("debug", "job.posting", args.agent, job=job, posting=posting)
    con.execute("COMMIT")
    print(f"posted job {job} ({args.kind}) in project {project}")
    print(f"Wait for applications (they arrive as APPLY):  mb inbox --agent {args.agent} --wait 540")
    print(f"Hire the first applicant of every job that has one:  mb job hire --agent {args.agent}")


def cmd_job_show(args):
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    _expire(con)
    con.execute("COMMIT")
    if args.job:
        if not con.execute("SELECT 1 FROM jobs WHERE id=?", (args.job,)).fetchone():
            die(f"no job {args.job}; list them with `mb job list`")
        job = args.job
    elif args.agent:
        job = _engineer_job(con, args.agent)
        if not job:
            managed = _managed_jobs(con, args.agent)
            if len(managed) != 1:
                die("as a manager, use `mb project show --agent <you>`, or give a job id")
            job = managed[0]
        _count(con, args.agent, "job.show")
    else:
        deadline = time.time() + args.wait
        while True:
            con.execute("BEGIN IMMEDIATE")
            job = _pick_open(con, args.label, args.kind, reserve=True)
            con.execute("COMMIT")
            if job or time.time() >= deadline:
                break
            time.sleep(3)
        if not job:
            print("(no open job)" + (f" with label {args.label}" if args.label else "")
                  + (f" of kind {args.kind}" if args.kind else ""))
            return
    _show_job(con, job)
    status = con.execute("SELECT status FROM jobs WHERE id=?", (job,)).fetchone()[0]
    if not args.agent and status == "open":
        print(f"\nTo take it, reply to the manager:  mb job apply {job} \"<your reply>\"")


def cmd_job_list(args):
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    _expire(con)
    con.execute("COMMIT")
    where, params = ("WHERE project=?", (args.project,)) if args.project else ("", ())
    rows = con.execute(
        f"SELECT id, label, status, kind, project, title, engineer, created_at FROM jobs {where} "
        f"ORDER BY created_at DESC LIMIT ?", (*params, args.n)
    ).fetchall()
    if not rows:
        print("(no jobs)")
    for jid, label, status, kind, project, title, engineer, created in rows:
        apps = con.execute("SELECT COUNT(*) FROM applications WHERE job=?", (jid,)).fetchone()[0]
        age = (now_ms() - created) // 60000
        print(f"{jid} [{status}] {kind or '-'}" + (f" project={project}" if project else "")
              + (f" label={label}" if label else "") + f" apps={apps} age={age}m"
              + (f" engineer={engineer}" if engineer else "") + f"  {title}")


def cmd_job_apply(args):
    reply = args.reply.strip()
    if not reply:
        die("the reply is empty: say what you understood, what you would add, and what you already know")
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    try:
        _expire(con)
        job = args.job or _pick_open(con, args.label, args.kind)
        if not job:
            die("there is no open job; wait for one with `mb job show --next --wait 90`")
        row = con.execute("SELECT status, manager, kind FROM jobs WHERE id=?", (job,)).fetchone()
        if not row:
            die(f"no job {job}")
        status, manager, kind = row
        if status != "open":
            die(f"job {job} is {status}; look for another with `mb job show --next`")
        while True:
            agent = f"engineer-{secrets.token_hex(2)}@{job}"
            if not con.execute("SELECT 1 FROM applications WHERE agent=?", (agent,)).fetchone():
                break
        con.execute(
            "INSERT INTO applications (job, agent, reply, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (job, agent, reply, now_ms()),
        )
        _set_cursor(con, agent, _max_seq(con))
        _post(con, f"agent/{manager}", agent, f"APPLY: {agent} applies for job {job} ({kind or '-'})\n{reply}")
        _count(con, agent, "job.apply")
        _log("info", "job.applied", agent, job=job, kind=kind)
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    print(_id_line(agent))
    print(_board_line())
    print(f"applied for job {job} ({kind or '-'}). Wait for HIRED or REJECTED:  mb inbox --agent {agent} --wait 90")


def _hire(con, manager, job, engineer):
    project, start_seq = con.execute("SELECT project, start_seq FROM jobs WHERE id=?", (job,)).fetchone()
    con.execute("UPDATE jobs SET status='filled', engineer=?, hired_at=? WHERE id=?", (engineer, now_ms(), job))
    con.execute("UPDATE applications SET status='hired' WHERE agent=?", (engineer,))
    _join(con, job, engineer, "engineer", f"job/{job}")
    if project:
        _join(con, project, engineer, "engineer", f"project/{project}")
        start_seq = con.execute("SELECT start_seq FROM projects WHERE id=?", (project,)).fetchone()[0]
    _set_cursor(con, engineer, start_seq)
    rejected = [r[0] for r in con.execute(
        "SELECT agent FROM applications WHERE job=? AND status='pending'", (job,)).fetchall()]
    for agent in rejected:
        con.execute("UPDATE applications SET status='rejected' WHERE agent=?", (agent,))
        _post(con, f"agent/{agent}", "mb",
              f"REJECTED: job {job} went to another engineer. Apply for another open job: mb job show --next")
        _log("warn", "job.rejected", agent, job=job)
    _post(con, f"agent/{engineer}", "mb",
          f"HIRED: you are the engineer on job {job}. Read it: mb job show --agent {engineer}. "
          f"Talk to the manager: mb say \"<TYPE>: ...\" --agent {engineer}"
          + (f". Tell everyone on the project: mb say \"INFO: ...\" --all --agent {engineer}" if project else ""))
    _post(con, f"job/{job}", "mb", f"HIRED: {engineer} is the engineer on job {job}")
    _post(con, LOBBY, "mb", f"FILLED: job {job} by {engineer}")
    _count(con, manager, "job.hire")
    _log("info", "job.hired", manager, job=job, engineer=engineer, rejected=len(rejected))
    return rejected


def cmd_job_hire(args):
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    try:
        managed = [j for j in _managed_jobs(con, args.agent)
                   if con.execute("SELECT status FROM jobs WHERE id=?", (j,)).fetchone()[0] == "open"]
        if args.applicant:
            row = con.execute("SELECT job FROM applications WHERE agent=? AND status='pending'",
                              (args.applicant,)).fetchone()
            if not row or row[0] not in managed:
                die(f"no pending application from {args.applicant} for an open job of yours")
            picks = [(row[0], args.applicant)]
        else:
            jobs = managed
            if args.job:
                if args.job not in managed:
                    die(f"job {args.job} is not an open job of yours")
                jobs = [args.job]
            picks = []
            for job in jobs:
                first = con.execute(
                    "SELECT agent FROM applications WHERE job=? AND status='pending' ORDER BY seq LIMIT 1", (job,)
                ).fetchone()
                if first:
                    picks.append((job, first[0]))
            if not picks:
                if not managed:
                    die(f"'{args.agent}' has no open jobs")
                die(f"no applications yet; wait for one:  mb inbox --agent {args.agent} --wait 540")
        results = [(job, engineer, _hire(con, args.agent, job, engineer)) for job, engineer in picks]
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    for job, engineer, rejected in results:
        print(f"hired {engineer} for job {job}" + (f"; rejected {len(rejected)} other applicant(s)" if rejected else ""))
    still_open = [j for j in _managed_jobs(con, args.agent)
                  if con.execute("SELECT status FROM jobs WHERE id=?", (j,)).fetchone()[0] == "open"]
    if still_open:
        print(f"still open: {', '.join(still_open)}")


def _resolve_managed_job(con, agent, job):
    managed = _managed_jobs(con, agent)
    if job:
        if con.execute("SELECT manager FROM jobs WHERE id=?", (job,)).fetchone() != (agent,):
            die(f"'{agent}' does not manage job {job}")
        return job
    if len(managed) == 1:
        return managed[0]
    if not managed:
        die(f"'{agent}' manages no open or filled job")
    die(f"you manage {len(managed)} jobs ({', '.join(managed)}): add --job <id>")


def cmd_job_update(args):
    posting = args.posting.strip()
    con = connect()
    job = _resolve_managed_job(con, args.agent, args.job)
    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE jobs SET posting=? WHERE id=?", (posting, job))
    seq = _post(con, f"job/{job}", args.agent, f"POSTING UPDATED:\n{posting}")
    _count(con, args.agent, "job.update")
    _log("info", "job.updated", args.agent, job=job, seq=seq)
    con.execute("COMMIT")
    print(f"posting of job {job} updated (seq={seq})")


def _close_job(con, manager, job, note):
    con.execute("UPDATE jobs SET status='closed', closed_at=? WHERE id=?", (now_ms(), job))
    for (agent,) in con.execute("SELECT agent FROM applications WHERE job=? AND status='pending'", (job,)).fetchall():
        con.execute("UPDATE applications SET status='rejected' WHERE agent=?", (agent,))
        _post(con, f"agent/{agent}", "mb", f"REJECTED: job {job} was closed")
    _post(con, f"job/{job}", "mb", f"CLOSED: job {job}" + (f": {note}" if note else ""))
    _post(con, LOBBY, "mb", f"CLOSED: job {job}" + (f": {note}" if note else ""))
    _count(con, manager, "job.close")
    _log("info", "job.closed", manager, job=job, note=note)


def cmd_job_close(args):
    con = connect()
    job = _resolve_managed_job(con, args.agent, args.job)
    con.execute("BEGIN IMMEDIATE")
    _close_job(con, args.agent, job, args.note)
    con.execute("COMMIT")
    print(f"job {job} closed")


# ---- locks -------------------------------------------------------------------------------------

LOCK_OUTCOMES = {
    "acquire": {0: "ok", 1: "busy", 3: "stale"},
    "wait": {0: "ok", 1: "busy", 3: "stale"},
    "check": {0: "free", 1: "locked"},
}


def cmd_lock(args):
    if not args.lock_args:
        die("usage: mb lock --agent ID <acquire|wait|release|release-all|alive|check|list|status|watch|reap|break> [args...]")
    con = connect()
    if not _project_of(con, args.agent) and not _engineer_job(con, args.agent) and not _managed_jobs(con, args.agent):
        die(f"'{args.agent}' is not on any project or job")
    lock_dir = _lock_dir(con, args.agent)
    if not lock_dir:
        die("no `locks: <absolute dir>` line in the project or job posting; the manager must add one")
    if not LOCK_SH.is_file():
        die(f"lock.sh not found at {LOCK_SH}")
    cmd, *rest = args.lock_args
    argv = ["bash", str(LOCK_SH), lock_dir, cmd] + ([args.agent] if cmd in OWNER_CMDS else []) + rest
    started = time.time()
    rc = subprocess.run(argv).returncode
    secs = time.time() - started
    outcome = LOCK_OUTCOMES.get(cmd, {}).get(rc, "ok" if rc == 0 else f"rc{rc}")
    _count(con, args.agent, f"lock.{cmd}", secs)
    _count(con, args.agent, f"lock.{cmd}.{outcome}", secs)
    if cmd in ("acquire", "wait") and rc in (1, 3):
        level = "warn"
    elif cmd in OWNER_CMDS or cmd in ("reap", "break"):
        level = "info"
    else:
        level = "debug"
    _log(level, f"lock.{cmd}", args.agent, outcome=outcome, rc=rc, secs=round(secs, 1), args=" ".join(rest) or None)
    sys.exit(rc)


# ---- stats -------------------------------------------------------------------------------------

ROUTING = ("READY", "BUILD", "REPORT", "FIX")


def _dur(ms):
    if ms is None:
        return "-"
    s = int(ms // 1000)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _span(a, b):
    return b - a if a is not None and b is not None else None


def _counters(con, agent):
    return {name: {"count": count, "total": round(total, 1)} for name, count, total in con.execute(
        "SELECT name, count, total FROM counters WHERE agent=? ORDER BY name", (agent,))}


def _agent_summary(con, agent):
    c = _counters(con, agent)
    get = lambda name, key="count": c.get(name, {}).get(key, 0)  # noqa: E731
    calls = get("inbox")
    return {
        "messages_sent": get("msg.sent"),
        "bytes_sent": int(get("msg.sent", "total")),
        "sent_by_type": {k[len("msg.sent."):]: v["count"] for k, v in c.items() if k.startswith("msg.sent.")},
        "inbox_calls": calls,
        "inbox_empty": get("inbox.empty"),
        "inbox_empty_pct": round(100 * get("inbox.empty") / calls) if calls else 0,
        "inbox_wait_s": get("inbox", "total"),
        "messages_read": int(get("inbox.delivered", "total")),
        "lock_acquire": {k.split(".")[-1]: v["count"] for k, v in c.items() if k.startswith("lock.acquire.")},
        "lock_wait": {k.split(".")[-1]: v["count"] for k, v in c.items() if k.startswith("lock.wait.")},
        "lock_wait_s": get("lock.wait", "total"),
        "counters": c,
    }


def _tally(msgs):
    by_type, by_sender, size = {}, {}, 0
    for _, _, sender, body, _ in msgs:
        kind = _msg_type(body)
        by_type[kind] = by_type.get(kind, 0) + 1
        by_sender[sender] = by_sender.get(sender, 0) + 1
        size += len(body.encode())
    return {"total": len(msgs), "bytes": size, "by_type": by_type, "by_sender": by_sender}


def _job_stats(con, job, with_agents=True):
    row = con.execute(
        "SELECT id, label, title, status, manager, engineer, created_at, hired_at, closed_at, project, kind "
        "FROM jobs WHERE id=?", (job,)).fetchone()
    if not row:
        die(f"no job {job}")
    jid, label, title, status, manager, engineer, posted, hired, closed, project, kind = row
    msgs = con.execute(
        "SELECT seq, topic, sender, body, created_at FROM messages "
        "WHERE topic=? OR topic LIKE ? OR sender LIKE ? ORDER BY seq",
        (f"job/{jid}", f"agent/%@{jid}", f"%@{jid}"),
    ).fetchall()

    def first(kind_):
        return next((t for _, topic, _, body, t in msgs if topic == f"job/{jid}" and _msg_type(body) == kind_), None)

    agreed, first_sync, done, final = first("AGREED"), first("SYNC"), first("DONE"), first("FINAL")
    tally = _tally(msgs)
    tally["syncs"] = tally["by_type"].get("SYNC", 0)
    tally["interventions"] = tally["by_type"].get("STOP", 0) + tally["by_type"].get("REDIRECT", 0)
    applicants = [r[0] for r in con.execute("SELECT agent FROM applications WHERE job=? ORDER BY seq", (jid,))]
    result = {
        "job": jid, "project": project, "kind": kind, "label": label, "title": title, "status": status,
        "manager": manager, "engineer": engineer, "applicants": len(applicants),
        "timeline": {"posted": posted, "hired": hired, "agreed": agreed, "first_sync": first_sync,
                     "done": done, "final": final, "closed": closed},
        "durations_ms": {
            "waiting_for_engineer": _span(posted, hired),
            "negotiation": _span(hired, agreed),
            "work": _span(agreed, done),
            "evaluation": _span(done, final or closed),
            "total": _span(posted, closed or now_ms()),
        },
        "messages": tally,
    }
    if with_agents:
        result["agents"] = {a: _agent_summary(con, a) for a in [manager] + [a for a in applicants if a != manager]}
    return result


def _project_stats(con, project):
    row = con.execute("SELECT id, label, title, status, manager, created_at, closed_at FROM projects WHERE id=?",
                      (project,)).fetchone()
    if not row:
        die(f"no project {project}")
    pid, label, title, status, manager, created, closed = row
    jobs = [j for (j,) in con.execute("SELECT id FROM jobs WHERE project=? ORDER BY created_at", (pid,))]
    topics = [f"project/{pid}"] + [f"job/{j}" for j in jobs]
    placeholders = ",".join("?" * len(topics))
    msgs = con.execute(f"SELECT seq, topic, sender, body, created_at FROM messages WHERE topic IN ({placeholders}) "
                       f"ORDER BY seq", topics).fetchall()
    tally = _tally(msgs)
    hired = [h for (h,) in con.execute("SELECT hired_at FROM jobs WHERE project=? AND hired_at IS NOT NULL", (pid,))]
    first_build = next((t for _, _, _, body, t in msgs if _msg_type(body) == "BUILD"), None)
    final = next((t for _, _, _, body, t in msgs if _msg_type(body) == "FINAL"), None)
    engineers = [e for (e,) in con.execute(
        "SELECT agent FROM memberships WHERE scope=? AND role='engineer' ORDER BY joined_at", (pid,))]
    return {
        "project": pid, "label": label, "title": title, "status": status, "manager": manager,
        "jobs": [_job_stats(con, j, with_agents=False) for j in jobs],
        "durations_ms": {
            "staffing": _span(created, max(hired)) if len(hired) == len(jobs) and jobs else None,
            "to_first_build": _span(created, first_build),
            "to_final": _span(created, final),
            "total": _span(created, closed or now_ms()),
        },
        "messages": tally,
        "routing": {k: tally["by_type"].get(k, 0) for k in ROUTING},
        "agents": {a: _agent_summary(con, a) for a in [manager] + engineers},
    }


def _board_stats(con, n):
    return {
        "db": str(DB_PATH),
        "messages": con.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "agents": con.execute("SELECT COUNT(DISTINCT agent) FROM counters WHERE agent != 'mb'").fetchone()[0],
        "projects": {s: c for s, c in con.execute("SELECT status, COUNT(*) FROM projects GROUP BY status")},
        "jobs": {s: c for s, c in con.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")},
        "recent_projects": [_project_stats(con, p) for (p,) in con.execute(
            "SELECT id FROM projects ORDER BY created_at DESC LIMIT ?", (n,))],
        "recent_jobs_without_project": [_job_stats(con, j, with_agents=False) for (j,) in con.execute(
            "SELECT id FROM jobs WHERE project IS NULL ORDER BY created_at DESC LIMIT ?", (n,))],
    }


def _print_agent(name, a, indent="  "):
    acq = a["lock_acquire"]
    print(f"{indent}{name}")
    print(f"{indent}  sent {a['messages_sent']} msgs ({a['bytes_sent']} B)"
          + ("  by type: " + ", ".join(f"{k} {v}" for k, v in sorted(a['sent_by_type'].items())) if a['sent_by_type'] else ""))
    print(f"{indent}  inbox: {a['inbox_calls']} calls, {a['inbox_empty']} empty ({a['inbox_empty_pct']}%), "
          f"{_dur(a['inbox_wait_s'] * 1000)} waiting, {a['messages_read']} msgs read")
    if acq or a["lock_wait"]:
        print(f"{indent}  locks: acquire " + (", ".join(f"{k} {v}" for k, v in acq.items()) or "-")
              + f"; wait {sum(a['lock_wait'].values())} calls, {_dur(a['lock_wait_s'] * 1000)}")


def _print_job(j, indent="", detail=True):
    d, m = j["durations_ms"], j["messages"]
    print(f"{indent}{j['job']} [{j['status']}] {j['kind'] or '-'}" + (f" label={j['label']}" if j["label"] else "")
          + f" engineer={j['engineer'] or '-'}  {j['title']}")
    print(f"{indent}  total {_dur(d['total'])} | waiting for engineer {_dur(d['waiting_for_engineer'])} | "
          f"negotiation {_dur(d['negotiation'])} | work {_dur(d['work'])} | evaluation {_dur(d['evaluation'])}")
    print(f"{indent}  messages {m['total']} ({m['bytes']} B), SYNCs {m['syncs']}, STOP/REDIRECT {m['interventions']}, "
          f"applicants {j['applicants']}")
    if detail:
        print(f"{indent}  by type: " + ", ".join(f"{k} {v}" for k, v in sorted(m["by_type"].items(), key=lambda kv: -kv[1])))
        if "agents" in j:
            print(f"{indent}  agents:")
            for name, a in j["agents"].items():
                _print_agent(name, a, indent + "    ")


def _print_project(p, detail=True):
    d, m, r = p["durations_ms"], p["messages"], p["routing"]
    print(f"{p['project']} [{p['status']}]" + (f" label={p['label']}" if p["label"] else "") + f"  {p['title']}")
    print(f"  total {_dur(d['total'])} | staffing {_dur(d['staffing'])} | to first build {_dur(d['to_first_build'])} "
          f"| to final {_dur(d['to_final'])}")
    print(f"  messages {m['total']} ({m['bytes']} B) | " + " ".join(f"{k} {v}" for k, v in r.items())
          + f" | jobs {len(p['jobs'])}")
    if not detail:
        return
    print("  by type: " + ", ".join(f"{k} {v}" for k, v in sorted(m["by_type"].items(), key=lambda kv: -kv[1])))
    print("  jobs:")
    for j in p["jobs"]:
        _print_job(j, "    ", detail=False)
    print("  agents:")
    for name, a in p["agents"].items():
        _print_agent(name, a, "    ")


def cmd_stats(args):
    con = connect()
    if args.agent:
        result = {"agent": args.agent, **_agent_summary(con, args.agent)}
    elif args.job:
        result = _job_stats(con, args.job)
    elif args.project:
        result = _project_stats(con, args.project)
    else:
        result = _board_stats(con, args.n)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    if args.agent:
        _print_agent(args.agent, result, "")
        for name, v in result["counters"].items():
            print(f"  {name:28} count={v['count']:<6} total={v['total']}")
    elif args.job:
        _print_job(result)
    elif args.project:
        _print_project(result)
    else:
        fmt = lambda d: ", ".join(f"{k} {v}" for k, v in d.items()) or "none"  # noqa: E731
        print(f"board {result['db']}: {result['messages']} messages, {result['agents']} agents, "
              f"projects {fmt(result['projects'])}, jobs {fmt(result['jobs'])}")
        for p in result["recent_projects"]:
            _print_project(p, detail=False)
        for j in result["recent_jobs_without_project"]:
            _print_job(j, detail=False)


# ---- log config --------------------------------------------------------------------------------

def _set_config(con, **values):
    for k, v in values.items():
        con.execute("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, v))


def cmd_log(args):
    con = connect()
    if args.action == "on":
        path = pathlib.Path(args.file or DEFAULT_LOG).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        _set_config(con, **{"log.enabled": "1", "log.file": str(path), "log.level": args.level})
        _load_log(con)
        _log("info", "log.enabled", log_level=args.level, file=str(path))
    elif args.action == "off":
        _log("info", "log.disabled")
        _set_config(con, **{"log.enabled": "0"})
        _load_log(con)
    cfg = dict(con.execute("SELECT key, value FROM config WHERE key LIKE 'log.%'").fetchall())
    if cfg.get("log.enabled") == "1":
        size = pathlib.Path(cfg["log.file"]).stat().st_size if pathlib.Path(cfg["log.file"]).exists() else 0
        print(f"logging: on, level {cfg['log.level']}, file {cfg['log.file']} ({size} B)")
    else:
        print("logging: off" + (f" (last file {cfg['log.file']})" if "log.file" in cfg else ""))


# ---- board location ----------------------------------------------------------------------------

def _write_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def cmd_config(args):
    cfg = _read_config()
    if args.action in ("set", "unset") and args.key != "board":
        die("the only setting is `board`: mb config set board <path> / mb config unset board")
    if args.action == "set":
        if not args.value:
            die("usage: mb config set board <path to a .db file, or a directory>")
        path = pathlib.Path(args.value).expanduser().absolute()
        if path.is_dir() or args.value.endswith("/"):
            path = path / "board.db"
        try:
            _open_board(path).close()
        except (OSError, sqlite3.Error) as e:
            die(f"cannot create or open a board at {path}: {e}")
        cfg["board"] = str(path)
        _write_config(cfg)
        print(f"board set to {path}  (saved in {CONFIG_FILE})")
        if _on_windows_drive(path):
            print("warning: this is a Windows drive under WSL; SQLite's locking is unreliable there. "
                  "Prefer a Linux path such as ~/...")
    elif args.action == "unset":
        cfg.pop("board", None)
        _write_config(cfg)
        print(f"board setting removed from {CONFIG_FILE}")
    board, source = _resolve_board()
    print(f"board in effect: {board}")
    print(f"  set by:        {source}")
    print(f"  config file:   {CONFIG_FILE}" + ("" if CONFIG_FILE.exists() else " (does not exist)"))
    if os.environ.get("MB_DB") and args.action != "show":
        print("  note: MB_DB is set in this shell and overrides the config file here")
    folder = board.parent
    print(f"  folder:        {folder} (" + ("writable" if os.access(folder, os.W_OK) else
                                            "exists, NOT writable" if folder.exists() else "missing") + ")")


# ---- entry point -------------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(prog="mb", description="Message board, projects, jobs and locks for agents.")
    p.add_argument("--version", action="version", version=f"mb {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("pub", help="publish a message to a topic")
    pp.add_argument("topic")
    pp.add_argument("body")
    pp.add_argument("--sender", required=True)
    pp.add_argument("--reply-to", type=int, default=None, dest="reply_to")
    pp.set_defaults(func=cmd_pub)

    yp = sub.add_parser("say", help="post to your job channel, a given job (--job) or the whole project (--all)")
    yp.add_argument("body")
    yp.add_argument("--agent", required=True)
    target = yp.add_mutually_exclusive_group()
    target.add_argument("--job", default=None, help="manager: the job (engineer) to talk to")
    target.add_argument("--all", action="store_true", help="everyone on the project")
    yp.add_argument("--reply-to", type=int, default=None, dest="reply_to")
    yp.set_defaults(func=cmd_say)

    sp = sub.add_parser("sub", help="subscribe an agent to a topic")
    sp.add_argument("topic")
    sp.add_argument("--agent", required=True)
    sp.set_defaults(func=cmd_sub)

    ip = sub.add_parser("inbox", help="read (and consume) unread messages for an agent")
    ip.add_argument("--agent", required=True)
    ip.add_argument("--peek", action="store_true", help="don't advance the read cursor")
    ip.add_argument("--wait", type=int, default=0, metavar="SECONDS", help="block up to SECONDS for new mail")
    ip.set_defaults(func=cmd_inbox)

    ap = sub.add_parser("ack", help="manually set an agent's read cursor")
    ap.add_argument("agent")
    ap.add_argument("seq", type=int)
    ap.set_defaults(func=cmd_ack)

    tp = sub.add_parser("tail", help="recent messages regardless of cursor")
    tp.add_argument("--topic", default=None)
    tp.add_argument("-n", type=int, default=20)
    tp.set_defaults(func=cmd_tail)

    project = sub.add_parser("project", help="manager: the shared context all jobs belong to").add_subparsers(
        dest="project_cmd", required=True)
    prp = project.add_parser("post", help="manager: post a project (prints your manager id)")
    prp.add_argument("posting", help="shared context for every job; include a `locks: <absolute dir>` line")
    prp.add_argument("--title", required=True)
    prp.add_argument("--label", default=None)
    prp.set_defaults(func=cmd_project_post)
    prs = project.add_parser("show", help="a project's posting and jobs")
    prs.add_argument("project", nargs="?")
    prs.add_argument("--agent", default=None)
    prs.set_defaults(func=cmd_project_show)
    prc = project.add_parser("close", help="manager: close the project, once every job is closed")
    prc.add_argument("--agent", required=True)
    prc.add_argument("--note", default=None)
    prc.set_defaults(func=cmd_project_close)

    job = sub.add_parser("job", help="job postings: manager posts, engineers apply, manager hires").add_subparsers(
        dest="job_cmd", required=True)

    jp = job.add_parser("post", help="manager: post one job (one engineer) in your project")
    jp.add_argument("posting", help="what this engineer owns and does")
    jp.add_argument("--agent", required=True)
    jp.add_argument("--title", required=True)
    jp.add_argument("--kind", default="code", help="e.g. code or build (default code)")
    jp.add_argument("--ttl", type=int, default=0, metavar="MINUTES",
                    help="expire if nobody is hired by then (default 0: never, so a backlog can wait)")
    jp.set_defaults(func=cmd_job_post)

    shp = job.add_parser("show", help="show a job: by id, your own (--agent), or the next free one")
    shp.add_argument("job", nargs="?")
    shp.add_argument("--agent", default=None)
    shp.add_argument("--next", action="store_true", help="the next free open job (default when no id/agent)")
    shp.add_argument("--label", default=None)
    shp.add_argument("--kind", default=None)
    shp.add_argument("--wait", type=int, default=0, metavar="SECONDS", help="wait up to SECONDS for an open job")
    shp.set_defaults(func=cmd_job_show)

    lp = job.add_parser("list", help="recent jobs")
    lp.add_argument("--project", default=None)
    lp.add_argument("-n", type=int, default=20)
    lp.set_defaults(func=cmd_job_list)

    app = job.add_parser("apply", help="engineer: reply to a job posting (prints your engineer id)")
    app.add_argument("job", nargs="?", help="job id (default: the next free open job)")
    app.add_argument("reply")
    app.add_argument("--label", default=None)
    app.add_argument("--kind", default=None)
    app.set_defaults(func=cmd_job_apply)

    hp = job.add_parser("hire", help="manager: hire the first applicant of every open job (or --job / an applicant)")
    hp.add_argument("applicant", nargs="?")
    hp.add_argument("--agent", required=True)
    hp.add_argument("--job", default=None)
    hp.set_defaults(func=cmd_job_hire)

    up = job.add_parser("update", help="manager: replace a job's posting (e.g. with the agreed scope)")
    up.add_argument("posting")
    up.add_argument("--agent", required=True)
    up.add_argument("--job", default=None)
    up.set_defaults(func=cmd_job_update)

    cp = job.add_parser("close", help="manager: close one job when its goals are met (its engineer then stops)")
    cp.add_argument("--agent", required=True)
    cp.add_argument("--job", default=None)
    cp.add_argument("--note", default=None)
    cp.set_defaults(func=cmd_job_close)

    kp = sub.add_parser("lock", help="path locks for your project: mb lock --agent ID <command> [args...]")
    kp.add_argument("--agent", required=True)
    kp.add_argument("lock_args", nargs=argparse.REMAINDER)
    kp.set_defaults(func=cmd_lock)

    stp = sub.add_parser("stats", help="board, project, job or agent statistics (add --json for machine use)")
    group = stp.add_mutually_exclusive_group()
    group.add_argument("--project", default=None)
    group.add_argument("--job", default=None)
    group.add_argument("--agent", default=None)
    stp.add_argument("-n", type=int, default=10, help="recent projects/jobs in the board summary")
    stp.add_argument("--json", action="store_true")
    stp.set_defaults(func=cmd_stats)

    cfp = sub.add_parser("config", help="where the board lives: mb config show | set board <path> | unset board")
    cfp.add_argument("action", choices=["show", "set", "unset"])
    cfp.add_argument("key", nargs="?")
    cfp.add_argument("value", nargs="?")
    cfp.set_defaults(func=cmd_config)

    lgp = sub.add_parser("log", help="file logging for every agent on this board")
    lgp.add_argument("action", choices=["on", "off", "status"])
    lgp.add_argument("--file", default=None, help=f"log file (default {DEFAULT_LOG})")
    lgp.add_argument("--level", choices=list(LEVELS), default="info")
    lgp.set_defaults(func=cmd_log)

    args = p.parse_args()
    args.func(args)
