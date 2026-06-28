#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys


def run_cmd(cmd, cwd=None, capture=False, check=True):
    """Run a shell command and return status/output."""
    print(f"Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=capture, text=True)
    if result.returncode != 0 and check:
        print(f"Error executing command: {cmd}")
        if capture:
            print(f"Stdout:\n{result.stdout}\nStderr:\n{result.stderr}")
        sys.exit(result.returncode)
    return result.stdout.strip() if capture else None

def get_current_version():
    """Extract version from pyproject.toml."""
    with open("pyproject.toml") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if not match:
        print("Error: Could not find version in pyproject.toml")
        sys.exit(1)
    return match.group(1)

def bump_version(current, bump_type):
    """Calculate the bumped version string."""
    parts = list(map(int, current.split('.')))
    if bump_type == 'patch':
        parts[2] += 1
    elif bump_type == 'minor':
        parts[1] += 1
        parts[2] = 0
    elif bump_type == 'major':
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    return ".".join(map(str, parts))

def update_version_in_files(new_version):
    """Update version in all project config files."""
    # 1. pyproject.toml
    print("Updating pyproject.toml...")
    with open("pyproject.toml") as f:
        content = f.read()
    new_content = re.sub(
        r'^(version\s*=\s*["\'])([^"\']+)(["\'])',
        rf'\g<1>{new_version}\g<3>',
        content,
        flags=re.MULTILINE
    )
    with open("pyproject.toml", "w") as f:
        f.write(new_content)

    # 2. saladbox/__init__.py
    print("Updating saladbox/__init__.py...")
    init_path = "saladbox/__init__.py"
    if os.path.exists(init_path):
        with open(init_path) as f:
            content = f.read()
        new_content = re.sub(
            r'^(__version__\s*=\s*["\'])([^"\']+)(["\'])',
            rf'\g<1>{new_version}\g<3>',
            content,
            flags=re.MULTILINE
        )
        with open(init_path, "w") as f:
            f.write(new_content)

    # 3. electron/package.json
    print("Updating electron/package.json...")
    electron_pkg = "electron/package.json"
    if os.path.exists(electron_pkg):
        with open(electron_pkg) as f:
            data = json.load(f)
        data["version"] = new_version
        with open(electron_pkg, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

def get_changelog():
    """Generate automatic log messages since last tag or prompt user."""
    print("\n--- Generating Changelog ---")
    last_tag = run_cmd("git describe --tags --abbrev=0", capture=True, check=False)
    if last_tag:
        print(f"Commits since last tag ({last_tag}):")
        log_cmd = f"git log {last_tag}..HEAD --oneline"
    else:
        print("No previous tags found. Commits:")
        log_cmd = "git log --oneline"

    commits = run_cmd(log_cmd, capture=True)
    print(commits if commits else "No new commits.")

    print("\nEnter release notes / changelog details (Press Ctrl+D or type EOF on a new line when finished):")
    notes = []
    while True:
        try:
            line = input()
            if line.strip() == "EOF":
                break
            notes.append(line)
        except EOFError:
            break
    return "\n".join(notes) if notes else "Maintenance release."

def main():
    # Make sure we're in clean git state
    status = run_cmd("git status --porcelain", capture=True)
    if status:
        print("Warning: You have uncommitted changes in your workspace:")
        print(status)
        confirm = input("Do you want to proceed anyway? (y/N): ")
        if confirm.lower() != 'y':
            sys.exit(1)

    current = get_current_version()
    print(f"Current version: {current}")

    bump = input("Select bump type [patch/minor/major/custom] (default: patch): ").strip().lower()
    if not bump:
        bump = 'patch'

    if bump in ['patch', 'minor', 'major']:
        new_version = bump_version(current, bump)
    elif bump == 'custom':
        new_version = input("Enter custom version (e.g. 0.4.0): ").strip()
    else:
        new_version = bump

    print(f"Target Release Version: {new_version}")
    confirm = input("Confirm update version? (y/N): ")
    if confirm.lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    # Update files
    update_version_in_files(new_version)

    # Get changelog
    notes = get_changelog()

    # Git stage & commit
    print("\n--- Git Commit & Tag ---")
    run_cmd("git add pyproject.toml saladbox/__init__.py electron/package.json")
    run_cmd(f'git commit -m "chore(release): v{new_version}"')
    run_cmd(f'git tag -a v{new_version} -m "Release v{new_version}\n\n{notes}"')

    # Push to origin
    push = input("\nPush commits and tags to GitHub? (y/N): ")
    if push.lower() == 'y':
        run_cmd("git push origin main")
        run_cmd(f"git push origin v{new_version}")

        # Build Electron & Upload Release
        build_electron = input("\nDo you want to build and release the Electron app? (y/N): ")
        if build_electron.lower() == 'y':
            print("\n--- Building Electron App ---")
            run_cmd("npm run build", cwd="electron")

            print("\n--- Creating GitHub Release & Uploading Artifacts ---")
            # Find generated files in electron/dist
            assets = []
            dist_dir = "electron/dist"
            if os.path.exists(dist_dir):
                for f in os.listdir(dist_dir):
                    if f.endswith(f"-{new_version}-arm64.dmg") or f.endswith(f"-{new_version}-arm64-mac.zip") or f.endswith(f"-{new_version}-mac.zip"):
                        assets.append(os.path.join(dist_dir, f))

            asset_args = " ".join([f'"{a}"' for a in assets])
            if asset_args:
                release_cmd = f'gh release create v{new_version} {asset_args} --title "v{new_version}" --notes "{notes}"'
                run_cmd(release_cmd)
                print(f"\nRelease v{new_version} successfully published to GitHub!")
            else:
                print("No matching Electron artifacts found to upload.")

    print("\nDone!")

if __name__ == "__main__":
    main()
