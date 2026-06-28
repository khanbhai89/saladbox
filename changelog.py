#!/usr/bin/env python3
import sys
import os
import subprocess
from datetime import datetime

CHANGELOG_FILE = "CHANGELOG.md"

def run_cmd(cmd):
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def initialize_changelog():
    """Create a default CHANGELOG.md if it doesn't exist."""
    if not os.path.exists(CHANGELOG_FILE):
        print(f"Creating new {CHANGELOG_FILE}...")
        with open(CHANGELOG_FILE, "w") as f:
            f.write("# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n## [Unreleased]\n")

def main():
    initialize_changelog()
    
    # Check for modified/untracked files
    status = run_cmd("git status --porcelain")
    if not status:
        print("No changes detected in the repository.")
        sys.exit(0)
        
    print("Detected changed files:")
    print(status)
    
    # Prompt for changelog entry
    print("\nEnter your changelog description (e.g. 'Fix broken logo link in README'):")
    entry = input("> ").strip()
    if not entry:
        print("Empty entry. Aborted.")
        sys.exit(0)
        
    # Read existing changelog
    with open(CHANGELOG_FILE, "r") as f:
        lines = f.readlines()
        
    # Find the "[Unreleased]" line
    unreleased_idx = -1
    for i, line in enumerate(lines):
        if "## [Unreleased]" in line:
            unreleased_idx = i
            break
            
    if unreleased_idx == -1:
        # If [Unreleased] section isn't found, append to the end
        lines.append(f"\n## [Unreleased]\n- {entry} ({datetime.now().strftime('%Y-%m-%d')})\n")
    else:
        # Insert the entry right below "## [Unreleased]" header
        lines.insert(unreleased_idx + 1, f"- {entry} ({datetime.now().strftime('%Y-%m-%d')})\n")
        
    # Write back to CHANGELOG.md
    with open(CHANGELOG_FILE, "w") as f:
        f.writelines(lines)
        
    print(f"\nSuccessfully added entry to {CHANGELOG_FILE}:")
    print(f"- {entry}")
    
    # Automatically stage, commit, and push
    print("\n--- Automatically Committing & Pushing Changes ---")
    run_cmd(f"git add .")
    commit_res = subprocess.run(f'git commit -m "{entry}"', shell=True, capture_output=True, text=True)
    print(commit_res.stdout.strip())
    if commit_res.returncode == 0:
        print("Pushing to GitHub...")
        push_res = subprocess.run("git push origin main", shell=True, capture_output=True, text=True)
        if push_res.returncode == 0:
            print("Successfully pushed to GitHub!")
        else:
            print(f"Failed to push to GitHub:\n{push_res.stderr.strip()}")
    else:
        print(f"Failed to commit:\n{commit_res.stderr.strip()}")

if __name__ == "__main__":
    main()
