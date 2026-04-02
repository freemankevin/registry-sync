#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像清单管理器
负责加载、更新和保存镜像清单文件
"""

import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class ManifestManager:
    """镜像清单管理器"""
    
    def __init__(self, manifest_file: Path, logger=None):
        """初始化清单管理器
        
        Args:
            manifest_file: 清单文件路径
            logger: 日志记录器
        """
        self.manifest_file = manifest_file
        self.logger = logger
        self.manifest = None
        self._last_mtime = None
        self._load_manifest()
    
    def _get_file_mtime(self) -> float:
        """获取文件最后修改时间"""
        try:
            return self.manifest_file.stat().st_mtime
        except Exception:
            return 0
    
    def check_and_reload(self) -> bool:
        """检查文件是否变更，如有变更则重新加载
        
        Returns:
            是否重新加载了文件
        """
        current_mtime = self._get_file_mtime()
        if self._last_mtime is None:
            self._last_mtime = current_mtime
            return False
        
        if current_mtime > self._last_mtime:
            if self.logger:
                self.logger.info(f"检测到清单文件变更，重新加载: {self.manifest_file}")
            self._load_manifest()
            self._last_mtime = current_mtime
            return True
        
        return False
    
    def _load_manifest(self) -> None:
        """加载清单文件"""
        try:
            with open(self.manifest_file, 'r', encoding='utf-8') as f:
                self.manifest = yaml.safe_load(f)
            
            if self.logger:
                self.logger.debug(f"已加载清单文件: {self.manifest_file}")
        except FileNotFoundError:
            if self.logger:
                self.logger.error(f"清单文件不存在: {self.manifest_file}")
            raise
        except yaml.YAMLError as e:
            if self.logger:
                self.logger.error(f"清单文件格式错误: {str(e)}")
            raise
    
    def _save_manifest(self) -> None:
        """保存清单文件"""
        try:
            # 更新最后检查时间
            if 'config' not in self.manifest:
                self.manifest['config'] = {}
            self.manifest['config']['last_checked'] = datetime.now(timezone.utc).isoformat()
            
            with open(self.manifest_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.manifest, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            if self.logger:
                self.logger.debug(f"已保存清单文件: {self.manifest_file}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"保存清单文件失败: {str(e)}")
            raise
    
    def update_versions(self, registry_api, ghcr_api=None, dry_run: bool = False, use_concurrency: bool = True) -> int:
        """更新镜像版本
        
        Args:
            registry_api: RegistryAPI 实例（支持 Docker Hub, GCR, Quay）
            ghcr_api: GHCRRegistryAPI 实例（可选，用于查询 GHCR 镜像）
            dry_run: 预演模式，不修改文件
            use_concurrency: 是否使用并发获取版本信息
            
        Returns:
            更新的镜像数量
        """
        updated_count = 0
        
        # 收集需要检查的镜像
        images_to_check = []
        for img in self.manifest.get('images', []):
            if not img.get('enabled', True):
                continue
            
            source = img['source']
            tag_pattern = img.get('tag_pattern')
            exclude_pattern = img.get('exclude_pattern')
            
            # 提取镜像名和当前版本
            if ':' in source:
                image_name, current_version = source.rsplit(':', 1)
            else:
                image_name = source
                current_version = 'latest'
            
            # 只有当有 tag_pattern 时才需要检查
            if tag_pattern:
                # 判断镜像源类型
                registry_type = registry_api.detect_registry(image_name)
                
                images_to_check.append({
                    'img': img,
                    'image_name': image_name,
                    'current_version': current_version,
                    'tag_pattern': tag_pattern,
                    'exclude_pattern': exclude_pattern,
                    'registry_type': registry_type
                })
        
        # 分离不同类型镜像
        standard_images = [item for item in images_to_check if item['registry_type'] != 'ghcr']
        ghcr_images = [item for item in images_to_check if item['registry_type'] == 'ghcr']
        
        # 处理标准镜像（Docker Hub, GCR, Quay）
        if standard_images:
            if use_concurrency:
                images_to_query = [
                    (item['image_name'], item['tag_pattern'], item['exclude_pattern'])
                    for item in standard_images
                ]
                
                if self.logger:
                    registry_types = set(item['registry_type'] for item in standard_images)
                    self.logger.info(f"并发获取 {len(images_to_query)} 个镜像的最新版本（{', '.join(registry_types)}）...")
                
                results = registry_api.get_latest_versions_batch(images_to_query)
                version_map = {img: version for img, version in results}
                
                # 更新有新版本的镜像
                for item in standard_images:
                    latest = version_map.get(item['image_name'])
                    self._check_and_update_image(item, latest, dry_run)
                    if latest and latest != item['current_version']:
                        updated_count += 1
            else:
                for item in standard_images:
                    latest_version = registry_api.get_latest_version(
                        item['image_name'], 
                        item['tag_pattern'], 
                        item['exclude_pattern']
                    )
                    if self._check_and_update_image(item, latest_version, dry_run):
                        updated_count += 1
        
        # 处理 GHCR 镜像
        if ghcr_images:
            if not ghcr_api:
                if self.logger:
                    self.logger.warning(f"跳过 {len(ghcr_images)} 个 GHCR 镜像: 未提供 GHCR API 实例")
                print(f"\n⚠️  跳过 {len(ghcr_images)} 个 GHCR 镜像: 未提供 GHCR API 实例")
                for item in ghcr_images:
                    print(f"   ℹ️  {item['image_name']}: 需要 ghcr_api 参数")
            else:
                for item in ghcr_images:
                    # 提取 GHCR 仓库信息
                    # 格式: ghcr.io/{owner}/{repo}
                    parts = item['image_name'].replace('ghcr.io/', '').split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        # GitHub API 使用带斜杠的包名路径
                        repo = '/'.join(parts[1:])
                        
                        # 从 GHCR 获取标签
                        tags = ghcr_api.get_repository_tags(owner, repo)
                        
                        if tags:
                            # 过滤和排序标签
                            from scripts.generate_images_json import filter_tags_by_pattern, sort_tags_by_version
                            
                            filtered_tags = filter_tags_by_pattern(
                                tags,
                                tag_pattern=item['tag_pattern'],
                                exclude_pattern=item['exclude_pattern'],
                                logger=self.logger
                            )
                            sorted_tags = sort_tags_by_version(filtered_tags, self.logger)
                            
                            if sorted_tags:
                                latest_version = sorted_tags[0]['name']
                                if self._check_and_update_image(item, latest_version, dry_run):
                                    updated_count += 1
                        else:
                            print(f"   ⚠️  {item['image_name']}: 无法获取标签列表")
                    else:
                        print(f"   ⚠️  {item['image_name']}: GHCR 镜像格式不正确")
        
        # 保存清单（如果不是预演模式）
        if updated_count > 0 and not dry_run:
            self._save_manifest()
        
        return updated_count
    
    def _check_and_update_image(self, item: dict, latest_version: str, dry_run: bool) -> bool:
        """检查并更新镜像版本
        
        Args:
            item: 镜像信息
            latest_version: 最新版本
            dry_run: 预演模式
            
        Returns:
            是否更新
        """
        registry_type = item.get('registry_type', 'dockerhub')
        
        # 无法获取最新版本（可能是私有仓库或 API 限制）
        if not latest_version:
            # 只对特定 registry 显示提示
            if registry_type in ['gcr', 'quay']:
                if self.logger:
                    self.logger.debug(f"无法获取 {registry_type} 镜像版本，保持当前版本: {item['image_name']}")
            return False
        
        # 版本相同，无需更新
        if latest_version == item['current_version']:
            return False
        
        # 有新版本
        print(f"\n📦 {item['image_name']}")
        print(f"   当前版本: {item['current_version']}")
        print(f"   最新版本: {latest_version}")
        
        if not dry_run:
            # 更新版本
            item['img']['source'] = f"{item['image_name']}:{latest_version}"
            print(f"   ✅ 已更新")
        else:
            print(f"   ℹ️  预演模式：将更新")
        
        return True
    
    def get_manifest(self) -> Dict:
        """获取清单数据"""
        return self.manifest
