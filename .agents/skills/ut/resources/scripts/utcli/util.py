import os, re, shlex, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
SKILL_DIR = os.path.dirname(os.path.dirname(SCRIPTS))
RES = os.path.join(SKILL_DIR, 'resources')


def sh(cmd, cwd=None, timeout=3600, env=None, input_text=None):
    """run a shell command; returns (rc, combined output)"""
    r = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, capture_output=True, text=True, errors='replace',
                       timeout=timeout, env=env, input=input_text)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def script(name):
    return os.path.join(SCRIPTS, name)


def read(path, default=''):
    try:
        return open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return default


def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'w', encoding='utf-8').write(text)


def ask(question, default='', yes=False, answers=None, key=None):
    """one question with a default; --yes takes the default; answers dict (from --answers) wins"""
    if answers and key in answers:
        return str(answers[key])
    if yes:
        return default
    try:
        a = input(f'{question} [{default}]: ').strip()
    except EOFError:
        a = ''
    return a or default


def say(msg):
    print(msg, flush=True)


def norm(p):
    return p.replace('\\', '/')


def md_table_rows(text, first_col_prefix):
    """rows of a markdown table whose first cell starts with prefix -> list of cell lists"""
    rows = []
    for line in text.splitlines():
        if line.startswith('| ' + first_col_prefix) or re.match(r'\|\s*' + re.escape(first_col_prefix) + r'\d', line):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows.append(cells)
    return rows


def words(text):
    return len(text.split())
