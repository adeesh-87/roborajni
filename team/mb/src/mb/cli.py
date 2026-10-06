"""mb — minimal message board for agents. Pull-based, email-like.

Storage: single SQLite file (WAL mode) at ~/.mb/board.db (override with MB_DB).
No daemon: every invocation opens the DB, does one operation, exits.
Jobs: a manager posts a job, engineers apply, the manager hires the first applicant.
Locks: `mb lock` runs lock.sh (next to this file) on the lock dir named in the job posting.
Stats: every agent action bumps a counter; `mb stats` reports them with job timelines.
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

DB_PATH = pathlib.Path(os.environ.get("MB_DB", pathlib.Path.home() / ".mb" / "board.db"))
DEFAULT_LOG = DB_PATH.parent / "mb.log"
LOBBY = "lobby"
LOCK_SH = pathlib.Path(__file__).resolve().parent / "lock.sh"
OWNER_CMDS = {"acquire", "wait", "release", "release-all", "alive"}
LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}

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
  closed_at  INTEGER
);
CREATE TABLE IF NOT EXISTS applications (
  seq        INTEGER PRIMARY KEY AUTOINCREMENT,
  job        TEXT NOT NULL,
  agent      TEXT NOT NULL UNIQUE,
  reply      TEXT NOT NULL,
  status     TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
  team      TEXT NOT NULL,
  role      TEXT NOT NULL,
  agent     TEXT NOT NULL UNIQUE,
  joined_at INTEGER NOT NULL,
  PRIMARY KEY (team, role)
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

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
    for col in ("hired_at", "closed_at"):
        if col not in cols:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {col} INTEGER")
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


def _job_of(con, agent):
    row = con.execute(
        "SELECT m.team FROM members m JOIN jobs j ON j.id = m.team WHERE m.agent=?", (agent,)
    ).fetchone()
    return row[0] if row else None


def _is_member(con, job, agent):
    return con.execute("SELECT 1 FROM members WHERE team=? AND agent=?", (job, agent)).fetchone() is not None


# ---- messages ----------------------------------------------------------------------------------

def cmd_pub(args):
    con = connect()
    if args.topic.startswith("job/") and not _is_member(con, args.topic[4:], args.sender):
        die(f"'{args.sender}' is not on job {args.topic[4:]}; job channels are private")
    seq = _post(con, args.topic, args.sender, args.body, args.reply_to)
    print(f"published seq={seq} topic={args.topic}")


def cmd_say(args):
    con = connect()
    job = _job_of(con, args.agent)
    if not job:
        die(f"'{args.agent}' is not on any job (post one, or apply and get hired, first)")
    seq = _post(con, f"job/{job}", args.agent, args.body, args.reply_to)
    print(f"published seq={seq} topic=job/{job}")


def cmd_sub(args):
    con = connect()
    if args.topic.startswith("job/") and not _is_member(con, args.topic[4:], args.agent):
        die(f"'{args.agent}' is not on job {args.topic[4:]}")
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
        return
    for seq, topic, sender, body, reply_to in rows:
        _log("debug", "msg.read", args.agent, seq=seq, topic=topic, sender=sender, type=_msg_type(body))
        reply = f" (reply_to={reply_to})" if reply_to else ""
        print(f"[{seq}] {topic} <{sender}>{reply}: {body}")
    if not args.peek:
        _set_cursor(con, args.agent, rows[-1][0])


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


# ---- jobs --------------------------------------------------------------------------------------

def _expire(con):
    for (jid,) in con.execute(
        "SELECT id FROM jobs WHERE status='open' AND created_at < ? - ttl_min * 60000", (now_ms(),)
    ).fetchall():
        con.execute("UPDATE jobs SET status='expired', closed_at=? WHERE id=?", (now_ms(), jid))
        con.execute("UPDATE applications SET status='rejected' WHERE job=? AND status='pending'", (jid,))
        _post(con, LOBBY, "mb", f"EXPIRED: job {jid} was never filled")
        _log("warn", "job.expired", job=jid)


def _oldest_open(con, label):
    row = con.execute(
        "SELECT id FROM jobs WHERE status='open' AND label IS ? ORDER BY created_at LIMIT 1", (label,)
    ).fetchone()
    return row[0] if row else None


def _resolve_job(con, args):
    if getattr(args, "job", None):
        if not con.execute("SELECT 1 FROM jobs WHERE id=?", (args.job,)).fetchone():
            die(f"no job {args.job}; list them with `mb job list`")
        return args.job
    if getattr(args, "agent", None):
        job = _job_of(con, args.agent)
        if not job:
            die(f"'{args.agent}' is not on any job")
        return job
    return _oldest_open(con, args.label)


def _lock_dir(con, job):
    posting = con.execute("SELECT posting FROM jobs WHERE id=?", (job,)).fetchone()[0]
    m = re.search(r"^\s*locks:\s*(\S.*?)\s*$", posting, re.MULTILINE)
    return os.path.expanduser(m.group(1)) if m else None


def _show(con, job):
    jid, label, title, posting, manager, engineer, status = con.execute(
        "SELECT id, label, title, posting, manager, engineer, status FROM jobs WHERE id=?", (job,)
    ).fetchone()
    pending = con.execute(
        "SELECT COUNT(*) FROM applications WHERE job=? AND status='pending'", (jid,)
    ).fetchone()[0]
    print(f"job:       {jid}" + (f" (label: {label})" if label else ""))
    print(f"title:     {title}")
    print(f"status:    {status}" + (f" ({pending} application(s) pending)" if status == "open" else ""))
    print(f"manager:   {manager}")
    print(f"engineer:  {engineer or '(not hired yet)'}")
    print(f"channel:   job/{jid}")
    print("posting:")
    print("\n".join("  " + line for line in posting.splitlines()))


def cmd_job_post(args):
    posting = args.posting.strip()
    if not posting:
        die("the posting is empty")
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    _expire(con)
    job = f"j-{secrets.token_hex(3)}"
    manager = f"manager@{job}"
    start = _max_seq(con)
    con.execute(
        "INSERT INTO jobs (id, label, title, posting, manager, status, start_seq, ttl_min, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
        (job, args.label, args.title, posting, manager, start, args.ttl, now_ms()),
    )
    con.execute("INSERT INTO members (team, role, agent, joined_at) VALUES (?, 'manager', ?, ?)", (job, manager, now_ms()))
    con.execute("INSERT OR IGNORE INTO subscriptions (agent, topic) VALUES (?, ?)", (manager, f"job/{job}"))
    _set_cursor(con, manager, start)
    _post(con, LOBBY, "mb", f"JOB {job}" + (f" [label {args.label}]" if args.label else "") + f": {args.title}")
    _count(con, manager, "job.post")
    _log("info", "job.posted", manager, job=job, label=args.label, title=args.title, ttl_min=args.ttl)
    _log("debug", "job.posting", manager, job=job, posting=posting)
    con.execute("COMMIT")
    print(f"YOUR AGENT ID: {manager}   <- use it as --agent / --sender in EVERY mb command")
    print(f"posted job {job}; engineers find it with `mb job show --next" + (f" --label {args.label}" if args.label else "") + "`")
    if not _lock_dir(con, job):
        print("note: the posting has no `locks: <absolute dir>` line, so `mb lock` will not work until you add it (mb job update).")
    print(f"\nNext: wait for applications (they arrive in your inbox as APPLY):  mb inbox --agent {manager} --wait 540")
    print(f"Then hire the first applicant:  mb job hire --agent {manager}")


def cmd_job_show(args):
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    _expire(con)
    con.execute("COMMIT")
    deadline = time.time() + args.wait
    job = _resolve_job(con, args)
    while not job and time.time() < deadline:
        time.sleep(3)
        job = _oldest_open(con, args.label)
    if args.agent:
        _count(con, args.agent, "job.show")
    if not job:
        print("(no open job)" + (f" with label {args.label}" if args.label else ""))
        return
    _show(con, job)
    if not args.agent:
        status = con.execute("SELECT status FROM jobs WHERE id=?", (job,)).fetchone()[0]
        if status == "open":
            print(f"\nTo take it, reply to the manager:  mb job apply {job} \"<your reply>\"")


def cmd_job_list(args):
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    _expire(con)
    con.execute("COMMIT")
    rows = con.execute(
        "SELECT id, label, status, title, engineer, created_at FROM jobs ORDER BY created_at DESC LIMIT ?", (args.n,)
    ).fetchall()
    if not rows:
        print("(no jobs)")
    for jid, label, status, title, engineer, created in rows:
        apps = con.execute("SELECT COUNT(*) FROM applications WHERE job=?", (jid,)).fetchone()[0]
        age = (now_ms() - created) // 60000
        print(f"{jid} [{status}]" + (f" label={label}" if label else "") + f" apps={apps} age={age}m"
              + (f" engineer={engineer}" if engineer else "") + f"  {title}")


def cmd_job_apply(args):
    reply = args.reply.strip()
    if not reply:
        die("the reply is empty: say what you understood, what you would add, and what you already know")
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    try:
        _expire(con)
        job = args.job or _oldest_open(con, args.label)
        if not job:
            die("there is no open job; wait for one with `mb job show --next --wait 90`")
        row = con.execute("SELECT status, manager FROM jobs WHERE id=?", (job,)).fetchone()
        if not row:
            die(f"no job {job}")
        status, manager = row
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
        _post(con, f"agent/{manager}", agent, f"APPLY: {agent} applies for job {job}\n{reply}")
        _count(con, agent, "job.apply")
        _log("info", "job.applied", agent, job=job)
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    print(f"YOUR AGENT ID: {agent}   <- use it as --agent / --sender in EVERY mb command")
    print(f"applied for job {job}. Wait for HIRED or REJECTED:  mb inbox --agent {agent} --wait 90")


def cmd_job_hire(args):
    con = connect()
    con.execute("BEGIN IMMEDIATE")
    try:
        job = _job_of(con, args.agent)
        row = con.execute("SELECT status, manager, start_seq FROM jobs WHERE id=?", (job,)).fetchone() if job else None
        if not row or row[1] != args.agent:
            die(f"'{args.agent}' is not the manager of a job")
        status, manager, start = row
        if status != "open":
            die(f"job {job} is {status}")
        if args.applicant:
            pick = con.execute(
                "SELECT agent FROM applications WHERE job=? AND agent=? AND status='pending'", (job, args.applicant)
            ).fetchone()
            if not pick:
                die(f"no pending application from {args.applicant}")
        else:
            pick = con.execute(
                "SELECT agent FROM applications WHERE job=? AND status='pending' ORDER BY seq LIMIT 1", (job,)
            ).fetchone()
            if not pick:
                die(f"no applications yet; wait for one:  mb inbox --agent {manager} --wait 540")
        engineer = pick[0]
        con.execute("UPDATE jobs SET status='filled', engineer=?, hired_at=? WHERE id=?", (engineer, now_ms(), job))
        con.execute("UPDATE applications SET status='hired' WHERE agent=?", (engineer,))
        con.execute("INSERT INTO members (team, role, agent, joined_at) VALUES (?, 'engineer', ?, ?)", (job, engineer, now_ms()))
        con.execute("INSERT OR IGNORE INTO subscriptions (agent, topic) VALUES (?, ?)", (engineer, f"job/{job}"))
        _set_cursor(con, engineer, start)
        rejected = [r[0] for r in con.execute(
            "SELECT agent FROM applications WHERE job=? AND status='pending'", (job,)
        ).fetchall()]
        for agent in rejected:
            con.execute("UPDATE applications SET status='rejected' WHERE agent=?", (agent,))
            _post(con, f"agent/{agent}", "mb", f"REJECTED: job {job} went to another engineer. Look for another job: mb job show --next")
            _log("warn", "job.rejected", agent, job=job)
        _post(con, f"agent/{engineer}", "mb",
              f"HIRED: you are the engineer on job {job}. Read the posting: mb job show --agent {engineer}. "
              f"Talk on the job channel: mb say \"<TYPE>: ...\" --agent {engineer}")
        _post(con, f"job/{job}", "mb", f"HIRED: {engineer} is the engineer on job {job}")
        _post(con, LOBBY, "mb", f"FILLED: job {job} by {engineer}")
        _count(con, args.agent, "job.hire")
        _log("info", "job.hired", args.agent, job=job, engineer=engineer, rejected=len(rejected))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    print(f"hired {engineer}" + (f"; rejected {len(rejected)} other applicant(s)" if rejected else ""))
    print(f"Talk on the job channel:  mb say \"<TYPE>: ...\" --agent {args.agent}")


def _manager_job(con, agent):
    job = _job_of(con, agent)
    if not job or con.execute("SELECT manager FROM jobs WHERE id=?", (job,)).fetchone()[0] != agent:
        die(f"'{agent}' is not the manager of a job")
    return job


def cmd_job_update(args):
    posting = args.posting.strip()
    con = connect()
    job = _manager_job(con, args.agent)
    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE jobs SET posting=? WHERE id=?", (posting, job))
    seq = _post(con, f"job/{job}", args.agent, f"POSTING UPDATED:\n{posting}")
    _count(con, args.agent, "job.update")
    _log("info", "job.updated", args.agent, job=job, seq=seq)
    con.execute("COMMIT")
    print(f"posting of job {job} updated (seq={seq})")
    if not _lock_dir(con, job):
        print("note: the posting has no `locks: <absolute dir>` line, so `mb lock` will not work.")


def cmd_job_close(args):
    con = connect()
    job = _manager_job(con, args.agent)
    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE jobs SET status='closed', closed_at=? WHERE id=?", (now_ms(), job))
    for (agent,) in con.execute("SELECT agent FROM applications WHERE job=? AND status='pending'", (job,)).fetchall():
        con.execute("UPDATE applications SET status='rejected' WHERE agent=?", (agent,))
        _post(con, f"agent/{agent}", "mb", f"REJECTED: job {job} was closed")
    _post(con, f"job/{job}", "mb", f"CLOSED: job {job}" + (f": {args.note}" if args.note else ""))
    _post(con, LOBBY, "mb", f"CLOSED: job {job}" + (f": {args.note}" if args.note else ""))
    _count(con, args.agent, "job.close")
    _log("info", "job.closed", args.agent, job=job, note=args.note)
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
    job = _job_of(con, args.agent)
    if not job:
        die(f"'{args.agent}' is not on any job")
    lock_dir = _lock_dir(con, job)
    if not lock_dir:
        die("the job posting has no `locks: <absolute dir>` line; the manager must add it with `mb job update`")
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

def _dur(ms):
    if ms is None:
        return "-"
    s = int(ms // 1000)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


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


def _job_stats(con, job):
    row = con.execute(
        "SELECT id, label, title, status, manager, engineer, created_at, hired_at, closed_at FROM jobs WHERE id=?",
        (job,),
    ).fetchone()
    if not row:
        die(f"no job {job}")
    jid, label, title, status, manager, engineer, posted, hired, closed = row
    msgs = con.execute(
        "SELECT seq, topic, sender, body, created_at FROM messages "
        "WHERE topic=? OR topic LIKE ? OR sender LIKE ? ORDER BY seq",
        (f"job/{jid}", f"agent/%@{jid}", f"%@{jid}"),
    ).fetchall()

    def first(kind):
        return next((t for _, topic, _, body, t in msgs if topic == f"job/{jid}" and _msg_type(body) == kind), None)

    agreed, first_sync, done, final = first("AGREED"), first("SYNC"), first("DONE"), first("FINAL")
    end = closed or now_ms()

    def span(a, b):
        return b - a if a is not None and b is not None else None

    by_type, by_sender, size = {}, {}, 0
    for _, _, sender, body, _ in msgs:
        kind = _msg_type(body)
        by_type[kind] = by_type.get(kind, 0) + 1
        by_sender[sender] = by_sender.get(sender, 0) + 1
        size += len(body.encode())
    applicants = [r[0] for r in con.execute("SELECT agent FROM applications WHERE job=? ORDER BY seq", (jid,))]
    agents = [manager] + [a for a in applicants if a != manager]
    return {
        "job": jid, "label": label, "title": title, "status": status,
        "manager": manager, "engineer": engineer, "applicants": len(applicants),
        "timeline": {
            "posted": posted, "hired": hired, "agreed": agreed, "first_sync": first_sync,
            "done": done, "final": final, "closed": closed,
        },
        "durations_ms": {
            "waiting_for_engineer": span(posted, hired),
            "negotiation": span(hired, agreed),
            "work": span(agreed, done),
            "evaluation": span(done, final or closed),
            "total": span(posted, end),
        },
        "messages": {"total": len(msgs), "bytes": size, "by_type": by_type, "by_sender": by_sender,
                     "syncs": by_type.get("SYNC", 0),
                     "interventions": by_type.get("STOP", 0) + by_type.get("REDIRECT", 0)},
        "agents": {a: _agent_summary(con, a) for a in agents},
    }


def _board_stats(con, n):
    jobs = {s: c for s, c in con.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}
    return {
        "db": str(DB_PATH),
        "messages": con.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "agents": con.execute("SELECT COUNT(DISTINCT agent) FROM counters WHERE agent != 'mb'").fetchone()[0],
        "jobs": jobs,
        "recent_jobs": [_job_stats(con, j) for (j,) in con.execute(
            "SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?", (n,))],
    }


def _print_agent(name, a, indent="  "):
    acq = a["lock_acquire"]
    print(f"{indent}{name}")
    print(f"{indent}  sent {a['messages_sent']} msgs ({a['bytes_sent']} B)"
          + (f"  by type: " + ", ".join(f"{k} {v}" for k, v in sorted(a['sent_by_type'].items())) if a['sent_by_type'] else ""))
    print(f"{indent}  inbox: {a['inbox_calls']} calls, {a['inbox_empty']} empty ({a['inbox_empty_pct']}%), "
          f"{_dur(a['inbox_wait_s'] * 1000)} waiting, {a['messages_read']} msgs read")
    if acq or a["lock_wait"]:
        print(f"{indent}  locks: acquire " + (", ".join(f"{k} {v}" for k, v in acq.items()) or "-")
              + f"; wait {sum(a['lock_wait'].values())} calls, {_dur(a['lock_wait_s'] * 1000)}")


def _print_job(j, detail=True):
    d = j["durations_ms"]
    print(f"{j['job']} [{j['status']}]" + (f" label={j['label']}" if j["label"] else "") + f"  {j['title']}")
    print(f"  total {_dur(d['total'])} | waiting for engineer {_dur(d['waiting_for_engineer'])} | "
          f"negotiation {_dur(d['negotiation'])} | work {_dur(d['work'])} | evaluation {_dur(d['evaluation'])}")
    m = j["messages"]
    print(f"  messages {m['total']} ({m['bytes']} B), SYNCs {m['syncs']}, STOP/REDIRECT {m['interventions']}, "
          f"applicants {j['applicants']}")
    if not detail:
        return
    print("  by type: " + ", ".join(f"{k} {v}" for k, v in sorted(m["by_type"].items(), key=lambda kv: -kv[1])))
    print("  agents:")
    for name, a in j["agents"].items():
        _print_agent(name, a, "    ")


def cmd_stats(args):
    con = connect()
    if args.agent:
        result = {"agent": args.agent, **_agent_summary(con, args.agent)}
    elif args.job:
        result = _job_stats(con, args.job)
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
    else:
        print(f"board {result['db']}: {result['messages']} messages, {result['agents']} agents, jobs "
              + (", ".join(f"{k} {v}" for k, v in result["jobs"].items()) or "none"))
        for j in result["recent_jobs"]:
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


# ---- entry point -------------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(prog="mb", description="Message board, jobs and locks for agents.")
    p.add_argument("--version", action="version", version=f"mb {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("pub", help="publish a message to a topic")
    pp.add_argument("topic")
    pp.add_argument("body")
    pp.add_argument("--sender", required=True)
    pp.add_argument("--reply-to", type=int, default=None, dest="reply_to")
    pp.set_defaults(func=cmd_pub)

    yp = sub.add_parser("say", help="post to your job's channel")
    yp.add_argument("body")
    yp.add_argument("--agent", required=True)
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

    job = sub.add_parser("job", help="job postings: manager posts, engineers apply, manager hires").add_subparsers(
        dest="job_cmd", required=True)

    jp = job.add_parser("post", help="manager: post a job (prints your manager id)")
    jp.add_argument("posting", help="the posting text; include a `locks: <absolute dir>` line")
    jp.add_argument("--title", required=True)
    jp.add_argument("--label", default=None)
    jp.add_argument("--ttl", type=int, default=240, metavar="MINUTES", help="expire if nobody is hired by then")
    jp.set_defaults(func=cmd_job_post)

    shp = job.add_parser("show", help="show a job: by id, your own (--agent), or the oldest open one")
    shp.add_argument("job", nargs="?")
    shp.add_argument("--agent", default=None)
    shp.add_argument("--next", action="store_true", help="the oldest open job (default when no id/agent)")
    shp.add_argument("--label", default=None)
    shp.add_argument("--wait", type=int, default=0, metavar="SECONDS", help="wait up to SECONDS for an open job")
    shp.set_defaults(func=cmd_job_show)

    lp = job.add_parser("list", help="recent jobs")
    lp.add_argument("-n", type=int, default=20)
    lp.set_defaults(func=cmd_job_list)

    app = job.add_parser("apply", help="engineer: reply to a job posting (prints your engineer id)")
    app.add_argument("job", nargs="?", help="job id (default: the oldest open job)")
    app.add_argument("reply")
    app.add_argument("--label", default=None)
    app.set_defaults(func=cmd_job_apply)

    hp = job.add_parser("hire", help="manager: hire the first pending applicant (or a named one)")
    hp.add_argument("applicant", nargs="?")
    hp.add_argument("--agent", required=True)
    hp.set_defaults(func=cmd_job_hire)

    up = job.add_parser("update", help="manager: replace the posting (e.g. with the agreed scope)")
    up.add_argument("posting")
    up.add_argument("--agent", required=True)
    up.set_defaults(func=cmd_job_update)

    cp = job.add_parser("close", help="manager: close the job")
    cp.add_argument("--agent", required=True)
    cp.add_argument("--note", default=None)
    cp.set_defaults(func=cmd_job_close)

    kp = sub.add_parser("lock", help="path locks for your job: mb lock --agent ID <command> [args...]")
    kp.add_argument("--agent", required=True)
    kp.add_argument("lock_args", nargs=argparse.REMAINDER)
    kp.set_defaults(func=cmd_lock)

    stp = sub.add_parser("stats", help="board, job or agent statistics (add --json for machine use)")
    group = stp.add_mutually_exclusive_group()
    group.add_argument("--job", default=None)
    group.add_argument("--agent", default=None)
    stp.add_argument("-n", type=int, default=10, help="recent jobs in the board summary")
    stp.add_argument("--json", action="store_true")
    stp.set_defaults(func=cmd_stats)

    lgp = sub.add_parser("log", help="file logging for every agent on this board")
    lgp.add_argument("action", choices=["on", "off", "status"])
    lgp.add_argument("--file", default=None, help=f"log file (default {DEFAULT_LOG})")
    lgp.add_argument("--level", choices=list(LEVELS), default="info")
    lgp.set_defaults(func=cmd_log)

    args = p.parse_args()
    args.func(args)
