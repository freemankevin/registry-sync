#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像同步工具
处理 Docker 镜像的实际同步操作
"""

import json
import subprocess
import sys
import time
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import defaultdict

from scripts.utils import convert_to_ghcr_path, get_ghcr_image_name, parse_image_name


def parse_version_tag(tag: str):
    """解析版本标签，返回 (major, minor, patch)"""
    match = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', tag)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    
    match = re.match(r'^v?(\d+)\.(\d+)$', tag)
    if match:
        return (int(match.group(1)), int(match.group(2)), 0)
    
    return None


def get_major_version(tag: str):
    """获取主版本号"""
    parsed = parse_version_tag(tag)
    return parsed[0] if parsed else None


def apply_retention_strategy(
    versions: List[str],
    strategy: str,
    max_versions: int,
    major_versions: List[int] = None,
    keep_minor_versions: List[str] = None
) -> List[str]:
    """应用清理策略，返回需要保留的版本列表
    
    Args:
        versions: 所有版本列表
        strategy: 清理策略 (max_versions, latest_per_major, latest_per_minor)
        max_versions: 最大保留版本数
        major_versions: 需要保留的大版本列表
        keep_minor_versions: 需要保留的小版本系列列表
        
    Returns:
        需要保留的版本列表
    """
    if not versions:
        return []
    
    if strategy == 'latest_per_major' and major_versions:
        versions_by_major = defaultdict(list)
        
        for v in versions:
            parsed = parse_version_tag(v)
            if parsed:
                major = parsed[0]
                if major in major_versions:
                    versions_by_major[major].append({
                        'version': v,
                        'major': parsed[0],
                        'minor': parsed[1],
                        'patch': parsed[2]
                    })
        
        retained = []
        for major, v_list in versions_by_major.items():
            v_list.sort(key=lambda x: (x['minor'], x['patch']), reverse=True)
            if v_list:
                retained.append(v_list[0]['version'])
        
        return retained
    
    elif strategy == 'latest_per_minor' and keep_minor_versions:
        versions_by_minor = defaultdict(list)
        
        for v in versions:
            parsed = parse_version_tag(v)
            if parsed:
                minor_key = f"{parsed[0]}.{parsed[1]}"
                if minor_key in keep_minor_versions or not keep_minor_versions:
                    versions_by_minor[minor_key].append({
                        'version': v,
                        'patch': parsed[2]
                    })
        
        retained = []
        for minor_key, v_list in versions_by_minor.items():
            v_list.sort(key=lambda x: x['patch'], reverse=True)
            if v_list:
                retained.append(v_list[0]['version'])
        
        return retained
    
    else:
        return versions[:max_versions] if len(versions) > max_versions else versions


class MirrorSync:
    """镜像同步管理器"""

    def __init__(self, registry: str, owner: str, logger=None, max_workers: int = 3,
                 max_retries: int = 3, retry_delay: float = 2.0):
        self.registry = registry
        self.owner = owner
        self.logger = logger
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.mirrored_images = []
        self.failed_images = []  # 记录失败的镜像
        self.success_count = 0
        self.fail_count = 0
        self._lock = threading.Lock()
    
    def _get_image_digest(self, image: str) -> Optional[str]:
        """获取镜像的 digest
        
        Args:
            image: 镜像名称
            
        Returns:
            镜像的 digest，如果获取失败返回 None
        """
        try:
            cmd = ['regctl', 'image', 'digest', image]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                digest = result.stdout.strip()
                return digest
            else:
                return None
        except Exception as e:
            return None
    
    def _is_ghcr_source(self, source: str) -> bool:
        """检查源镜像是否来自 GitHub Container Registry
        
        Args:
            source: 源镜像地址
            
        Returns:
            True 表示源镜像来自 GHCR，False 表示来自其他仓库
        """
        return source.startswith('ghcr.io/')

    def needs_sync(self, source: str, target: str) -> bool:
        """检查镜像是否需要同步
        
        Args:
            source: 源镜像
            target: 目标镜像
            
        Returns:
            True 表示需要同步，False 表示可以跳过
        """
        # 获取源镜像的 digest
        source_digest = self._get_image_digest(source)
        if not source_digest:
            if self.logger:
                self.logger.warning(f"无法获取源镜像 {source} 的 digest，将强制同步")
            return True
        
        # 获取目标镜像的 digest
        target_digest = self._get_image_digest(target)
        if not target_digest:
            return True
        
        # 比较 digest
        if source_digest == target_digest:
            if self.logger:
                self.logger.info(f"镜像 {source} 已存在且 digest 相同，跳过同步")
            return False
        else:
            return True

    def mirror_image(self, source: str, target: str) -> bool:
        """镜像同步（带重试机制）"""
        if not self.needs_sync(source, target):
            return True
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    # 线性增长策略，最大不超过10秒
                    delay = min(self.retry_delay * attempt + random.uniform(0, 1), 10)
                    if self.logger:
                        self.logger.info(f"第 {attempt + 1} 次重试，等待 {delay:.2f} 秒...")
                    time.sleep(delay)

                cmd = [
                    'regctl', 'image', 'copy',
                    '--verbosity', 'warn',
                    '--force-recursive',
                    source, target
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                if result.returncode == 0:
                    return True
                else:
                    last_error = result.stderr
                    error_lower = result.stderr.lower()
                    
                    is_rate_limit = 'rate limit' in error_lower or 'toomanyrequests' in error_lower or '429' in error_lower
                    is_network_error = 'network' in error_lower or 'connection' in error_lower or 'timeout' in error_lower
                    
                    # Rate limit错误直接失败，不重试（6小时窗口限制，等待无效）
                    if is_rate_limit:
                        if self.logger:
                            self.logger.error(f"遇到 Docker Hub rate limit 限制，无法继续同步")
                            self.logger.error(f"错误详情: {result.stderr}")
                        return False
                    
                    # 其他错误重试，但限制延迟时间
                    if attempt < self.max_retries - 1:
                        if self.logger:
                            self.logger.warning(f"同步失败，重试中... ({attempt + 1}/{self.max_retries})")
                        continue
                    else:
                        if self.logger:
                            self.logger.error(f"同步失败（已重试 {self.max_retries} 次）")
                            self.logger.error(f"错误详情: {result.stderr}")
                        return False

            except subprocess.TimeoutExpired:
                last_error = f"同步超时（600秒）"
                if self.logger:
                    self.logger.warning(f"同步超时，重试中... ({attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    continue
                if self.logger:
                    self.logger.error(f"同步超时（已重试 {self.max_retries} 次）: {source}")
                return False
                
            except Exception as e:
                last_error = str(e)
                if self.logger:
                    self.logger.warning(f"同步异常，重试中... ({attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    continue
                if self.logger:
                    self.logger.error(f"同步异常（已重试 {self.max_retries} 次）: {str(e)}")
                return False

        return False
    
    def sync_single_version(
        self, 
        image_name: str, 
        version: str,
        description: str = ''
    ) -> bool:
        """同步单个版本"""
        source_image = f"{image_name}:{version}"
        
        # 检查源镜像是否来自 GHCR
        if self._is_ghcr_source(source_image):
            # GHCR 源镜像保持原样，不需要转换路径
            target_image = source_image
            repo_name = image_name.replace('ghcr.io/', '').replace('/', '__')
            
            print(f"✓ {source_image} (GHCR source, skipped)")
            
            with self._lock:
                self.mirrored_images.append({
                    'name': image_name,
                    'source': source_image,
                    'target': target_image,
                    'version': version,
                    'description': description,
                    'repository': repo_name,
                    'synced_at': datetime.now(timezone.utc).isoformat()
                })
                self.success_count += 1
            return True
        
        ghcr_path = convert_to_ghcr_path(image_name)
        repo_name = ghcr_path.replace('/', '__')
        target_image = f"{self.registry}/{self.owner}/{ghcr_path}:{version}"
        
        if self.mirror_image(source_image, target_image):
            print(f"✓ {source_image} -> {ghcr_path}:{version}")
            
            with self._lock:
                self.mirrored_images.append({
                    'name': image_name,
                    'source': source_image,
                    'target': target_image,
                    'version': version,
                    'description': description,
                    'repository': repo_name,
                    'synced_at': datetime.now(timezone.utc).isoformat()
                })
                self.success_count += 1
            return True
        else:
            print(f"✗ {source_image} (failed)")
            
            with self._lock:
                self.fail_count += 1
                self.failed_images.append({
                    'name': image_name,
                    'source': source_image,
                    'target': target_image,
                    'version': version,
                    'description': description
                })
            return False
    
    def sync_from_manifest(
        self,
        manifest: Dict,
        api,
        output_file: Optional[Path] = None,
        use_concurrency: bool = True
    ) -> Dict:
        """从清单同步所有镜像

        Args:
            manifest: 镜像清单
            api: DockerHubAPI 实例
            output_file: 输出文件路径
            use_concurrency: 是否使用并发同步

        Returns:
            同步结果字典
        """
        # 收集所有需要同步的任务
        sync_tasks = []

        for img in manifest.get('images', []):
            if not img.get('enabled', True):
                continue

            source = img['source']
            description = img.get('description', '')
            tag_pattern = img.get('tag_pattern')
            exclude_pattern = img.get('exclude_pattern')
            sync_all = img.get('sync_all_matching', False)
            
            retention = img.get('retention', {})
            global_retention = manifest.get('config', {}).get('retention', {})
            
            strategy = retention.get('strategy', global_retention.get('strategy', 'max_versions'))
            max_versions = retention.get('max_versions', global_retention.get('max_versions', 3))
            major_versions = retention.get('major_versions', [])
            keep_minor_versions = retention.get('keep_minor_versions', [])

            image_name = source.split(':')[0]

            versions_to_sync = []

            if sync_all:
                all_versions = api.get_all_matching_versions(
                    source, tag_pattern, exclude_pattern
                )

                if all_versions:
                    if self.logger:
                        self.logger.info(f"找到 {len(all_versions)} 个匹配版本，应用清理策略...")
                    
                    retained_versions = apply_retention_strategy(
                        all_versions,
                        strategy,
                        max_versions,
                        major_versions,
                        keep_minor_versions
                    )
                    
                    if self.logger:
                        self.logger.info(f"清理策略 '{strategy}' 保留 {len(retained_versions)} 个版本: {retained_versions}")
                    
                    versions_to_sync = retained_versions
                else:
                    if self.logger:
                        self.logger.warning(f"No matching versions found for {image_name}")
                    continue
            else:
                current_version = source.split(':')[1] if ':' in source else 'latest'
                versions_to_sync = [current_version]

            for version in versions_to_sync:
                sync_tasks.append({
                    'image_name': image_name,
                    'version': version,
                    'description': description
                })

        if use_concurrency and sync_tasks:
            print(f"Syncing {len(sync_tasks)} images (workers: {self.max_workers}, retries: {self.max_retries})")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_task = {}
                for i, task in enumerate(sync_tasks):
                    if i > 0:
                        delay = random.uniform(0.5, 1.5)
                        time.sleep(delay)

                    future = executor.submit(
                        self.sync_single_version,
                        task['image_name'],
                        task['version'],
                        task['description']
                    )
                    future_to_task[future] = task

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        future.result()
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"Sync {task['image_name']}:{task['version']} failed: {str(e)}")
                        with self._lock:
                            self.fail_count += 1
        else:
            for task in sync_tasks:
                self.sync_single_version(
                    task['image_name'],
                    task['version'],
                    task['description']
                )

        print(f"\nSummary: {self.success_count} success, {self.fail_count} failed")
        
        if self.failed_images:
            print(f"Failed images:")
            for img in self.failed_images:
                print(f"  - {img['source']}")

        return {
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'failed_images': self.failed_images
        }