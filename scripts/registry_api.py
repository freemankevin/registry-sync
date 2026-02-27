#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一容器镜像仓库 API 客户端
支持 Docker Hub、Google Container Registry (GCR)、Quay.io
"""

import re
import requests
from typing import Optional, Tuple, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class RegistryAPI:
    """统一容器镜像仓库 API 客户端"""
    
    REGISTRY_TYPES = {
        'dockerhub': 'hub.docker.com',
        'gcr': 'gcr.io',
        'quay': 'quay.io',
        'ghcr': 'ghcr.io'
    }
    
    def __init__(self, logger=None, max_workers: int = 5):
        self.session = self._create_session()
        self.logger = logger
        self.max_workers = max_workers
        self._lock = threading.Lock()
    
    def _create_session(self) -> requests.Session:
        """创建带重试策略的会话"""
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retries, pool_maxsize=10)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        return session
    
    def detect_registry(self, image: str) -> str:
        """检测镜像所属的仓库类型
        
        Args:
            image: 镜像地址，如 gcr.io/project/image:tag
            
        Returns:
            仓库类型: 'dockerhub', 'gcr', 'quay', 'ghcr'
        """
        if image.startswith('gcr.io/') or image.startswith('registry.k8s.io/'):
            return 'gcr'
        elif image.startswith('quay.io/'):
            return 'quay'
        elif image.startswith('ghcr.io/'):
            return 'ghcr'
        else:
            return 'dockerhub'
    
    def extract_repository(self, image: str) -> Tuple[str, str, str]:
        """提取镜像的仓库信息
        
        Args:
            image: 镜像地址
            
        Returns:
            (registry_type, repository_name, registry_url)
        """
        registry = self.detect_registry(image)
        
        if registry == 'dockerhub':
            # library/nginx 或 user/repo
            repo = image.split(':')[0]
            if '/' not in repo:
                repo = f"library/{repo}"
            return (registry, repo, 'dockerhub')
        elif registry == 'gcr':
            # gcr.io/project/image 或 registry.k8s.io/image
            if image.startswith('registry.k8s.io/'):
                repo = image.replace('registry.k8s.io/', '').split(':')[0]
                return (registry, repo, 'registry.k8s.io')
            else:
                repo = image.replace('gcr.io/', '').split(':')[0]
                return (registry, repo, 'gcr.io')
        elif registry == 'quay':
            # quay.io/org/repo
            repo = image.replace('quay.io/', '').split(':')[0]
            return (registry, repo, 'quay.io')
        elif registry == 'ghcr':
            # ghcr.io/owner/repo
            repo = image.replace('ghcr.io/', '').split(':')[0]
            return (registry, repo, 'ghcr.io')
        
        return (registry, image.split(':')[0], 'dockerhub')
    
    def version_key(self, version_str: str) -> Tuple[int, ...]:
        """将版本号字符串转换为可比较的元组"""
        try:
            if not version_str:
                return (0, 0, 0)
            
            # 处理 RELEASE 格式
            if version_str.startswith('RELEASE.'):
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', version_str)
                if date_match:
                    return tuple(map(int, date_match.groups()))
            
            # 移除 v 前缀
            if version_str.startswith('v'):
                version_str = version_str[1:]
            
            # 分割版本号
            version_parts = version_str.split('-')[0]
            parts = []
            for part in version_parts.split('.'):
                try:
                    parts.append(int(part))
                except ValueError:
                    parts.append(0)
            
            while len(parts) < 3:
                parts.append(0)
            
            return tuple(parts[:3])
        except Exception as e:
            if self.logger:
                self.logger.debug(f"版本号解析出错 {version_str}: {str(e)}")
            return (0, 0, 0)
    
    def _get_dockerhub_tags(
        self, 
        repository: str, 
        tag_pattern: str,
        exclude_pattern: Optional[str] = None,
        max_pages: int = 5
    ) -> List[str]:
        """获取 Docker Hub 镜像的标签列表"""
        matching_tags = []
        page = 1
        
        while page <= max_pages:
            url = f"https://registry.hub.docker.com/v2/repositories/{repository}/tags"
            params = {
                'page_size': 100,
                'page': page,
                'ordering': 'last_updated'
            }
            
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                results = data.get('results', [])
                if not results:
                    break
                
                for tag in results:
                    tag_name = tag['name']
                    
                    if not re.match(tag_pattern, tag_name):
                        continue
                    
                    if exclude_pattern and re.match(exclude_pattern, tag_name):
                        continue
                    
                    matching_tags.append(tag_name)
                
                if not data.get('next'):
                    break
                
                page += 1
                
            except Exception as e:
                if self.logger:
                    self.logger.error(f"获取 Docker Hub 标签失败 {repository}: {str(e)}")
                break
        
        return matching_tags
    
    def _get_quay_tags(
        self, 
        repository: str, 
        tag_pattern: str,
        exclude_pattern: Optional[str] = None,
        max_pages: int = 5
    ) -> List[str]:
        """获取 Quay.io 镜像的标签列表"""
        matching_tags = []
        page = 1
        
        while page <= max_pages:
            url = f"https://quay.io/api/v1/repository/{repository}/tag/"
            params = {
                'limit': 100,
                'page': page,
                'onlyActiveTags': 'true'
            }
            
            try:
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 404:
                    if self.logger:
                        self.logger.debug(f"Quay 仓库不存在: {repository}")
                    return []
                
                if response.status_code == 401:
                    if self.logger:
                        self.logger.debug(f"Quay 仓库需要认证: {repository}")
                    return []
                
                response.raise_for_status()
                data = response.json()
                
                results = data.get('tags', [])
                if not results:
                    break
                
                for tag in results:
                    tag_name = tag.get('name', '')
                    
                    if not tag_name:
                        continue
                    
                    if not re.match(tag_pattern, tag_name):
                        continue
                    
                    if exclude_pattern and re.match(exclude_pattern, tag_name):
                        continue
                    
                    matching_tags.append(tag_name)
                
                # Quay 使用不同的分页机制
                if not data.get('has_additional'):
                    break
                
                page += 1
                
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"获取 Quay 标签失败 {repository}: {str(e)}")
                break
        
        return matching_tags
    
    def _get_gcr_tags(
        self, 
        repository: str, 
        tag_pattern: str,
        exclude_pattern: Optional[str] = None,
        max_pages: int = 5,
        registry_url: str = 'gcr.io'
    ) -> List[str]:
        """获取 GCR 镜像的标签列表
        
        GCR 使用 Container Registry API 或可以直接查询 gcr.io 的清单
        注意：某些 GCR 仓库是私有的，可能返回 401
        """
        matching_tags = []
        
        # GCR 的 tags 列表 API
        # https://gcr.io/v2/{repository}/tags/list
        url = f"https://{registry_url}/v2/{repository}/tags/list"
        
        try:
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 404:
                if self.logger:
                    self.logger.debug(f"GCR 仓库不存在: {repository}")
                return []
            
            if response.status_code == 401:
                # 私有仓库，无法获取标签列表
                if self.logger:
                    self.logger.debug(f"GCR 仓库需要认证，跳过: {repository}")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            tags = data.get('tags', [])
            
            for tag_name in tags:
                if not re.match(tag_pattern, tag_name):
                    continue
                
                if exclude_pattern and re.match(exclude_pattern, tag_name):
                    continue
                
                matching_tags.append(tag_name)
                
        except Exception as e:
            if self.logger:
                self.logger.debug(f"获取 GCR 标签失败 {repository}: {str(e)}")
        
        return matching_tags
    
    def get_all_matching_versions(
        self, 
        image: str,
        tag_pattern: str,
        exclude_pattern: Optional[str] = None,
        max_pages: int = 5
    ) -> List[str]:
        """获取符合模式的所有版本
        
        Args:
            image: 完整镜像地址
            tag_pattern: 标签匹配正则
            exclude_pattern: 排除标签正则
            max_pages: 最大页数
            
        Returns:
            匹配的标签列表
        """
        registry, repository, registry_url = self.extract_repository(image)
        
        if self.logger:
            self.logger.debug(f"获取 {registry} 镜像 {repository} 的标签列表")
        
        if registry == 'quay':
            matching_tags = self._get_quay_tags(repository, tag_pattern, exclude_pattern, max_pages)
        elif registry == 'gcr':
            matching_tags = self._get_gcr_tags(repository, tag_pattern, exclude_pattern, max_pages, registry_url)
        elif registry == 'ghcr':
            # GHCR 需要通过 GitHub API 或直接跳过
            if self.logger:
                self.logger.debug(f"跳过 GHCR 标签获取: {image}")
            return []
        else:
            matching_tags = self._get_dockerhub_tags(repository, tag_pattern, exclude_pattern, max_pages)
        
        if not matching_tags:
            if self.logger:
                self.logger.debug(f"未找到符合模式的标签: {image} (模式: {tag_pattern})")
            return []
        
        # 去重并排序
        matching_tags = list(set(matching_tags))
        matching_tags.sort(key=self.version_key)
        
        if self.logger:
            self.logger.debug(f"找到 {len(matching_tags)} 个匹配标签")
        
        return matching_tags
    
    def get_latest_version(
        self, 
        image: str,
        tag_pattern: str,
        exclude_pattern: Optional[str] = None
    ) -> Optional[str]:
        """获取符合模式的最新版本"""
        matching_tags = self.get_all_matching_versions(
            image, tag_pattern, exclude_pattern
        )
        
        if not matching_tags:
            return None
        
        latest = matching_tags[-1]
        if self.logger:
            self.logger.debug(f"找到 {len(matching_tags)} 个匹配标签，最新: {latest}")
        return latest
    
    def get_latest_versions_batch(
        self,
        images: List[Tuple[str, str, Optional[str]]],
        max_workers: Optional[int] = None
    ) -> List[Tuple[str, Optional[str]]]:
        """并发获取多个镜像的最新版本
        
        Args:
            images: 镜像列表，每个元素为 (image, tag_pattern, exclude_pattern)
            max_workers: 最大并发数
            
        Returns:
            返回列表，每个元素为 (image, latest_version)
        """
        if max_workers is None:
            max_workers = self.max_workers
        
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_image = {
                executor.submit(
                    self.get_latest_version, 
                    img, 
                    pattern, 
                    exclude
                ): img 
                for img, pattern, exclude in images
            }
            
            for future in as_completed(future_to_image):
                img = future_to_image[future]
                try:
                    latest_version = future.result()
                    results.append((img, latest_version))
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"获取 {img} 最新版本失败: {str(e)}")
                    results.append((img, None))
        
        return results
