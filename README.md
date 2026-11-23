# ai-agent-data-toolkit

Set up **Claude Code and Codex** in a project to work with **MySQL, AWS / Redshift,
GitHub, Atlassian (Jira / Confluence), and MLflow conversation tracing**.
This guide uses **v1.1.4**, which adds Atlassian browser login.
MLflow remains a separate tracing mechanism.

## Atlassian setup

To install from a local checkout, run its installer against your project:

```bash
bash /path/to/ai-agent-data-toolkit/install.sh /path/to/your/project
```

Append `--claude` or `--codex` before the project path to configure one agent.
The commands in section 2 install the published release, including Atlassian support.

Both agents connect directly to the official
[Atlassian MCP server](https://atlassian.github.io/atlassian-mcp-server/)
at `https://mcp.atlassian.com/v2/mcp`. This requires an Atlassian Cloud site;
self-hosted Jira Data Center needs a different integration.

Both templates use manual browser login (OAuth). No Atlassian API-token
environment variables are required.

1. Install the configuration into your destination project.
2. For Codex, trust the destination project, then run `codex mcp login atlassian`
   from that project directory and complete the browser sign-in and authorization.
3. For Claude Code, launch Claude in the destination project, open `/mcp`, select
   `atlassian`, and complete its authentication flow in your browser.

Access follows your signed-in account's permissions and organization policies.
See the [official setup guide](https://atlassian.github.io/atlassian-mcp-server/).
The installer only adds configuration; it does not sign you in or verify Jira access.
After login, run the connection check or ask: “Read and summarize Jira issue PROJ-123.”
Reinstall and uninstall use the same tracked configuration mechanism as the other
MCP servers. OAuth credentials are managed by the agent client, outside installer records.

Claude templates are grouped under `claude/`, including `claude/.mcp.json` for MySQL and Atlassian.
The installer merges that MCP template into the destination project's root `.mcp.json`,
where Claude reads project MCP configuration. Codex templates live under `codex/`.

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
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.4/install.sh)
```

To configure only one agent, use the matching command:

```bash
# Claude Code only
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.4/install.sh) --claude

# Codex only
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.4/install.sh) --codex
```

You can also append an existing project directory to any installation command:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.4/install.sh) --codex /path/to/your/project
```

Without a path, the target is your current Git repository's root, or your current directory
outside Git. Configuration is local to that project. Installer-owned files are excluded
from Git through `.git/info/exclude`; unrelated settings are preserved.

Use the explicit `v1.1.4` URL above to stay on this version. A latest-release URL may
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
Conversation tracing is configured by the installer. Codex additionally requires you
to review and trust the installed hook before it runs. For a different destination:

- **Claude Code:** change `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT_ID`, and
  `MLFLOW_EXPERIMENT_NAME` in the `env` object of `.claude/settings.local.json`.
- **Codex:** export `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` before launching.
  Alternatively, edit the project's `.codex/mlflow-tracing.json`.

## 4. Start your agent

Run your chosen agent from the project directory where you installed the toolkit.

### Claude Code

```bash
claude
```

The installer installs the enabled AWS, GitHub, and MLflow plugins at local scope.
If Claude was already running, use `/reload-plugins` or restart it. If plugin installation
fails or the Claude CLI is unavailable, resolve the reported problem and rerun the installer.
Approve the MySQL and Atlassian MCP servers when prompted. Open `/mcp`, select
`atlassian`, and complete browser authentication.

### Codex

```bash
codex
```

Trust the project when prompted so its configuration can load. Use `/mcp` to inspect the
MySQL, AWS, GitHub, and Atlassian servers. From that project directory, run
`codex mcp login atlassian` and complete browser authentication, then restart Codex.
Use `/hooks`
or **Review hooks** in the desktop app to review and trust the project-local `Stop`
hook. Project trust and hook trust are separate; automatic tracing is skipped until
the exact hook definition is trusted.

The installer merges a hook entry into `.codex/hooks.json` and installs its adapter at
`.codex/hooks/mlflow_stop.py`. The adapter reads the latest user prompt from Codex's
JSONL transcript and calls `@mlflow/codex@0.4.0` after a completed turn. It uses the
project's MLflow destination and existing credential environment. It does not add
user-level settings. Hook command paths are quoted for spaces and resolve to the
installed project even when invoked from a subdirectory. Start Codex at the project
root so its configuration is discovered.

Tracing failures produce a warning without blocking or continuing the coding turn.
Transcript parsing depends on Codex's transcript format, which can change; review
the adapter when upgrading Codex if prompts stop being captured.
The bundled AWS configuration uses `us-east-1`; there is no installer region flag.

## 5. Check connections and start working

Connection checks are **manual in v1.1.4**. In your agent session, run:

| Agent | Prompt |
|---|---|
| Claude Code | `/check-connectors` |
| Codex | `$check-connectors` |

You can also ask: “Check whether this project's connector tools work.”

The check uses small read-only probes and reports `PASS`, `FAIL`, or `UNTESTED`, with
evidence and a next step for MySQL, AWS, Redshift, GitHub, and Atlassian. Run it after setup
and after changing credentials. Installation alone does not verify connectivity.
AWS authentication does not prove Redshift SQL access. MLflow is a separate conversation
tracing mechanism and is outside the connection-check skill's scope.

Once the connections you need work, ask the agent to use them. For example:

- “List the tables in my MySQL database and describe their columns.”
- “List the Redshift workgroups I can access in us-east-1.”
- “Summarize the open issues in owner/repository.”

Access depends on your credentials and service permissions.

## Update or uninstall

Rerun the same installation command to reapply v1.1.4. To upgrade, replace `v1.1.4` in
the URL with the desired published release tag and keep the same agent selection.
Toolkit upgrades are manual; some runtime packages use `@latest`. Claude plugin updates
use Claude's native marketplace auto-update settings, configurable in `/plugin` under
Marketplaces. Official marketplaces enable auto-update by default; third-party marketplaces
such as MLflow require you to enable it. The toolkit does not update plugins at startup.
Rerunning the installer removes the toolkit's previously recorded startup hook while
preserving user hooks and edited hook files.

The installer also migrates an older toolkit-owned Codex `notify` block to
the project-local `Stop` hook. Reinstalling preserves unrelated hooks and avoids
duplicate toolkit entries. Uninstall removes the toolkit entry, restores original
hook files where possible, and preserves edited adapter files with a notice.

If you installed v1.1.0, uninstall it with its v1.1.0 installer before installing
v1.1.4 so its added `CLAUDE.md` / `AGENTS.md` instructions are cleaned up.

Keep `.claude/ai-kit.json` and `.codex/ai-kit.json`: they record the installed version and
changes needed for uninstall.

From the destination project, remove both agents' recorded toolkit configuration:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.1.4/install.sh) --uninstall
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
  blocks, Stop hook entry, adapter, or edited connector skill before updating.
  Preserve your customizations separately.
- **Codex traces are missing:** open `/hooks` or **Review hooks** and check that the
  project Stop hook is enabled and trusted. The connector check verifies configuration
  and optional experiment reads; it does not upload a trace to test tracing.
- **An older shared installation is detected:** uninstall it with its installer before
  installing this local version.
