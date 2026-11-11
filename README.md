# ai-agent-data-toolkit

A reusable setup for Claude Code and Codex to work with **MySQL, AWS / Redshift, GitHub,
and MLflow tracing** through MCP servers and agent integrations.

## Install into a work directory

Run the installer from the project where you want to use the agents. It configures
**both agents locally by default**. For Codex, installation requires **Python 3.11+**;
Claude-only installation requires Python 3. Running the integrations also requires the selected
agent, **Node.js 18+** (`npx`), and **uv** (`uvx`).

Current release: [v1.0.0](https://github.com/Yuzhouboat/ai-agent-data-toolkit/releases/tag/v1.0.0).
Both installation methods below are published and available.

Install the latest published release:

```bash
bash <(curl -fsSL https://github.com/Yuzhouboat/ai-agent-data-toolkit/releases/latest/download/install.sh)
```

To install a specific version, use its release tag. For example, to install `v1.0.0`:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.0.0/install.sh)
```

The latest-release command downloads the `install.sh` asset attached to the latest published
GitHub release. Both commands download templates from the selected installer's fixed release
tag. Pushing changes to `main` does not publish a release or change an existing version.

Generated files are hidden through the destination repository's `.git/info/exclude`, so there
is nothing to commit. There is no `--local` flag or shared installation mode.
Existing tracked settings are preserved; conflicting destinations cause installation to stop.

Select one agent when needed:

```bash
bash <(curl -fsSL https://github.com/Yuzhouboat/ai-agent-data-toolkit/releases/latest/download/install.sh) --claude
bash <(curl -fsSL https://github.com/Yuzhouboat/ai-agent-data-toolkit/releases/latest/download/install.sh) --codex
```

An optional project path selects another destination:

```bash
bash <(curl -fsSL https://github.com/Yuzhouboat/ai-agent-data-toolkit/releases/latest/download/install.sh) /path/to/project
```

Append `[--claude | --codex] [--uninstall] [project-dir]` to either curl command as needed.
The target defaults to the Git repo root you're in, or the current directory outside Git.
Nested project directories and non-Git directories are supported. Outside Git the installer
writes the same local configuration, with no Git exclusions to add.

After installation, set credentials, start the selected agent in the destination project,
and run its connector-check prompt below. Branch overrides are not supported.

## What's included

Templates live in the visible `claude/` and `codex/` source folders. The installer writes
agent configuration into `.claude/` and `.codex/` in the destination project. The shared
connector-check skill lives in `skills/` here and is installed into each agent's skill directory.

| Source file | Purpose |
|---|---|
| `install.sh` | One local-only installer for both agents, with selection and uninstall arguments |
| `claude/settings.json` | Claude plugin, tracing and startup-hook template, merged into the destination's `.claude/settings.local.json` |
| `claude/hooks/install-plugins.py` | Installs missing Claude plugins and updates installed plugins at startup |
| `.mcp.json` | MySQL MCP template for Claude |
| `codex/config.toml` | Codex MCP connections and MLflow notification-hook template |
| `codex/mlflow-tracing.json` | MLflow tracking URI and experiment template for Codex |
| `skills/check-connectors/SKILL.md` | Shared read-only connector-check prompt installed for each selected agent |
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

The installer does not prompt for credentials, load `.env` files or a private credentials
file, or configure a secret manager. Missing credentials do not block installation; the
agent may report errors later when tools start or connect. After changing exported variables,
restart the agent from that terminal so it inherits the new values.

For Claude, you may put the MLflow username and password in the `env` object of
`.claude/settings.local.json` instead. Codex does not read Claude settings, so export the
credentials when using Codex. Do not commit credentials.

## Check connections

After installing, start a new agent session in the destination project and invoke:

| Agent | Prompt |
|---|---|
| Claude Code | `/check-connectors` |
| Codex | `$check-connectors` |

You can also ask either agent: "Check whether this project's connector tools work."
The installer places the shared skill in `.claude/skills/check-connectors/SKILL.md` for
Claude and `.agents/skills/check-connectors/SKILL.md` for Codex. Both are local to the
destination project and excluded from Git when the installer owns them.

The prompt checks MySQL, AWS, Redshift, GitHub, and MLflow using available tools and small
read-only operations. It reports `PASS`, `FAIL`, or `UNTESTED` with evidence and a next step,
without showing credential values. Missing tools and authentication errors are reported
separately. AWS identity does not prove Redshift database access; MLflow configuration or
experiment read access does not prove the tracing hook uploaded a trace. The check does
not install packages, change settings, or create test data.

Installation itself does not check credentials or contact these services. Run this prompt
after setting credentials, and again after changing them. It verifies the operations
actually attempted, rather than every tool or permission the integrations might expose.

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

The versioned Codex template sets the AWS endpoint and default operation region to `us-east-1`.
The installer has no region-selection flag. `AWS_REGION` alone does not select the managed
server's operation region. Your IAM permissions must allow the MCP server and downstream
AWS operations. Re-running a published installer reapplies its templates; it does not use
edits made to this repository's templates on `main`.

To override the Codex MLflow destination without editing templates, export `MLFLOW_TRACKING_URI`
and `MLFLOW_EXPERIMENT_ID`. The repo does not verify your server version or authentication setup.

## Updates and uninstall

To upgrade, run the curl command for the newer release tag with the same agent selection.
Alternatively, rerun the latest-release command to install the current published release:

```bash
bash <(curl -fsSL https://github.com/Yuzhouboat/ai-agent-data-toolkit/releases/latest/download/install.sh)
```

Re-running the same release reapplies that version; upgrades are never automatic. Existing
unversioned local installs can be upgraded with the same command. Each agent records the installed
release in the `version` field of its `ai-kit.json` file. Unrelated settings are preserved.

Release tags are fixed once published. Installer and template versions are pinned; runtime
dependencies that use `@latest` can still change independently. Claude's startup
hook updates its enabled plugins. MySQL and the MLflow Codex package use `@latest`; Claude's AWS
plugins manage their MCP dependencies. The Codex AWS proxy is pinned and updated explicitly in
the template. First startup may take longer while packages are downloaded.

Each agent records its changes in its own `.claude/ai-kit.json` or `.codex/ai-kit.json`. Keep these
records for uninstall. The Git exclusions and local-only plugin/server registrations are part of
the recorded setup. The installer does not install packages globally or commit files.

Uninstall using the installer for the version recorded in your agent's `ai-kit.json`.
For `v1.0.0`:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/v1.0.0/install.sh) --uninstall
```

Add `--claude` or `--codex` to uninstall only one agent. Missing agent installs are skipped.
Uninstall removes recorded configuration, restores overwritten values where possible, removes
owned local registrations and plugins, and drops the exclusions it added. User edits are
preserved and reported. Codex's marked configuration blocks must remain intact for an update or
uninstall; edited blocks must be restored first. Edits outside those blocks are preserved.
Connector skills are updated and uninstalled with their selected agent. A different existing
skill at the destination blocks installation. Restore an edited installed skill before updating;
uninstall preserves edited skills. Unrelated skills and preexisting matching skill files are kept.
Codex refuses a tracked `.agents/skills/check-connectors/SKILL.md`, even if its content matches.
Claude can reuse a matching tracked connector skill without changing it.

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
conflicts, symlinks, connector skill lifecycle, release-pinned downloads, versioned and
unversioned upgrades, and download failures. Live authentication must be verified with
your credentials using the installed connector-check prompt.

To publish a release:

1. Set `KIT_VERSION` in `install.sh`, the fixed-version URLs in this README, and the version
   expectations in `tests/test_installer.py` to the same tag. Update the current release link above.
2. Run the installer checks, commit the tested files, and push the commit.
3. Create and push a Git tag matching `KIT_VERSION` on that commit.
4. Publish a GitHub release for that tag and attach that commit's `install.sh` as a release
   asset named exactly `install.sh`. Mark the release as latest when it is ready for that URL.
5. Verify both download URLs before announcing the release. The asset must match the tagged
   script, whose embedded version selects the matching templates.

Use a new version for subsequent changes; keep published tags and assets fixed.
The latest-release download follows [GitHub's release asset URL format](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases).

References: [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp),
[MLflow Codex tracing](https://www.mlflow.org/docs/latest/genai/tracing/integrations/listing/codex/),
[AWS MCP proxy configuration](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md),
and [GitHub MCP server](https://github.com/github/github-mcp-server).
Skill locations and invocation follow the [Codex skills documentation](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skills documentation](https://code.claude.com/docs/en/skills).
