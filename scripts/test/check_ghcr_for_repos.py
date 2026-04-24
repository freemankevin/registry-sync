"""
Check which repo images actually exist in GHCR
Compare with manifest and add missing ones
"""
import requests
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.utils import load_env_files, get_env_variable

load_env_files(project_root)

TOKEN = get_env_variable('GHCR_TOKEN', required=True)
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_all_packages():
    packages = []
    page = 1
    while True:
        resp = requests.get(
            "https://api.github.com/user/packages",
            headers=HEADERS,
            params={"package_type": "container", "per_page": 100, "page": page}
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        packages.extend(data)
        page += 1
    return packages

def get_package_versions(package_name):
    versions = []
    page = 1
    while True:
        resp = requests.get(
            f"https://api.github.com/user/packages/container/{package_name}/versions",
            headers=HEADERS,
            params={"per_page": 100, "page": page}
        )
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        versions.extend(data)
        page += 1
    return versions

REPOS_WITH_DOCKER = [
    "dao-de-jing",
    "DockerPull",
    "freemankevin.github.io",  # -> freemankevin
    "harbor-export",
    "harbor-export-ui",
    "java-local",
    "loadstrike",
    "Netkit",  # -> netkit
    "postgresql-backup",  # -> freelabspace/postgresql-backup
    "postgresql-postgis",  # -> freelabspace/postgresql-postgis
    "python-local",
    "python3.10",
]

def main():
    print("Fetching all GHCR packages...")
    packages = get_all_packages()
    ghcr_names = {p["name"] for p in packages}
    
    print(f"\nGHCR packages ({len(ghcr_names)}):")
    for n in sorted(ghcr_names):
        print(f"  - {n}")
    
    print("\n" + "="*60)
    print("Checking repo images in GHCR:")
    print("="*60 + "\n")
    
    found_repos = []
    missing_repos = []
    
    for repo in REPOS_WITH_DOCKER:
        # Map repo names to possible GHCR names
        possible_names = [
            repo.lower(),
            repo,
            repo.replace("-", ""),
            repo.replace(".", ""),
        ]
        
        # Special mappings
        if repo == "freemankevin.github.io":
            possible_names = ["freemankevin"]
        elif repo == "Netkit":
            possible_names = ["netkit", "Netkit"]
        elif repo == "postgresql-backup":
            possible_names = ["freelabspace/postgresql-backup", "postgresql-backup"]
        elif repo == "postgresql-postgis":
            possible_names = ["freelabspace/postgresql-postgis", "postgresql-postgis"]
        
        matched = None
        for pn in possible_names:
            if pn in ghcr_names:
                matched = pn
                break
        
        if matched:
            versions = get_package_versions(matched)
            tags = []
            for v in versions:
                tags.extend(v.get("metadata", {}).get("container", {}).get("tags", []))
            tags = list(set(tags))
            latest = "latest" if "latest" in tags else (tags[0] if tags else "unknown")
            
            found_repos.append({
                "repo": repo,
                "ghcr_name": matched,
                "tags": tags,
                "latest": latest
            })
            print(f"[FOUND] {repo} -> ghcr.io/freemankevin/{matched}:{latest}")
            print(f"        Tags: {tags}")
        else:
            missing_repos.append(repo)
            print(f"[MISSING] {repo} -> Not in GHCR")
    
    print("\n" + "="*60)
    print("YAML entries for repo images NOT in manifest:")
    print("="*60 + "\n")
    
    # Already in manifest: netkit, freelabspace/postgresql-backup, freelabspace/postgresql-postgis, freemankevin
    already_in_manifest = ["netkit", "freelabspace/postgresql-backup", "freelabspace/postgresql-postgis", "freemankevin"]
    
    for r in found_repos:
        if r["ghcr_name"] not in already_in_manifest:
            print(f"- source: ghcr.io/freemankevin/{r['ghcr_name']}:{r['latest']}")
            print(f"  enabled: true")
            print(f"  description: {r['repo']} project container")
            print(f"  tag_pattern: ^latest$|^[0-9]+\\.[0-9]+")
            print(f"  sync_all_matching: false")
            print()

if __name__ == "__main__":
    main()