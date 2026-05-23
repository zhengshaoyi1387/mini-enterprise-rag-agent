# Enterprise Skill Runtime Findings

## Current State

- The user wants a low-risk skill runtime layered onto the existing unified mainline.
- Existing worktree already contains SQLite repositories and tool changes; this task must not revert them.
- Tests should run in the Ubuntu ollama environment:
  `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python ...`

## Design Notes

- Skill Runtime will live under `src/mini_rag/skills/`.
- Skill packages will live under top-level `skills/`.
- Planner integration should be minimal: expose Skill Cards/tool adapter, but avoid injecting large `SKILL.md` content into prompts.

