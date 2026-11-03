#!/usr/bin/env python3
"""
Astraea-ADK Universal Skill Installer
=====================================
Installs the Astraea-ADK skill for AI Coding Assistants (Antigravity, Cursor, Claude Code, Windsurf, Copilot).
Can be run locally from the repo or directly via one-line URL:

    python -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/HillarioRZA/AstraeaADK/main/install_skill.py').read())"

Supported Targets:
  1. Antigravity Global (~/.gemini/config/skills/astraea-adk & ~/.gemini/config/plugins/astraea-adk)
  2. Project Workspace (.agents/skills/astraea-adk)
  3. Cursor Rules (.cursor/rules/astraea-adk.mdc)
  4. Claude Code & Universal Agents (.claude/skills/astraea-adk & AGENTS.md)
"""

import os
import sys
import argparse
import urllib.request
import urllib.error
from pathlib import Path
import json

# Safe output encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/HillarioRZA/AstraeaADK/main"

SKILL_FILES = [
    "SKILL.md",
    "plugin.json",
    "references/api_reference.md",
    "references/architecture.md",
    "references/examples.md",
]

CURSOR_RULE_HEADER = """---
description: Astraea-ADK (v1.5.2) Multi-Agent Orchestration & MoA Runtime Framework Rules
globs: **/*
alwaysApply: false
---

"""

def get_home_dir() -> Path:
    return Path.home()

def fetch_content_local_or_remote(rel_path: str, local_base: Path = None) -> str:
    """Fetch file content from local directory if present, else download from GitHub raw."""
    if local_base:
        candidate = local_base / rel_path
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    
    url = f"{GITHUB_RAW_BASE}/skills/astraea-adk/{rel_path}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AstraeaADK-Skill-Installer"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Gagal mengunduh {url}: {e}")

def create_cursor_rule(skill_content: str, api_ref: str, examples: str) -> str:
    """Combine skill and key references into a standalone Cursor MDC rule."""
    return f"""{CURSOR_RULE_HEADER}# Astraea-ADK (`AstraeaADK`) Developer Rules

When the user asks to build, use, or debug agents using Astraea-ADK:
- Distribution: PyPI `pip install astraea-adk`
- Import package: `import AstraeaADK` (never `import LegionADK`)
- Strict role-agnostic, zero-external-DB requirement.

{skill_content}

---

## Quick API Reference
{api_ref}

---

## Production Boilerplate
{examples}
"""

def install_files_to_dir(target_dir: Path, file_contents: dict[str, str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in file_contents.items():
        if rel_path == "plugin.json":
            dest = target_dir / "plugin.json"
        else:
            dest = target_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

def install_antigravity_plugin(plugin_dir: Path, file_contents: dict[str, str]) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    # Write plugin.json
    if "plugin.json" in file_contents:
        (plugin_dir / "plugin.json").write_text(file_contents["plugin.json"], encoding="utf-8")
    
    # Write skills under skills/astraea-adk/
    sub_skill_dir = plugin_dir / "skills" / "astraea-adk"
    sub_skill_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in file_contents.items():
        if rel_path == "plugin.json":
            continue
        dest = sub_skill_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(
        description="Astraea-ADK Universal Skill Installer for AI Coding Assistants"
    )
    parser.add_argument(
        "--global", "-g",
        dest="install_global",
        action="store_true",
        help="Install globally to ~/.gemini/config/skills and plugins"
    )
    parser.add_argument(
        "--workspace", "-w",
        nargs="?",
        const=".",
        default=None,
        help="Install to workspace directory (default: current directory if flag present)"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Install to both Global user environment and Current Workspace"
    )
    parser.add_argument(
        "--cursor",
        action="store_true",
        help="Generate .cursor/rules/astraea-adk.mdc in target workspace"
    )
    args = parser.parse_args()

    # Determine execution context (local repository or standalone)
    script_dir = Path(__file__).resolve().parent if "__file__" in globals() else None
    local_source = None
    if script_dir:
        candidate_source = script_dir / "skills" / "astraea-adk"
        if candidate_source.is_dir() and (candidate_source / "SKILL.md").is_file():
            local_source = candidate_source

    print("=" * 60)
    print("  [*] Astraea-ADK Universal Skill Installer (v1.5.2)")
    print("=" * 60)
    if local_source:
        print(f"[>] Sumber file lokal terdeteksi: {local_source}")
    else:
        print(f"[>] Mengunduh sumber file dari GitHub: {GITHUB_RAW_BASE}")

    # Fetch all file contents
    file_contents = {}
    for rel_path in SKILL_FILES:
        try:
            content = fetch_content_local_or_remote(rel_path, local_source)
            file_contents[rel_path] = content
            print(f"  [+] Memuat {rel_path} ({len(content)} bytes)")
        except Exception as e:
            print(f"  [!] Peringatan: {e}")

    if "SKILL.md" not in file_contents:
        print("[!] Gagal memuat SKILL.md. Instalasi dibatalkan.")
        sys.exit(1)

    # Defaults: If neither --global nor --workspace is specified, install to BOTH
    do_global = args.install_global or args.all or (not args.install_global and args.workspace is None)
    workspace_path = args.workspace if (args.workspace or args.all) else ("." if not args.install_global else None)

    home = get_home_dir()

    # 1. Global Installation
    if do_global:
        print("\n[*] Memasang ke direktori Global AI Agent...")
        # A. Antigravity Global Skills
        global_skill_dir = home / ".gemini" / "config" / "skills" / "astraea-adk"
        install_files_to_dir(global_skill_dir, file_contents)
        print(f"  [OK] Antigravity Global Skill : {global_skill_dir}")

        # B. Antigravity Builtin / User Skills fallback
        gemini_app_skill_dir = home / ".gemini" / "antigravity" / "skills" / "astraea-adk"
        install_files_to_dir(gemini_app_skill_dir, file_contents)
        print(f"  [OK] Antigravity App Skill    : {gemini_app_skill_dir}")

        # C. Antigravity Global Plugin
        global_plugin_dir = home / ".gemini" / "config" / "plugins" / "astraea-adk"
        install_antigravity_plugin(global_plugin_dir, file_contents)
        print(f"  [OK] Antigravity Global Plugin: {global_plugin_dir}")

        # D. Claude Code Global Skills
        claude_global_skill_dir = home / ".claude" / "skills" / "astraea-adk"
        install_files_to_dir(claude_global_skill_dir, file_contents)
        print(f"  [OK] Claude Code Global Skill : {claude_global_skill_dir}")

    # 2. Workspace Installation
    if workspace_path:
        target_ws = Path(workspace_path).resolve()
        print(f"\n[*] Memasang ke Workspace: {target_ws}...")
        
        # A. .agents/skills/astraea-adk
        ws_agents_dir = target_ws / ".agents" / "skills" / "astraea-adk"
        install_files_to_dir(ws_agents_dir, file_contents)
        print(f"  [OK] Workspace Skill (.agents): {ws_agents_dir}")

        # B. Cursor MDC Rule (.cursor/rules/astraea-adk.mdc)
        cursor_dir = target_ws / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        cursor_mdc_path = cursor_dir / "astraea-adk.mdc"
        cursor_rule_content = create_cursor_rule(
            file_contents.get("SKILL.md", ""),
            file_contents.get("references/api_reference.md", ""),
            file_contents.get("references/examples.md", "")
        )
        cursor_mdc_path.write_text(cursor_rule_content, encoding="utf-8")
        print(f"  [OK] Cursor IDE Rule (.cursor): {cursor_mdc_path}")

        # C. Claude Code Workspace (.claude/skills/astraea-adk)
        ws_claude_dir = target_ws / ".claude" / "skills" / "astraea-adk"
        install_files_to_dir(ws_claude_dir, file_contents)
        print(f"  [OK] Claude Workspace Skill   : {ws_claude_dir}")

        # D. Standalone guide for general agents (AGENTS.md)
        agents_md_path = target_ws / "AGENTS.md"
        if not agents_md_path.exists():
            agents_md_path.write_text(cursor_rule_content, encoding="utf-8")
            print(f"  [OK] Universal Agent Guide   : {agents_md_path}")
        else:
            standalone_path = target_ws / "astraea-adk-guide.md"
            standalone_path.write_text(cursor_rule_content, encoding="utf-8")
            print(f"  [OK] Standalone Guide         : {standalone_path}")

    print("\n" + "=" * 60)
    print("  [SUCCESS] Astraea-ADK Skill berhasil terpasang sempurna!")
    print("  AI Agent sekarang dapat langsung memahami API, arsitektur,")
    print("  dan pola orkestrasi AstraeaADK v1.5.2 di proyek ini / global.")
    print("=" * 60)

if __name__ == "__main__":
    main()
