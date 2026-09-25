"""Task state (state.json) and the human/agent-readable renderings (status.md, context.md)."""
import datetime, json, os

PHASES = ['setup', 'baseline', 'knowledge', 'discovery', 'scope', 'pilot', 'coverage', 'plan', 'execute', 'closeout']
CATS = {'A': 'remove', 'B': 'update tests', 'C': 'mocks/stubs', 'D': 'new tests', 'E': 'fix build',
        'F': 'fix run', 'G': 'coverage', 'H': 'cleanup', 'I': 'production bug (report only)'}


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


class State:
    def __init__(self, task_dir):
        self.dir = os.path.abspath(task_dir)
        self.path = os.path.join(self.dir, 'state.json')
        self.d = {'task': self.dir, 'created': now(), 'phases': {}, 'profile': {}, 'permissions':
                  {'production_code': 'no', 'delete_tests': 'ask', 'commit': 'no'}, 'safe_run': 'yes',
                  'inputs': [], 'coverage': {'wanted': 'no'}, 'resources': [], 'pilot': 'undecided',
                  'parallel': 0, 'baseline': {}, 'work_items': [], 'acceptance': '', 'plan': {'tasks': [], 'checkpoints': {}},
                  'open_issues': [], 'next_steps': [], 'decisions': [], 'log': []}
        if os.path.exists(self.path):
            self.d.update(json.load(open(self.path, encoding='utf-8')))

    def __getitem__(self, k): return self.d[k]
    def __setitem__(self, k, v): self.d[k] = v
    def get(self, k, default=None): return self.d.get(k, default)

    def log(self, who, msg):
        self.d['log'].append(f'{now()} [{who}] {msg}')

    def decide(self, q, a):
        self.d['decisions'].append({'when': now(), 'q': q, 'a': a})

    def done(self, phase, note=''):
        self.d['phases'][phase] = note or now()

    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        json.dump(self.d, open(self.path, 'w', encoding='utf-8'), indent=1)
        self.render()

    # ------------------------------------------------------------------ renderings
    def render(self):
        d = self.d
        L = ['# UT Task Status', f'> Rendered by the ut tool from state.json on {now()}. Edit state through the tool.', '', '## Config',
             '| Key | Value |', '|-----|-------|']
        for k in ('task', 'skill_dir', 'kb_dir', 'request', 'mode', 'safe_run', 'pilot', 'parallel', 'acceptance'):
            L.append(f'| {k} | {d.get(k, "")} |')
        L.append(f"| permissions | {', '.join(f'{k}: {v}' for k, v in d['permissions'].items())} |")
        L.append(f"| coverage | {d['coverage']} |")
        L.append(f"| resources | {', '.join(d['resources'])} |")
        L += ['', '## Profile'] + table(d['profile'])
        L += ['', '## Phases']
        L += [f"- [{'x' if p in d['phases'] else ' '}] {i + 1} {p}{': ' + d['phases'][p] if p in d['phases'] else ''}" for i, p in enumerate(PHASES)]
        L += ['', '## Baseline'] + table(d['baseline'])
        L += ['', '## Plan', '| ID | Title | Type | Wave | Depends | Status | Owner | Attempts |', '|---|---|---|---|---|---|---|---|']
        for t in d['plan']['tasks']:
            L.append(f"| {t['id']} | {t['title']} | {t['type']} | {t['wave']} | {','.join(t.get('depends', []))} | {t['status']} | {t.get('owner', '')} | {t.get('attempts', 0)} |")
        L += ['Checkpoints: ' + ', '.join(f'wave {k}: {v}' for k, v in d['plan']['checkpoints'].items())]
        L += ['', '## Open issues'] + [f'- {x}' for x in d['open_issues']] + ['', '## Next steps'] + [f'- {x}' for x in d['next_steps']]
        L += ['', '## Log'] + [f'- {x}' for x in d['log'][-60:]]
        open(os.path.join(self.dir, 'status.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
        C = ['# Task Context', '', '## 1. Request', d.get('request', ''), '', '## 2. Inputs'] + [f'- {x}' for x in d['inputs']]
        C += ['', '## 3. Work items', f"Mode: {d.get('mode', '')}  Range: {d.get('range', '')}",
              '| W# | Code item | Change kind | Existing tests | Mocks affected | Proposed work | Cat | In scope | Priority |',
              '|----|-----------|-------------|----------------|----------------|---------------|-----|----------|----------|']
        for w in d['work_items']:
            C.append(f"| {w['id']} | {w['item']} | {w['kind']} | {w.get('tests', '')} | {w.get('mocks', '')} | {w.get('work', '')} | {w['cat']} | {w.get('in_scope', '')} | {w.get('priority', '')} |")
        C += ['', f"Acceptance for the task: {d.get('acceptance', '')}", '', '## 4. Baseline problems'] + [f'- {x}' for x in d['baseline'].get('problems', [])]
        C += ['', '## 5. Coverage gaps'] + [f'- {x}' for x in d.get('coverage_gaps', [])]
        C += ['', '## 6. Decisions', '| When | Question | Answer |', '|---|---|---|'] + [f"| {x['when']} | {x['q']} | {x['a']} |" for x in d['decisions']]
        open(os.path.join(self.dir, 'context.md'), 'w', encoding='utf-8').write('\n'.join(C) + '\n')


def table(dct):
    return ['| Key | Value |', '|-----|-------|'] + [f'| {k} | {v} |' for k, v in dct.items() if not isinstance(v, (list, dict))] + \
           [f'| {k} | {", ".join(map(str, v))} |' for k, v in dct.items() if isinstance(v, list)]
