"""crew — launch and drive N agent sessions (Codex, Claude Code, ...) in tmux.

Every agent runs in its own tmux window, so you can list them, read their screen, enter one and type,
or send it a line. A run is one tmux session (default "crew"). Harness commands are named and saved in
the mb config file (~/.config/mb/config.json, or $MB_CONFIG) under "crew".
Set CREW_TMUX_SOCKET to use a separate tmux server (tmux -L).
"""
import argparse
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import time

CONFIG_FILE = pathlib.Path(os.environ.get("MB_CONFIG") or pathlib.Path.home() / ".config" / "mb" / "config.json")
LOG_ROOT = pathlib.Path.home() / ".local" / "state" / "crew"
SEP = "\t"
FIELDS = ["session", "window", "dead", "status", "harness", "started", "activity", "command", "crew", "log"]
FORMAT = SEP.join(["#{session_name}", "#{window_name}", "#{pane_dead}", "#{pane_dead_status}", "#{@crew_harness}",
                   "#{@crew_started}", "#{window_activity}", "#{pane_current_command}", "#{@crew}", "#{@crew_log}"])


def die(msg, code=1):
    print(f"crew: error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---- config ------------------------------------------------------------------------------------

def _read_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        die(f"cannot read config file {CONFIG_FILE}: {e}")


def _write_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def cmd_harness(args):
    cfg = _read_config()
    crew = cfg.setdefault("crew", {})
    harnesses = crew.setdefault("harnesses", {})
    if args.action == "add":
        if not args.name or not args.command:
            die('usage: crew harness add <name> "<command>"')
        harnesses[args.name] = args.command
        if not crew.get("default"):
            crew["default"] = args.name
        _write_config(cfg)
        print(f"harness {args.name}: {args.command}")
    elif args.action == "default":
        if args.name not in harnesses:
            die(f"no harness named {args.name}; add it with `crew harness add {args.name} \"<command>\"`")
        crew["default"] = args.name
        _write_config(cfg)
    elif args.action == "rm":
        if harnesses.pop(args.name, None) is None:
            die(f"no harness named {args.name}")
        if crew.get("default") == args.name:
            crew["default"] = next(iter(harnesses), None)
        _write_config(cfg)
    if not harnesses:
        print('no harnesses yet; e.g. crew harness add codex "codex"')
        return
    for name, command in harnesses.items():
        print(f"{'*' if name == crew.get('default') else ' '} {name:12} {command}")
    print(f"(saved in {CONFIG_FILE}; * = default)")


def _harness(spec):
    crew = _read_config().get("crew", {})
    harnesses = crew.get("harnesses", {})
    if spec is None:
        if not crew.get("default"):
            die('no default harness; add one with `crew harness add <name> "<command>"`, or pass --harness')
        return crew["default"], harnesses[crew["default"]]
    if spec in harnesses:
        return spec, harnesses[spec]
    return spec.split()[0], spec


# ---- tmux --------------------------------------------------------------------------------------

def _tmux_base():
    base = ["tmux"]
    if os.environ.get("CREW_TMUX_SOCKET"):
        base += ["-L", os.environ["CREW_TMUX_SOCKET"]]
    return base


def tmux(*args, check=True):
    result = subprocess.run(_tmux_base() + list(args), capture_output=True, text=True)
    if check and result.returncode != 0:
        die(f"tmux {' '.join(args[:2])}: {result.stderr.strip()}")
    return result


def _agents(session=None):
    result = tmux("list-windows", "-a", "-F", FORMAT, check=False)
    if result.returncode != 0:
        return []
    agents = []
    for line in result.stdout.splitlines():
        a = dict(zip(FIELDS, line.split(SEP)))
        if a.get("crew") == "1" and (session is None or a["session"] == session):
            agents.append(a)
    return agents


def _resolve(target, session=None):
    agents = _agents(session)
    if target.isdigit():
        i = int(target)
        if not 1 <= i <= len(agents):
            die(f"no agent #{target}; see `crew ls`")
        return agents[i - 1]
    if ":" in target:
        s, w = target.split(":", 1)
        hits = [a for a in agents if a["session"] == s and a["window"] == w]
    else:
        hits = [a for a in agents if a["window"] == target]
    if not hits:
        die(f"no agent {target}; see `crew ls`")
    if len(hits) > 1:
        die(f"{target} exists in several sessions ({', '.join(a['session'] for a in hits)}); use <session>:{target}")
    return hits[0]


def _tgt(a):
    return f"{a['session']}:{a['window']}"


def _age(epoch):
    try:
        s = max(0, int(time.time()) - int(epoch))
    except ValueError:
        return "-"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


# ---- commands ----------------------------------------------------------------------------------

def _names(session, base, n):
    taken = {a["window"] for a in _agents(session)}
    if n == 1 and base not in taken:
        return [base]
    names, i = [], 1
    while len(names) < n:
        if f"{base}-{i}" not in taken:
            names.append(f"{base}-{i}")
        i += 1
    return names


def cmd_launch(args):
    if not shutil.which("tmux"):
        die("tmux is not installed (e.g. sudo apt install tmux)")
    if args.prompt_file:
        prompt = sys.stdin.read() if args.prompt_file == "-" else pathlib.Path(args.prompt_file).read_text()
    else:
        prompt = args.prompt
    if not prompt or not prompt.strip():
        die("a prompt is required for every instance: crew launch ... \"<prompt>\" (or --prompt-file)")
    hname, command = _harness(args.harness)
    cwd = str(pathlib.Path(args.cwd).expanduser().resolve())
    env = []
    for kv in args.env:
        if "=" not in kv:
            die(f"--env needs KEY=VALUE, got {kv}")
        env += ["-e", kv]
    session_exists = tmux("has-session", "-t", f"={args.session}", check=False).returncode == 0
    launched = []
    for i, name in enumerate(_names(args.session, args.name, args.n), 1):
        text = prompt.replace("{i}", str(i)).replace("{name}", name).replace("{session}", args.session)
        full = command.replace("{prompt}", shlex.quote(text)) if "{prompt}" in command \
            else f"{command} {shlex.quote(text)}"
        wenv = env + ["-e", f"CREW_NAME={name}", "-e", f"CREW_SESSION={args.session}"]
        if session_exists:
            create = ["new-window", "-d", "-t", f"={args.session}:", "-n", name, "-c", cwd] + wenv + [full]
        else:
            create = ["new-session", "-d", "-s", args.session, "-n", name, "-c", cwd, "-x", "200", "-y", "50"] + wenv + [full]
            session_exists = True
        target = f"={args.session}:{name}"
        opts = [";", "set-option", "-w", "-t", target, "remain-on-exit", "on",
                ";", "set-option", "-w", "-t", target, "automatic-rename", "off",
                ";", "set-option", "-w", "-t", target, "@crew", "1",
                ";", "set-option", "-w", "-t", target, "@crew_harness", hname,
                ";", "set-option", "-w", "-t", target, "@crew_started", str(int(time.time()))]
        log = None
        if args.log:
            log = LOG_ROOT / args.session / f"{name}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            opts += [";", "set-option", "-w", "-t", target, "@crew_log", str(log),
                     ";", "pipe-pane", "-o", "-t", target, f"cat >> {shlex.quote(str(log))}"]
        tmux(*create, *opts)
        launched.append((name, log))
    print(f"launched {len(launched)} agent(s) in tmux session '{args.session}' with harness {hname}: {command}")
    for name, log in launched:
        print(f"  {name}" + (f"   log: {log}" if log else ""))
    print(f"\nsee them: crew ls   read one: crew peek {launched[0][0]}   enter one: crew attach {launched[0][0]}")


def cmd_ls(args):
    agents = _agents(args.session)
    if not agents:
        print("no crew agents" + (f" in session {args.session}" if args.session else ""))
        return
    now = int(time.time())

    def quiet(a):
        return a["dead"] != "1" and a["activity"].isdigit() and now - int(a["activity"]) > args.stale * 60

    running = sum(a["dead"] != "1" for a in agents)
    stale = sum(quiet(a) for a in agents)
    sessions = sorted({a["session"] for a in agents})
    print(f"{len(agents)} agent(s) in {len(sessions)} session(s): {running} running, {len(agents) - running} exited"
          + (f", {stale} quiet for >{args.stale}m (maybe waiting at a prompt: crew peek <agent>)" if stale else ""))
    print(f"{'#':>3}  {'SESSION':14} {'AGENT':14} {'STATE':12} {'HARNESS':10} {'UP':>7}  {'OUTPUT':>9}  COMMAND")
    for i, a in enumerate(agents, 1):
        state = "running" if a["dead"] != "1" else f"exited({a['status'] or '?'})"
        flag = "  <- quiet" if quiet(a) else ""
        print(f"{i:>3}  {a['session']:14} {a['window']:14} {state:12} {a['harness'] or '-':10} "
              f"{_age(a['started']):>7}  {_age(a['activity']) + ' ago':>9}  {a['command']}{flag}")


def cmd_peek(args):
    a = _resolve(args.target, args.session)
    out = tmux("capture-pane", "-p", "-J", "-t", _tgt(a), "-S", f"-{args.lines}").stdout.rstrip("\n")
    lines = out.splitlines()
    print("\n".join(lines[-args.lines:]))


def cmd_attach(args):
    if args.target:
        a = _resolve(args.target, args.session)
        session, target = a["session"], _tgt(a)
    else:
        sessions = sorted({a["session"] for a in _agents(args.session)})
        if len(sessions) != 1:
            die("say which agent: crew attach <agent>  (see `crew ls`)" if sessions else "no crew agents")
        session = target = sessions[0]
    if os.environ.get("TMUX") and not os.environ.get("CREW_TMUX_SOCKET"):
        os.execvp("tmux", ["tmux", "switch-client", "-t", target])
    tmux("select-window", "-t", target)
    print("entering; leave with Ctrl-b d (the agent keeps running)", file=sys.stderr)
    os.execvp("tmux", _tmux_base() + ["attach-session", "-t", session])


def cmd_send(args):
    a = _resolve(args.target, args.session)
    if a["dead"] == "1":
        die(f"{a['window']} has exited; nothing to type into")
    tmux("send-keys", "-t", _tgt(a), "-l", args.text)
    if not args.no_enter:
        time.sleep(0.2)
        tmux("send-keys", "-t", _tgt(a), "Enter")
    print(f"sent to {_tgt(a)}")


def cmd_kill(args):
    if args.all or args.exited or args.session_only:
        agents = _agents(args.session)
        if args.exited:
            agents = [a for a in agents if a["dead"] == "1"]
    elif args.targets:
        agents = [_resolve(t, args.session) for t in args.targets]
    else:
        die("say what to kill: crew kill <agent>... | --exited | --all [--session S]")
    for a in agents:
        tmux("kill-window", "-t", _tgt(a), check=False)
        print(f"killed {_tgt(a)}")
    if not agents:
        print("nothing to kill")


def main():
    p = argparse.ArgumentParser(prog="crew", description="Launch and drive agent sessions in tmux.")
    sub = p.add_subparsers(dest="cmd", required=True)

    hp = sub.add_parser("harness", help="named harness commands: list | add <name> \"<cmd>\" | default <name> | rm <name>")
    hp.add_argument("action", nargs="?", default="list", choices=["list", "add", "default", "rm"])
    hp.add_argument("name", nargs="?")
    hp.add_argument("command", nargs="?")
    hp.set_defaults(func=cmd_harness)

    lp = sub.add_parser("launch", help="start N agents, each with the same prompt")
    lp.add_argument("prompt", nargs="?", help="the prompt given to every instance ({i}, {name}, {session} are filled in)")
    lp.add_argument("-n", type=int, default=1, help="how many (default 1)")
    lp.add_argument("--name", default="agent", help="window name; several get -1, -2, ... (default agent)")
    lp.add_argument("--harness", default=None, help="a saved harness name, or a literal command (default: the default harness)")
    lp.add_argument("--session", default="crew", help="tmux session for this run (default crew)")
    lp.add_argument("--cwd", default=".", help="working directory (default: here)")
    lp.add_argument("--env", action="append", default=[], metavar="KEY=VALUE", help="extra environment (repeatable)")
    lp.add_argument("--prompt-file", default=None, help="read the prompt from a file ('-' for stdin)")
    lp.add_argument("--log", action="store_true", help=f"also record each screen to {LOG_ROOT}/<session>/<agent>.log")
    lp.set_defaults(func=cmd_launch)

    sp = sub.add_parser("ls", help="how many agents are running, and their state")
    sp.add_argument("--session", default=None)
    sp.add_argument("--stale", type=int, default=15, metavar="MINUTES",
                    help="flag running agents with no screen output for this long (default 15)")
    sp.set_defaults(func=cmd_ls)

    pk = sub.add_parser("peek", help="print an agent's screen without entering it")
    pk.add_argument("target", help="agent name, <session>:<name>, or # from `crew ls`")
    pk.add_argument("-n", "--lines", type=int, default=60)
    pk.add_argument("--session", default=None)
    pk.set_defaults(func=cmd_peek)

    ap = sub.add_parser("attach", help="enter an agent's session to read and type (Ctrl-b d to leave)")
    ap.add_argument("target", nargs="?")
    ap.add_argument("--session", default=None)
    ap.set_defaults(func=cmd_attach)

    snd = sub.add_parser("send", help="type one line into an agent's session")
    snd.add_argument("target")
    snd.add_argument("text")
    snd.add_argument("--no-enter", action="store_true", help="don't press Enter after the text")
    snd.add_argument("--session", default=None)
    snd.set_defaults(func=cmd_send)

    kp = sub.add_parser("kill", help="stop agents")
    kp.add_argument("targets", nargs="*")
    kp.add_argument("--exited", action="store_true", help="remove every exited agent")
    kp.add_argument("--all", action="store_true", help="every agent (in --session, if given)")
    kp.add_argument("--session", default=None)
    kp.set_defaults(func=cmd_kill, session_only=False)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
