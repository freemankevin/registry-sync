"""
Get detailed info for a specific GHCR package
Usage: python get_package_info.py <package_name>
"""
import requests
import sys
import os
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

def get_package_info(package_name):
    resp = requests.get(
        f"https://api.github.com/user/packages/container/{package_name}",
        headers=HEADERS
    )
    
    if resp.status_code != 200:
        print(f"Error: {resp.status_code} - {resp.text}")
        return
    
    pkg = resp.json()
    print(f"Package: {pkg['name']}")
    print(f"Created: {pkg.get('created_at', 'N/A')}")
    print(f"Visibility: {pkg.get('visibility', 'N/A')}")
    
    versions_resp = requests.get(
        f"https://api.github.com/user/packages/container/{package_name}/versions",
        headers=HEADERS,
        params={"per_page": 100}
    )
    
    if versions_resp.status_code == 200:
        versions = versions_resp.json()
        print(f"\nVersions ({len(versions)}):")
        for v in versions:
            metadata = v.get("metadata", {})
            container = metadata.get("container", {})
            tags = container.get("tags", [])
            created = v.get("created_at", "N/A")
            print(f"  Version ID: {v['id']}")
            print(f"  Tags: {tags}")
            print(f"  Created: {created}")
            print()

if __name__ == "__main__":
    package_name = sys.argv[1] if len(sys.argv) > 1 else "freemankevin"
    get_package_info(package_name)