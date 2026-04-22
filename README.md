# Registry Sync

Docker 镜像同步工具，支持将多源镜像同步到 GitHub Container Registry (GHCR)。

## 前端启动

```bash
chmod +x startup.sh
./startup.sh
```

访问 http://localhost:7886

## 支持的镜像源

- Docker Hub
- GitHub Container Registry (GHCR)
- Google Container Registry (GCR)
- Red Hat Quay
- AWS ECR Public (public.ecr.aws)

## 核心功能

```bash
python scripts/main.py update    # 更新镜像清单版本
python scripts/main.py sync      # 同步镜像到 GHCR
python scripts/main.py run       # 完整流程（更新+同步）
python scripts/main.py generate  # 生成 images.json
```
