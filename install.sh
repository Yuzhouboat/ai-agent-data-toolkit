#!/usr/bin/env bash
# Install local Claude Code and Codex integrations (both by default).
# Works from a clone or through bash <(curl -fsSL .../install.sh).
set -euo pipefail

# Keep this release tag fixed: remote templates must match the installer.
KIT_VERSION="v1.0.0"
USAGE="Usage: install.sh [--claude | --codex] [--uninstall] [project-dir]"
mode=local
agent=both
project_arg=""
while [ $# -gt 0 ]; do
    case "$1" in
        --claude|--codex)
            [ "$agent" = both ] || { echo "Choose only one of --claude or --codex." >&2; exit 1; }
            agent="${1#--}" ;;
        --uninstall) mode=uninstall ;;
        -h|--help)
            echo "$USAGE"
            echo "AI data kit $KIT_VERSION"
            echo "  (default)    install local-only Claude Code and Codex configuration"
            echo "  --claude     only configure Claude Code"
            echo "  --codex      only configure Codex"
            echo "  --uninstall  remove recorded installs for the selected agent(s)"
            echo "project-dir defaults to the Git repo root, else the current directory."
            exit 0 ;;
        -*) echo "Unknown option: $1 ($USAGE)" >&2; exit 1 ;;
        *)
            [ -z "$project_arg" ] || { echo "$USAGE" >&2; exit 1; }
            project_arg="$1" ;;
    esac
    shift
done
PROJECT="${project_arg:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PROJECT="$(cd "$PROJECT" && pwd -P)"
command -v python3 >/dev/null 2>&1 || { echo "python3 is required." >&2; exit 1; }
if [ "$agent" != claude ]; then
    python3 -c 'import tomllib' 2>/dev/null || { echo "Python 3.11+ is required for Codex configuration." >&2; exit 1; }
fi

RAW_BASE="https://raw.githubusercontent.com/Yuzhouboat/ai-agent-data-toolkit/$KIT_VERSION"
KIT_FILES=(skills/check-connectors/SKILL.md)
if [ "$agent" != codex ]; then
    KIT_FILES+=(claude/settings.json claude/hooks/install-plugins.py .mcp.json)
fi
if [ "$agent" != claude ]; then
    KIT_FILES+=(codex/config.toml codex/mlflow-tracing.json)
fi
SRC="$(mktemp -d)"
trap 'rm -rf "$SRC"' EXIT
if [ "$mode" != uninstall ]; then
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P || true)"
    if [ -n "$HERE" ] && [ "$HERE" = "$PROJECT" ]; then
        echo "$PROJECT is the kit itself — pass the project to install into." >&2
        exit 1
    fi
    for f in "${KIT_FILES[@]}"; do
        mkdir -p "$SRC/$(dirname "$f")"
        if [ -n "$HERE" ] && [ -f "$HERE/$f" ]; then
            cp "$HERE/$f" "$SRC/$f"
        else
            curl -fsSL "$RAW_BASE/$f" -o "$SRC/$f"
        fi
    done
fi

run_claude() {
python3 - "$SRC" "$PROJECT" "$mode" "$KIT_VERSION" <<'PY'
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

src, project, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
version = sys.argv[4]
MANIFEST = ".claude/ai-kit.json"
HOOK = ".claude/hooks/install-plugins.py"
SKILL = ".claude/skills/check-connectors/SKILL.md"
IGNORES = [".claude/settings.local.json", ".playwright-mcp/"]
HEADERS = {
    "gitignore": "# AI agent settings",
    "exclude": "# AI agent settings, installed locally (not part of this repo)",
}
MISSING = object()


# --- git ---------------------------------------------------------------------
def git(*args):
    try:
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)
    except FileNotFoundError:  # no git on this machine: treat as "not a repo"
        return subprocess.CompletedProcess(args, 1, "", "")


in_git = git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
# project-dir may be a subfolder of the repo; exclude patterns are repo-relative.
prefix = git("rev-parse", "--show-prefix").stdout.strip() if in_git else ""


def tracked(rel):
    return in_git and git("ls-files", "--error-unmatch", "--", rel).returncode == 0


def ignore_file(kind):
    if kind == "gitignore":
        return project / ".gitignore"
    return Path(git("rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())


# --- helpers -------------------------------------------------------------------
def load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError as e:
        sys.exit(f"{path} isn't valid JSON ({e}) — fix it and re-run.")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commands(entry):
    return {h.get("command") for h in entry.get("hooks", [])} if isinstance(entry, dict) else set()


def dotted(path):
    return ".".join(path)


def node(data, path):
    for k in path:
        if not isinstance(data, dict) or k not in data:
            return MISSING
        data = data[k]
    return data


def claude(*args):
    if not shutil.which("claude"):
        return False
    return subprocess.run(["claude", *args], cwd=project, capture_output=True, text=True).returncode == 0


# --- install -------------------------------------------------------------------
def merge(dst, new, rec, changed, path=()):
    """Deep-merge new into dst, recording in rec how to undo it. Lists are
    unioned; a hook group replaces any existing group running the same
    command, so re-installs don't duplicate it."""
    for k, v in new.items():
        p = [*path, k]
        cur = dst.get(k, MISSING)
        if isinstance(v, (dict, list)) and cur is MISSING:
            dst[k] = cur = type(v)()
            if p not in rec["containers"]:
                rec["containers"].append(p)
        if isinstance(v, dict) and isinstance(cur, dict):
            merge(cur, v, rec, changed, p)
            continue
        if isinstance(v, list) and isinstance(cur, list):
            for item in v:
                if item in cur:
                    continue
                cmds = commands(item)
                for old in [c for c in cur if cmds and commands(c) & cmds]:
                    cur.remove(old)
                    if [p, old] in rec["items"]:
                        rec["items"].remove([p, old])
                    else:
                        rec["removed"].append([p, old])
                cur.append(item)
                rec["items"].append([p, item])
            continue
        key = json.dumps(p)
        if key not in rec["keys"]:
            rec["keys"][key] = {"absent": True} if cur is MISSING else {"orig": cur}
        rec["keys"][key]["set"] = v
        if cur is not MISSING and cur != v:
            changed.append(dotted(p))
        dst[k] = v


def merge_json(rel, new):
    path = project / rel
    rec = manifest["json"].setdefault(
        rel, {"created": not path.exists(), "keys": {}, "containers": [], "items": [], "removed": []})
    if path.exists():
        rec.setdefault("text", path.read_text())  # to restore it byte for byte
    data = load(path)
    changed = []
    merge(data, new, rec, changed)
    save(path, data)
    print(f"  merged   {rel}")
    for key in changed:
        print(f"           (overwrote {key})")


def copy(rel, source):
    dst = project / rel
    rec = manifest["copied"].setdefault(rel, {})
    if "orig" not in rec and "created" not in rec:
        if dst.exists():
            rec["orig"] = dst.read_text()
        else:
            rec["created"] = True
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / source, dst)
    rec["sha"] = sha(dst)
    print(f"  copied   {rel}")


def note_dirs(*rels):
    for rel in rels:
        if not (project / rel).exists() and rel not in manifest["dirs"]:
            manifest["dirs"].append(rel)


def add_lines(kind, lines):
    path = ignore_file(kind)
    rec = manifest["lines"].setdefault(kind, {"created": not path.exists(), "lines": []})
    existing = path.read_text().splitlines() if path.exists() else []
    todo = [line for line in lines if line not in existing]
    if not todo:
        return
    header = HEADERS[kind]
    if header not in existing:
        todo.insert(0, header)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        if existing and existing[-1].strip():
            f.write("\n")
        f.write("".join(f"{line}\n" for line in todo))
    rec["lines"] += [line for line in todo if line not in rec["lines"]]
    print(f"  added to {path}: {' '.join(line for line in todo if line != header)}")


def install():
    installed = manifest.get("mode")
    if installed and installed != mode:
        sys.exit("Older shared Claude install detected — run install.sh --claude --uninstall, then reinstall locally.")
    manifest["mode"] = mode
    manifest["version"] = version
    print(f"Installing local AI settings {version} into {project}")
    if not in_git:
        print("(not a git repo — no Git exclusions needed)")
    print()

    settings_rel = ".claude/settings.local.json"
    if tracked(settings_rel):
        sys.exit(f"This repo tracks {settings_rel}, so a local install can't use it.")
    if tracked(HOOK) and (project / HOOK).read_bytes() != (src / "claude/hooks/install-plugins.py").read_bytes():
        sys.exit(f"This repo already tracks a different {HOOK}; a local install would clash with it.")
    for rel in (".claude", ".claude/skills", ".claude/skills/check-connectors", SKILL):
        if (project / rel).is_symlink():
            sys.exit(f"Refusing to modify symlinked Claude skill path: {project / rel}")
    skill = project / SKILL
    skill_text = (src / "skills/check-connectors/SKILL.md").read_text()
    owned = manifest["copied"].get(SKILL)
    if owned and skill.exists() and sha(skill) != owned["sha"]:
        sys.exit(f"{SKILL} was edited since install; restore it before updating (uninstall preserves it).")
    if skill.exists() and (tracked(SKILL) or not owned) and skill.read_text() != skill_text:
        sys.exit(f"Existing {SKILL} differs; move it aside before installing.")

    note_dirs(".claude", ".claude/hooks", ".claude/skills", ".claude/skills/check-connectors")
    settings = load(src / "claude/settings.json")
    servers = load(src / ".mcp.json").get("mcpServers", {})
    merge_json(settings_rel, settings)
    if not tracked(HOOK):
        copy(HOOK, "claude/hooks/install-plugins.py")
    if not tracked(SKILL):
        copy(SKILL, "skills/check-connectors/SKILL.md")

    if tracked(".mcp.json"):
        # The repo's own .mcp.json can't change without showing in git status,
        # so register the servers in this clone's local scope (~/.claude.json).
        for name, cfg in servers.items():
            # Only replace registrations this kit owns; preserve existing local servers.
            if name in manifest["mcp_local"]:
                claude("mcp", "remove", "--scope", "local", name)
            if claude("mcp", "add-json", "--scope", "local", name, json.dumps(cfg)):
                if name not in manifest["mcp_local"]:
                    manifest["mcp_local"].append(name)
                print(f"  added MCP server '{name}' at local scope (repo tracks its own .mcp.json)")
            else:
                print(f"  !! couldn't add MCP server '{name}'; run in {project}:\n"
                      f"     claude mcp add-json --scope local {name} '{json.dumps(cfg)}'")
    else:
        merge_json(".mcp.json", {"mcpServers": servers})

    save(project / MANIFEST, manifest)
    if in_git:
        written = [settings_rel, MANIFEST, *manifest["copied"], *manifest["json"]]
        hidden = dict.fromkeys(["/" + prefix + p for p in [*IGNORES, *written]])
        add_lines("exclude", list(hidden))
    save(project / MANIFEST, manifest)  # again, now with the ignore lines

    print()
    print("Local install done" + (" — nothing to commit; git status stays clean." if in_git else "."))
    print()
    print("Next: set the credentials listed in the kit's README (MySQL, AWS, GitHub, MLflow),")
    print(f"then run `claude` in {project} — the SessionStart hook installs the plugins;")
    print("/reload-plugins loads them.")
    print("Then use /check-connectors to verify tools and authentication with read-only checks.")


# --- uninstall -----------------------------------------------------------------
def uninstall_plugins(rec, scope):
    """Uninstall the plugins the kit enabled, for this project only."""
    ours = [json.loads(k)[1] for k, r in rec["keys"].items()
            if json.loads(k)[0] == "enabledPlugins" and r.get("absent")]
    config = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    installed = load(config).get("plugins", {})
    for plugin in ours:
        here = [e for e in installed.get(plugin, [])
                if e.get("scope") == scope and Path(e.get("projectPath", "/nonexistent")).resolve() == project]
        if not here:
            continue
        if claude("plugin", "uninstall", plugin, "--scope", scope):
            print(f"  uninstalled plugin {plugin} ({scope} scope)")
        else:
            print(f"  !! couldn't uninstall plugin {plugin}; run: claude plugin uninstall {plugin} --scope {scope}")


def unmerge(rel, rec, kept):
    path = project / rel
    if not path.exists():
        return
    data = load(path)
    for key, r in rec["keys"].items():
        p = json.loads(key)
        parent = node(data, p[:-1])
        cur = parent.get(p[-1], MISSING) if isinstance(parent, dict) else MISSING
        if cur is MISSING:
            if not r.get("absent"):
                kept.append(f"{rel}: {dotted(p)} was removed since install; not restored")
            continue
        if cur != r["set"]:
            kept.append(f"{rel}: {dotted(p)} changed since install; left as is")
        elif r.get("absent"):
            del parent[p[-1]]
        else:
            parent[p[-1]] = r["orig"]
    for p, item in rec["items"]:
        lst = node(data, p)
        if isinstance(lst, list) and item in lst:
            lst.remove(item)
    for p, item in rec["removed"]:
        lst = node(data, p)
        if isinstance(lst, list) and item not in lst:
            lst.append(item)
    for p in sorted(rec["containers"], key=len, reverse=True):
        parent, c = node(data, p[:-1]), node(data, p)
        if isinstance(parent, dict) and c in ({}, []):
            del parent[p[-1]]
    if rec["created"] and data == {}:
        path.unlink()
        print(f"  removed  {rel}")
    else:
        if "text" in rec and json.loads(rec["text"]) == data:
            path.write_text(rec["text"])
        else:
            save(path, data)
        print(f"  restored {rel}")


def uncopy(rel, rec, kept):
    path = project / rel
    if not path.exists():
        return
    if sha(path) != rec["sha"]:
        kept.append(f"{rel} changed since install; left as is")
    elif "orig" in rec:
        path.write_text(rec["orig"])
        print(f"  restored {rel}")
    elif rec.get("created"):
        path.unlink()
        print(f"  removed  {rel}")


def remove_lines(kind, rec):
    path = ignore_file(kind) if in_git or kind == "gitignore" else None
    if not path or not path.exists():
        return
    lines = path.read_text().splitlines()
    for line in rec["lines"]:
        if line in lines:
            lines.remove(line)
    while lines and not lines[-1].strip():
        lines.pop()
    if rec["created"] and not lines:
        path.unlink()
        print(f"  removed  {path}")
    else:
        path.write_text("".join(f"{line}\n" for line in lines))
        print(f"  cleaned  {path}")


def uninstall():
    if not (project / MANIFEST).exists():
        sys.exit(f"No {MANIFEST} in {project} — nothing recorded to uninstall.")
    print(f"Uninstalling AI settings ({manifest['mode']} mode) from {project}\n")
    kept = []
    scope = "project" if manifest["mode"] == "shared" else "local"
    for rel, rec in manifest["json"].items():
        if rel.startswith(".claude/settings"):
            uninstall_plugins(rec, scope)
    for name in manifest["mcp_local"]:
        if claude("mcp", "remove", "--scope", "local", name):
            print(f"  removed MCP server '{name}' (local scope)")
    for rel, rec in manifest["json"].items():
        unmerge(rel, rec, kept)
    for rel, rec in manifest["copied"].items():
        uncopy(rel, rec, kept)
    for kind, rec in manifest["lines"].items():
        remove_lines(kind, rec)
    (project / MANIFEST).unlink()
    for rel in sorted(manifest["dirs"], key=len, reverse=True):
        d = project / rel
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print("\nUninstalled.")
    if kept:
        print("Left alone (edited after install — tidy up by hand if you like):")
        for line in kept:
            print(f"  - {line}")
    if manifest["mode"] == "shared" and in_git:
        print("Commit the result to take it out for everyone.")


manifest = load(project / MANIFEST) or {}
for field, empty in (("json", {}), ("copied", {}), ("dirs", []), ("lines", {}), ("mcp_local", [])):
    manifest.setdefault(field, empty)
if mode == "uninstall" and SKILL in manifest["copied"]:
    for rel in (".claude", ".claude/skills", ".claude/skills/check-connectors", SKILL):
        if (project / rel).is_symlink():
            sys.exit(f"Refusing to modify symlinked Claude skill path: {project / rel}")
uninstall() if mode == "uninstall" else install()
PY
}

run_codex() {
python3 - "$SRC/codex" "$PROJECT" "$mode" "$KIT_VERSION" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    sys.exit("Python 3.11+ is required (for TOML validation).")

src, project, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
version = sys.argv[4]
folder = project / ".codex"
config = folder / "config.toml"
tracing = folder / "mlflow-tracing.json"
record = folder / "ai-kit.json"
skill = project / ".agents/skills/check-connectors/SKILL.md"
for path in (folder, config, tracing, record):
    if path.is_symlink():
        sys.exit(f"Refusing to modify symlinked Codex path: {path}")


def read(path):
    return path.read_text() if path.exists() else ""


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 1, "", "")


def tracked(path):
    return git("ls-files", "--error-unmatch", "--", path).returncode == 0


def block(name, text):
    return f"# BEGIN AI data kit: {name}\n{text.rstrip()}\n# END AI data kit: {name}\n"


manifest = json.loads(read(record) or "{}")
if mode != "uninstall" or "skill_set" in manifest:
    for path in (project / ".agents", project / ".agents/skills", skill.parent, skill):
        if path.is_symlink():
            sys.exit(f"Refusing to modify symlinked Codex skill path: {path}")
current = read(config)
base = current
# Remove only the exact blocks we installed. Refuse changed blocks before writing.
for part in manifest.get("blocks", []):
    if base.count(part) != 1:
        sys.exit("The kit's Codex config blocks were edited or removed; restore them before updating/uninstalling.")
    base = base.replace(part, "", 1)

if mode == "uninstall":
    if not manifest:
        sys.exit("No .codex/ai-kit.json found; nothing recorded to uninstall.")
    if config.exists():
        if not base and manifest["config_created"]:
            config.unlink()
        else:
            config.write_text(base)
    if tracing.exists():
        if read(tracing) == manifest["tracing_set"]:
            if manifest["tracing_original"] is None:
                tracing.unlink()
            else:
                tracing.write_text(manifest["tracing_original"])
        else:
            print("Kept .codex/mlflow-tracing.json: edited since install.")
    if "skill_set" in manifest and skill.exists():
        if read(skill) == manifest["skill_set"]:
            if manifest["skill_original"] is None:
                skill.unlink()
            else:
                skill.write_text(manifest["skill_original"])
        else:
            print("Kept .agents/skills/check-connectors/SKILL.md: edited since install.")
    for rel in reversed(manifest.get("skill_dirs", [])):
        path = project / rel
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if manifest.get("exclude_lines"):
        exclude = Path(git("rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())
        if exclude.is_file():
            text = read(exclude)
            for line in manifest["exclude_lines"]:
                text = text.replace(line, "", 1)
            exclude.write_text(text)
    record.unlink()
    if manifest["dir_created"] and not any(folder.iterdir()):
        folder.rmdir()
    print(f"Uninstalled Codex kit from {project}.")
    sys.exit(0)

if manifest and manifest["mode"] != mode:
    sys.exit("Older shared Codex install detected — run install.sh --codex --uninstall, then reinstall locally.")
in_git = git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"
if any(tracked(f".codex/{name}") for name in ("config.toml", "mlflow-tracing.json", "ai-kit.json")):
    sys.exit("Local install cannot edit tracked .codex files. Configure Codex manually or remove the tracked configuration first.")
if tracked(".agents/skills/check-connectors/SKILL.md"):
    sys.exit("Local install cannot edit tracked .agents/skills/check-connectors/SKILL.md.")
skill_text = read(src.parent / "skills/check-connectors/SKILL.md")
if "skill_set" in manifest:
    if read(skill) != manifest["skill_set"]:
        sys.exit("Connector skill edited since install; restore it before updating (uninstall preserves it).")
elif skill.exists() and read(skill) != skill_text:
    sys.exit("Existing .agents/skills/check-connectors/SKILL.md differs; move it aside before installing.")

kit_text = read(src / "config.toml")
kit = tomllib.loads(kit_text)
existing = tomllib.loads(base)
# Keep another notifier intact instead of silently disabling it.
if "notify" in existing:
    sys.exit("Existing Codex notify hook: combine it with MLflow manually before installing this kit.")
conflicts = set(existing.get("mcp_servers", {})) & set(kit["mcp_servers"])
if conflicts:
    sys.exit("Existing Codex MCP server names conflict: " + ", ".join(sorted(conflicts)) + ". Rename/remove them before installing.")
trace_text = read(src / "mlflow-tracing.json")
json.loads(trace_text)
if not manifest and tracing.exists() and read(tracing) != trace_text:
    sys.exit("Existing .codex/mlflow-tracing.json differs; move it aside before installing.")
if manifest and read(tracing) != manifest["tracing_set"]:
    sys.exit("MLflow config edited since install; restore it before updating (uninstall preserves it).")

# The notify key must precede all TOML tables. Server tables go at the end.
root, servers = kit_text.split("[mcp_servers.", 1)
prefix = block("notify", root)
suffix = "\n" + block("servers", "[mcp_servers." + servers)
result = prefix + base + suffix
# Validate the complete file before making any changes.
tomllib.loads(result)
if not manifest:
    manifest = {
        "mode": mode,
        "config_created": not config.exists(),
        "dir_created": not folder.exists(),
        "tracing_original": read(tracing) if tracing.exists() else None,
        "exclude_lines": [],
    }
manifest.update(version=version, blocks=[prefix, suffix], tracing_set=trace_text)
manifest.setdefault("skill_original", read(skill) if skill.exists() else None)
manifest["skill_set"] = skill_text
for path in (project / ".agents", project / ".agents/skills", skill.parent):
    if not path.exists():
        manifest.setdefault("skill_dirs", []).append(str(path.relative_to(project)))
folder.mkdir(parents=True, exist_ok=True)
skill.parent.mkdir(parents=True, exist_ok=True)
skill.write_text(skill_text)
config.write_text(result)
tracing.write_text(trace_text)
if in_git:
    prefix_path = git("rev-parse", "--show-prefix").stdout.strip()
    exclude = Path(git("rev-parse", "--path-format=absolute", "--git-path", "info/exclude").stdout.strip())
    text = read(exclude)
    # A leading newline also handles exclude files with no final newline.
    lines = [f"/{prefix_path}.codex/{name}" for name in ("config.toml", "mlflow-tracing.json", "ai-kit.json")]
    lines.append(f"/{prefix_path}.agents/skills/check-connectors/SKILL.md")
    for line in lines:
        if line not in text.splitlines():
            addition = "\n" + line + "\n"
            text += addition
            manifest["exclude_lines"].append(addition)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(text)
record.write_text(json.dumps(manifest, indent=2) + "\n")
print(f"Installed local Codex kit {version} into {project}.")
print("Set MySQL, AWS, GitHub and MLflow credentials as described in the README.")
print("Then start codex, trust the project, and check /mcp. No services were contacted by this installer.")
print("Use $check-connectors to verify tools and authentication with read-only checks.")
PY
}

# Run Codex first so Codex config conflicts are detected before changing Claude files.
# Uninstall tolerates a project that only has one of the two kits installed.
if [ "$agent" != claude ]; then
    if [ "$mode" != uninstall ] || [ -f "$PROJECT/.codex/ai-kit.json" ]; then
        run_codex
    else
        echo "No recorded Codex install in $PROJECT; skipping."
    fi
fi
if [ "$agent" != codex ]; then
    if [ "$mode" != uninstall ] || [ -f "$PROJECT/.claude/ai-kit.json" ]; then
        run_claude
    else
        echo "No recorded Claude install in $PROJECT; skipping."
    fi
fi

if [ "$mode" != uninstall ]; then
    selection=""
    [ "$agent" = both ] || selection=" --$agent"
    echo "Configured agent selection: $agent."
    echo "To undo, rerun this installer$selection --uninstall \"$PROJECT\""
fi
