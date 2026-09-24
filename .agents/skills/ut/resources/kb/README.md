# Knowledge bases, one per codebase

Each folder here belongs to exactly ONE codebase:
```
kb/
  INDEX.md                 one row per codebase: id, remote, where it was seen
  <codebase-id>/
    kb.md                  durable knowledge (conventions, module notes, build quirks, learnings)
    codemap/               output of scripts/codemap.sh (regenerate when code changes a lot)
    decompositions/        module notes written by a stronger model (optional)
```
`<codebase-id>` comes from `scripts/kb-id.sh <repo>` (based on the git `origin` URL), so every clone,
branch and machine of the same repository finds the same folder.

Rules:
- Never read or use a KB folder whose id differs from the current codebase's id.
- When you update the ut skill, KEEP this `kb/` folder (copy it over to the new version).
- If this skill folder lives inside a repository, the KB is committed with it unless you ignore it.
