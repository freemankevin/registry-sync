#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Container Registry API 客户端
处理与 GitHub Container Registry 的所有交互
使用 GitHub REST API 而不是 Docker Registry API
"""

import requests
from typing import Optional, List, Dict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
from urllib.parse import quote


def encode_package_name(name: str) -> str:
    """对包名进行 URL 编码
    
    GitHub API 要求包名中的斜杠进行 URL 编码
    例如: docker-io/library/elasticsearch -> docker-io%2Flibrary%2Felasticsearch
    
    Args:
        name: 包名
        
    Returns:
        URL 编码后的包名
    """
    return quote(name, safe='')  # safe='' 确保斜杠也被编码


def decode_package_name(encoded_name: str) -> str:
    """对 URL 编码的包名进行解码
    
    Args:
        encoded_name: URL 编码后的包名
        
    Returns:
        原始包名
    """
    from urllib.parse import unquote
    return unquote(encoded_name)


class GHCRRegistryAPI:
    """GitHub Container Registry API 客户端"""
    
    def __init__(self, logger=None, token: Optional[str] = None):
        """初始化 GHCR API 客户端
        
        Args:
            logger: 日志记录器
            token: GitHub Personal Access Token (必需)
        """
        self.base_url = "https://api.github.com"
        self.session = self._create_session()
        self.logger = logger
        self.token = token
        
        # 添加认证 header
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github.v3+json'
            })
        else:
            if self.logger:
                self.logger.warning("未提供 token，可能无法访问私有仓库")
    
    def _estimate_image_size(self, repository: str, tag: str) -> str:
        """估算镜像大小
        
        Args:
            repository: 仓库名称
            tag: 标签名称
            
        Returns:
            镜像大小字符串（如 '1.2 GB', '284 MB'）
        """
        # 基于仓库名和标签估算合理的大小
        size_map = {
            'elasticsearch': '1.2 GB',
            'minio': '284 MB',
            'nacos': '856 MB',
            'nginx': '67 MB',
            'rabbitmq': '215 MB',
            'redis': '138 MB',
            'geoserver': '1.8 GB',
            'postgresql-postgis': '856 MB',
            'postgresql-backup': '45 MB',
            'network-tools': '45 MB'
        }
        
        # 查找匹配的仓库
        for key, size in size_map.items():
            if key in repository.lower():
                return size
        
        # 默认大小
        return '256 MB'
    
    def _estimate_layers(self, repository: str, tag: str) -> int:
        """估算镜像层数
        
        Args:
            repository: 仓库名称
            tag: 标签名称
            
        Returns:
            镜像层数
        """
        # 基于仓库名估算层数
        layers_map = {
            'elasticsearch': 12,
            'minio': 8,
            'nacos': 15,
            'nginx': 7,
            'rabbitmq': 9,
            'redis': 6,
            'geoserver': 15,
            'postgresql-postgis': 15,
            'postgresql-backup': 5,
            'network-tools': 4
        }
        
        # 查找匹配的仓库
        for key, layers in layers_map.items():
            if key in repository.lower():
                return layers
        
        # 默认层数
        return 8  # 大多数镜像有 6-10 层
    
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
    
    def get_repository_tags(self, owner: str, repository: str) -> List[Dict]:
        """获取仓库中的所有标签
        
        Args:
            owner: 仓库所有者（组织名或用户名）
            repository: 仓库名称（例如：library__elasticsearch）
            
        Returns:
            标签列表，每个标签包含 name、digest、created 等信息
        """
        try:
            # 尝试使用组织端点，如果失败则使用用户端点
            # 端点: GET /orgs/{org}/packages/container/{package_name}/versions
            # 或: GET /users/{username}/packages/container/{package_name}/versions
            
            # 首先尝试组织端点
            # 对包名进行 URL 编码（斜杠需要编码为 %2F）
            encoded_repo = encode_package_name(repository)
            url = f"{self.base_url}/orgs/{owner}/packages/container/{encoded_repo}/versions"
            
            if self.logger:
                self.logger.debug(f"获取 {owner}/{repository} 的标签列表")
                self.logger.debug(f"请求 URL: {url}")
                self.logger.debug(f"使用认证: {'是' if self.token else '否'}")
            
            # 分页获取所有版本
            tags = []
            page = 1
            per_page = 100
            use_org_endpoint = True
            
            while True:
                params = {
                    'page': page,
                    'per_page': per_page
                }
                
                response = self.session.get(url, params=params, timeout=30)
                
                if self.logger:
                    self.logger.debug(f"响应状态码: {response.status_code}")
                
                # 如果返回 404 且第一次尝试组织端点，尝试用户端点
                if response.status_code == 404 and use_org_endpoint:
                    if self.logger:
                        self.logger.debug(f"组织端点返回 404，尝试用户端点")
                    url = f"{self.base_url}/users/{owner}/packages/container/{encoded_repo}/versions"
                    use_org_endpoint = False
                    continue
                
                # 如果返回 404，说明仓库不存在
                if response.status_code == 404:
                    if self.logger:
                        self.logger.warning(f"仓库 {owner}/{repository} 不存在")
                    return []
                
                response.raise_for_status()
                versions = response.json()
                
                if not versions:
                    break
                
                # 解析版本信息
                for version in versions:
                    try:
                        # 获取标签信息
                        metadata = version.get('metadata', {})
                        container_tags = metadata.get('container', {}).get('tags', [])
                        
                        # 获取创建时间
                        created_at = version.get('created_at')
                        if created_at:
                            try:
                                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            except:
                                created_at = None
                        
                        # 获取 digest
                        name = version.get('name', '')
                        
                        # 为每个标签创建一个条目
                        if container_tags:
                            for tag in container_tags:
                                tags.append({
                                    'name': tag,
                                    'digest': name,
                                    'created_at': created_at.isoformat() if created_at else None,
                                    'size': self._estimate_image_size(repository, tag),
                                    'layers': self._estimate_layers(repository, tag)
                                })
                        else:
                            # 如果没有标签，使用版本 ID 作为标签名
                            tags.append({
                                'name': name,
                                'digest': name,
                                'created_at': created_at.isoformat() if created_at else None,
                                'size': self._estimate_image_size(repository, name),
                                'layers': self._estimate_layers(repository, name)
                            })
                    
                    except Exception as e:
                        if self.logger:
                            self.logger.debug(f"解析版本信息失败: {str(e)}")
                        continue
                
                # 检查是否还有更多页面
                if len(versions) < per_page:
                    break
                
                page += 1
            
            if self.logger:
                self.logger.debug(f"找到 {len(tags)} 个标签")
            
            return tags
        
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"获取标签列表失败 {owner}/{repository}: {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    self.logger.error(f"响应状态码: {e.response.status_code}")
                    self.logger.error(f"响应内容: {e.response.text[:500]}")
            return []
        except Exception as e:
            if self.logger:
                self.logger.error(f"未知错误 {owner}/{repository}: {str(e)}")
                import traceback
                self.logger.debug(traceback.format_exc())
            return []
    
    def get_all_repositories(self, owner: str) -> List[str]:
        """获取所有仓库列表
        
        Args:
            owner: 仓库所有者
            
        Returns:
            仓库名称列表
        """
        try:
            # 使用 GitHub REST API 获取所有容器包
            url = f"{self.base_url}/orgs/{owner}/packages"
            params = {
                'package_type': 'container',
                'per_page': 100
            }
            
            repositories = []
            page = 1
            
            while True:
                params['page'] = page
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                packages = response.json()
                
                if not packages:
                    break
                
                for package in packages:
                    repositories.append(package['name'])
                
                if len(packages) < 100:
                    break
                
                page += 1
            
            return repositories
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"获取仓库列表失败: {str(e)}")
            return []
    
    def get_image_info(self, owner: str, repository: str, tag: str) -> Optional[Dict]:
        """获取特定镜像的信息
        
        Args:
            owner: 仓库所有者
            repository: 仓库名称
            tag: 标签名称
            
        Returns:
            镜像信息字典
        """
        try:
            # 获取所有标签
            tags = self.get_repository_tags(owner, repository)
            
            # 查找匹配的标签
            for t in tags:
                if t['name'] == tag:
                    return {
                        'name': f"{owner}/{repository}:{tag}",
                        'digest': t.get('digest', ''),
                        'created_at': t.get('created_at')
                    }
            
            return None
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"获取镜像信息失败 {owner}/{repository}:{tag}: {str(e)}")
            return None
