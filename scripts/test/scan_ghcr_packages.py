"""
Scan GHCR packages and compare with images-manifest.yml
Finds packages that exist in GHCR but not tracked in manifest
"""
import requests
import json
import yaml
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.utils import load_env_files, get_env_variable

# Load environment variables
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
            print(f"Error: {resp.status_code} - {resp.text}")
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

def load_manifest():
    with open("images-manifest.yml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    print("Fetching all GHCR packages...")
    packages = get_all_packages()
    print(f"Found {len(packages)} packages in GHCR\n")
    
    print("Packages in GHCR:")
    for p in packages:
        print(f"  - {p['name']}")
    
    manifest = load_manifest()
    manifest_sources = set()
    for img in manifest.get("images", []):
        source = img.get("source", "")
        if source.startswith("ghcr.io/freemankevin/"):
            name = source.replace("ghcr.io/freemankevin/", "").split(":")[0]
            manifest_sources.add(name)
        elif "/" in source:
            parts = source.split(":")[0]
            if parts.startswith("library/"):
                manifest_sources.add(parts)
            else:
                manifest_sources.add(parts)
    
    ghcr_packages = {p["name"] for p in packages}
    
    missing_in_manifest = ghcr_packages - manifest_sources
    
    print(f"\nPackages in GHCR but NOT in images-manifest.yml:")
    if missing_in_manifest:
        for name in sorted(missing_in_manifest):
            print(f"  - {name}")
    else:
        print("  (None)")
    
    print("\n" + "="*60)
    print("Generating YAML entries for missing packages...")
    print("="*60 + "\n")
    
    for pkg in packages:
        if pkg["name"] in missing_in_manifest:
            versions = get_package_versions(pkg["name"])
            tags = []
            for v in versions:
                metadata = v.get("metadata", {})
                container_tags = metadata.get("container", {}).get("tags", [])
                tags.extend(container_tags)
            
            tags = list(set(tags))
            latest_tag = "latest" if "latest" in tags else (tags[0] if tags else "unknown")
            
            print(f"- source: ghcr.io/freemankevin/{pkg['name']}:{latest_tag}")
            print(f"  enabled: true")
            print(f"  description: Package from your repository")
            print(f"  tag_pattern: ^latest$|^[0-9]+\\.[0-9]+")
            print(f"  sync_all_matching: false")

if __name__ == "__main__":
    main()