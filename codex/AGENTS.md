## Connector check

On the first turn of each new session, use the `check-connectors` skill at
`.agents/skills/check-connectors/SKILL.md` to check the configured connections with
read-only probes. Show the compact results table, then continue the user's task.
Report missing credentials or tools without blocking the task or exposing secrets.
Run once per session; rerun when the user requests it. Follow an explicit request
to skip the check.
