"""
Delete GHCR packages containing double underscores (__)
Usage: python delete_packages_with_underscores.py [--yes]
"""
import requests
import sys
import time
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

def delete_package(package_name):
    resp = requests.delete(
        f"https://api.github.com/user/packages/container/{package_name}",
        headers=HEADERS
    )
    return resp.status_code == 204

def main():
    auto_confirm = "--yes" in sys.argv or "-y" in sys.argv
    
    print("Fetching all packages...")
    packages = get_all_packages()
    
    target_packages = [p for p in packages if "__" in p["name"]]
    print(f"\nFound {len(target_packages)} packages with '__' in name:")
    for p in target_packages:
        print(f"  - {p['name']}")
    
    if not target_packages:
        print("No packages to delete.")
        return
    
    if auto_confirm:
        print("\nAuto-confirming deletion (--yes flag)")
        confirm = "yes"
    else:
        confirm = input("\nDelete all these packages? (yes/no): ")
    
    if confirm.lower() != "yes":
        print("Cancelled.")
        return
    
    for pkg in target_packages:
        name = pkg["name"]
        print(f"\nDeleting package: {name}")
        
        if delete_package(name):
            print(f"  [OK] Deleted successfully")
        else:
            print(f"  [FAIL] Failed to delete")
        
        time.sleep(0.5)
    
    print("\nDone!")

if __name__ == "__main__":
    main()