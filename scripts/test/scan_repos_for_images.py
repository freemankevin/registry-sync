"""
Scan all GitHub repositories for Docker-related files
Finds projects that build/publish Docker images
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

def get_all_repos():
    repos = []
    page = 1
    while True:
        resp = requests.get(
            "https://api.github.com/user/repos",
            headers=HEADERS,
            params={"per_page": 100, "page": page, "type": "owner"}
        )
        if resp.status_code != 200:
            print(f"Error: {resp.status_code}")
            break
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def check_file_exists(repo_name, file_path):
    resp = requests.get(
        f"https://api.github.com/repos/freemankevin/{repo_name}/contents/{file_path}",
        headers=HEADERS
    )
    return resp.status_code == 200

def get_workflow_files(repo_name):
    files = []
    resp = requests.get(
        f"https://api.github.com/repos/freemankevin/{repo_name}/contents/.github/workflows",
        headers=HEADERS
    )
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list):
            files = [f["name"] for f in data if f["name"].endswith(".yml") or f["name"].endswith(".yaml")]
    return files

def check_workflow_for_docker(repo_name, workflow_file):
    resp = requests.get(
        f"https://api.github.com/repos/freemankevin/{repo_name}/contents/.github/workflows/{workflow_file}",
        headers=HEADERS
    )
    if resp.status_code == 200:
        content = resp.json()
        if "content" in content:
            import base64
            decoded = base64.b64decode(content["content"]).decode("utf-8", errors="ignore")
            docker_keywords = ["docker build", "docker push", "ghcr.io", "docker/login-action", "docker/build-push-action"]
            return any(kw in decoded.lower() for kw in docker_keywords)
    return False

def main():
    print("Fetching all repositories...")
    repos = get_all_repos()
    print(f"Found {len(repos)} repositories\n")
    
    docker_repos = []
    
    for repo in repos:
        name = repo["name"]
        print(f"Checking: {name}")
        
        has_dockerfile = check_file_exists(name, "Dockerfile")
        has_compose = check_file_exists(name, "docker-compose.yml") or check_file_exists(name, "docker-compose.yaml")
        
        workflows = get_workflow_files(name)
        docker_workflows = []
        for wf in workflows:
            if check_workflow_for_docker(name, wf):
                docker_workflows.append(wf)
        
        if has_dockerfile or docker_workflows:
            docker_repos.append({
                "name": name,
                "dockerfile": has_dockerfile,
                "compose": has_compose,
                "workflows": docker_workflows,
                "url": repo["html_url"]
            })
            print(f"  [FOUND] Dockerfile: {has_dockerfile}, Workflows: {docker_workflows}")
        else:
            print(f"  [SKIP] No Docker-related files")
    
    print("\n" + "="*60)
    print("Repositories with Docker support:")
    print("="*60)
    
    for r in docker_repos:
        print(f"\n{r['name']}")
        print(f"  URL: {r['url']}")
        print(f"  Dockerfile: {r['dockerfile']}")
        print(f"  Docker Compose: {r['compose']}")
        print(f"  Docker Workflows: {r['workflows']}")
        
        possible_image = f"ghcr.io/freemankevin/{r['name']}"
        print(f"  Likely image: {possible_image}")

if __name__ == "__main__":
    main()