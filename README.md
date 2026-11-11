# ai-data-agent-example

A reusable setup for Claude Code and Codex to work with **MySQL, AWS / Redshift, GitHub,
and MLflow tracing** through MCP servers and agent integrations.

## Install into a work directory

Run this from your work project to install directly from GitHub:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-data-agent-example/main/install.sh)
```

The installer configures **both agents locally by default**. Generated files are hidden through
that clone's `.git/info/exclude`, so there is nothing to commit. There is no `--local` flag or
shared installation mode. Existing tracked settings are preserved.

Select one agent when needed:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-data-agent-example/main/install.sh) --claude
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-data-agent-example/main/install.sh) --codex
```

An optional project path selects another destination. From a clone of this kit:

```bash
./install.sh /path/to/project                 # both agents, local-only
./install.sh --claude /path/to/project        # only Claude
./install.sh --codex /path/to/project         # only Codex
./install.sh --uninstall /path/to/project     # remove both recorded installs
./install.sh --codex --uninstall /path/to/project  # remove only Codex
```

Full syntax: `./install.sh [--claude | --codex] [--uninstall] [project-dir]`.
The target defaults to the Git repo root you're in, or the current directory outside Git.
Nested project directories and non-Git directories are supported. Outside Git the installer
writes the same local configuration, with no Git exclusions to add.

Install requires **Python 3.11+** when Codex is selected, or Python 3 for Claude-only installs.
You also need the selected agent installed, **Node.js 18+** (`npx`) and **uv** (`uvx`) to run the
integrations. The installer uses templates from its clone when available; when run through curl,
it downloads the selected templates from GitHub. `AI_KIT_BRANCH` selects the download branch.
The remote commands include changes only after they have been pushed to that branch.

## What's included

| Source file | Purpose |
|---|---|
| `install.sh` | One local-only installer for both agents, with selection and uninstall arguments |
| `.claude/settings.json` | Claude plugin, tracing and startup-hook template, merged into the destination's `.claude/settings.local.json` |
| `.claude/hooks/install-plugins.py` | Installs missing Claude plugins and updates installed plugins at startup |
| `.mcp.json` | MySQL MCP template for Claude |
| `codex/config.toml` | Codex MCP connections and MLflow notification-hook template |
| `codex/mlflow-tracing.json` | MLflow tracking URI and experiment template for Codex |
| `tests/` | Installer regression tests using disposable project directories |

Both agents connect to the same MySQL database and use the same MLflow destination:
`https://mlflow.yliumono.click`, experiment `yliu` (ID `2`). AWS and GitHub access depend on the
permissions of your credentials. The installer does not store credentials in the templates.

## Credentials

Export credentials in the terminal where you will launch the agent:

```bash
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_DATABASE=...
export MYSQL_USER=...
export MYSQL_PASSWORD=...
export GITHUB_PERSONAL_ACCESS_TOKEN=...
export MLFLOW_TRACKING_USERNAME=...
export MLFLOW_TRACKING_PASSWORD=...
# Optional: select a configured AWS profile instead of the default credential chain.
export AWS_PROFILE=...
```

AWS credentials can also come from `aws login` or the standard AWS credential environment
variables. Use a GitHub token with access to the repositories you need.

For Claude, you may put the MLflow username and password in the `env` object of
`.claude/settings.local.json` instead. Codex does not read Claude settings, so export the
credentials when using Codex. Do not commit credentials.

## Claude behavior

The installer merges the Claude template into **`.claude/settings.local.json`**, preserving
unrelated settings and listing overlapping values it updates. The startup hook installs plugins
at local scope for settings enabled in that file. The kit enables `aws-core`, `aws-data-analytics`,
`github`, and `mlflow-tracing`, plus their marketplace configuration.

If `.mcp.json` is untracked, the installer merges the MySQL server into it and hides it from Git.
If the project already tracks `.mcp.json`, the installer registers MySQL at local scope using
`claude mcp add-json --scope local`, preserving the tracked file. Existing local registrations
are not removed unless they belong to this kit. If the CLI rejects an addition, the installer
prints a manual setup warning.

Tracked `.claude/settings.local.json`, or a different tracked plugin hook at the same path,
causes the Claude install to stop. A matching tracked hook can be reused without modification.
The kit does not edit the project's shared `.claude/settings.json`.

Run `claude` in the destination project. On the first start the hook installs the plugins;
run `/reload-plugins` or restart to load them. Approve the MySQL MCP server when prompted.
MLflow tracing requires a reachable tracking server and valid credentials.

## Codex behavior

The installer adds marked blocks to **`.codex/config.toml`** and writes
**`.codex/mlflow-tracing.json`**. Unrelated settings and comments are preserved. Codex loads
project configuration for trusted projects; start `codex` in the destination, trust the project
when prompted, and use `/mcp` to check the three servers.

| Integration | Codex implementation |
|---|---|
| MySQL | Same Toolbox MCP command as Claude, with `MYSQL_*` variables forwarded |
| AWS / Redshift | AWS managed MCP server through `mcp-proxy-for-aws@1.6.3`, using local AWS credentials |
| GitHub | GitHub's hosted MCP server, with a token read from `GITHUB_PERSONAL_ACCESS_TOKEN` |
| MLflow | Official `@mlflow/codex` notification hook, recording conversation traces after completed CLI turns |

Codex installation stops before writing if an existing `notify` hook or an MCP server named
`mysql`, `aws-mcp`, or `github` conflicts. Resolve the conflicting entry manually before installing.
It also refuses tracked `.codex` destination files and symlinked Codex configuration paths, so it
cannot silently change shared or global configuration. Existing unrelated untracked settings can
be extended locally.

The AWS endpoint and default operation region are `us-east-1`. To select another operation region,
add `"--metadata", "AWS_REGION=your-region"` to the proxy arguments in `codex/config.toml` in this
kit, then rerun the installer. `AWS_REGION` alone does not select the managed server's operation
region. Your IAM permissions must allow the MCP server and downstream AWS operations.

To override the Codex MLflow destination without editing templates, export `MLFLOW_TRACKING_URI`
and `MLFLOW_EXPERIMENT_ID`. The repo does not verify your server version or authentication setup.

## Updates and uninstall

Re-run the installer with the same agent selection to update its configuration. Claude's startup
hook updates its enabled plugins. MySQL and the MLflow Codex package use `@latest`; Claude's AWS
plugins manage their MCP dependencies. The Codex AWS proxy is pinned and updated explicitly in
the template. First startup may take longer while packages are downloaded.

Each agent records its changes in its own `.claude/ai-kit.json` or `.codex/ai-kit.json`. Keep these
records for uninstall. The Git exclusions and local-only plugin/server registrations are part of
the recorded setup. The installer does not install packages globally or commit files.

Uninstall directly from GitHub:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-data-agent-example/main/install.sh) --uninstall
```

Add `--claude` or `--codex` to uninstall only one agent. Missing agent installs are skipped.
Uninstall removes recorded configuration, restores overwritten values where possible, removes
owned local registrations and plugins, and drops the exclusions it added. User edits are
preserved and reported. Codex's marked configuration blocks must remain intact for an update or
uninstall; edited blocks must be restored first. Edits outside those blocks are preserved.

If you used an older **shared installation**, uninstall it first with the selected agent's
`--uninstall` command, then rerun the installer. Legacy manifests are still supported for removal;
new installations are always local. You must commit the removal of previously tracked shared
files yourself if you want that removal reflected in Git.

If installation stops with an error, fix the reported issue and rerun. Changes to the other
agent may already have been applied. Local exclusions cannot hide files that Git already tracks,
which is why conflicting tracked destinations are refused.

## Verification and references

Run installer checks without contacting any service:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover agent selection, local Git visibility, update/uninstall, existing settings and hooks,
conflicts, symlinks, and simulated direct-from-GitHub downloads. Live authentication to the four
services must be verified with your credentials.

References: [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp),
[MLflow Codex tracing](https://www.mlflow.org/docs/latest/genai/tracing/integrations/listing/codex/),
[AWS MCP proxy configuration](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md),
and [GitHub MCP server](https://github.com/github/github-mcp-server).
