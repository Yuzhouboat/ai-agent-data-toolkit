# ai-agent-data-toolkit

Set up **Claude Code and Codex** in a project to work with **MySQL, AWS / Redshift,
GitHub, and MLflow conversation tracing**. This guide uses **v1.1.1**, which restores the v1.0.0 behavior.

## 1. Prerequisites

Install the agent you want to use, plus:

- **Python 3.11+** for Codex or both agents; Python 3 for Claude-only installation.
- **Node.js 18+**, including `npx`.
- **uv**, including `uvx`.
- **curl** and **Bash** to run the installation commands below.

Have credentials ready for the services you want to use.

## 2. Install in your project

From your project directory, install configuration for both agents:

```bash
cd /path/to/your/project
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.1/install.sh)
```

To configure only one agent, use the matching command:

```bash
# Claude Code only
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.1/install.sh) --claude

# Codex only
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.1/install.sh) --codex
```

You can also append an existing project directory to any installation command:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.1/install.sh) --codex /path/to/your/project
```

Without a path, the target is your current Git repository's root, or your current directory
outside Git. Configuration is local to that project. Installer-owned files are excluded
from Git through `.git/info/exclude`; unrelated settings are preserved.

Use the explicit `v1.1.1` URL above to stay on this version. A latest-release URL may
install a newer version.

## 3. Set credentials

Replace the placeholders and export these variables in the terminal where you will launch
the agent:

```bash
export MYSQL_HOST='localhost'
export MYSQL_PORT='3306'
export MYSQL_DATABASE='your_database'
export MYSQL_USER='your_user'
export MYSQL_PASSWORD='your_password'
export GITHUB_PERSONAL_ACCESS_TOKEN='your_github_token'
export MLFLOW_TRACKING_USERNAME='your_mlflow_username'
export MLFLOW_TRACKING_PASSWORD='your_mlflow_password'

# Optional: select an existing AWS profile.
export AWS_PROFILE='your_profile'
```

AWS uses your existing credential chain, including configured profiles or AWS credential
environment variables. Use credentials with permission for the AWS resources and GitHub
repositories you need.

The installer does not load `.env` files or prompt for credentials. Restart the agent from
this terminal after changing variables. Keep credentials out of Git.

Both agents default to MLflow at `https://mlflow.yliumono.click`, experiment `yliu` (ID `2`).
Conversation tracing is enabled by the installed configuration. For a different destination:

- **Claude Code:** change `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_ID`, and
  `MLFLOW_EXPERIMENT_NAME` in the `env` object of `.claude/settings.local.json`.
- **Codex:** export `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` before launching.

## 4. Start your agent

Run your chosen agent from the project directory where you installed the toolkit.

### Claude Code

```bash
claude
```

On first startup, the toolkit's hook installs the enabled AWS, GitHub, and MLflow plugins.
Run `/reload-plugins` or restart Claude to load them. Approve the MySQL MCP server when
prompted. First startup may take longer while dependencies download.

### Codex

```bash
codex
```

Trust the project when prompted so its configuration can load. Use `/mcp` to inspect the
MySQL, AWS, and GitHub servers. MLflow runs as a tracing hook after completed CLI turns.
The bundled AWS configuration uses `us-east-1`; there is no installer region flag.

## 5. Check connections and start working

Connection checks are **manual in v1.1.1**. In your agent session, run:

| Agent | Prompt |
|---|---|
| Claude Code | `/check-connectors` |
| Codex | `$check-connectors` |

You can also ask: “Check whether this project's connector tools work.”

The check uses small read-only probes and reports `PASS`, `FAIL`, or `UNTESTED`, with
evidence and a next step for MySQL, AWS, Redshift, GitHub, and MLflow. Run it after setup
and after changing credentials. Installation alone does not verify connectivity.
AWS authentication does not prove Redshift SQL access, and an MLflow configuration or
experiment-read check does not prove that a conversation trace was uploaded.

Once the connections you need work, ask the agent to use them. For example:

- “List the tables in my MySQL database and describe their columns.”
- “List the Redshift workgroups I can access in us-east-1.”
- “Summarize the open issues in owner/repository.”

Access depends on your credentials and service permissions.

## Update or uninstall

Rerun the same installation command to reapply v1.1.1. To upgrade, replace `v1.1.1` in
the URL with the desired published release tag and keep the same agent selection.
Toolkit upgrades are manual; some runtime packages use `@latest`, and Claude's startup
hook updates its enabled plugins.

If you installed v1.1.0, uninstall it with its v1.1.0 installer before installing
v1.1.1 so its added `CLAUDE.md` / `AGENTS.md` instructions are cleaned up.

Keep `.claude/ai-kit.json` and `.codex/ai-kit.json`: they record the installed version and
changes needed for uninstall.

From the destination project, remove both agents' recorded toolkit configuration:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.1/install.sh) --uninstall
```

Add `--claude` or `--codex` to remove only that agent's setup, and append the project path
if running from another directory. Use the installer matching your recorded installed version.
Uninstall restores overwritten settings where possible and preserves edited files with a notice.

## If something fails

- **Missing tools or authentication errors:** check prerequisites and credentials, restart
  the agent from the terminal containing your exports, then rerun the connection check.
- **Installation reports conflicting settings or tracked files:** resolve the reported
  conflict and rerun. One agent may already be installed even if the other fails.
- **An update reports edited managed files:** restore the toolkit's marked Codex config
  blocks or edited connector skill before updating. Preserve your customizations separately.
- **An older shared installation is detected:** uninstall it with its installer before
  installing this local version.
