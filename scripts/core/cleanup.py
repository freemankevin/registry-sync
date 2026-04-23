#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像清理工具
清理不符合当前镜像规则的旧镜像
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from scripts.api.ghcr_api import GHCRRegistryAPI, encode_package_name
from scripts.utils import convert_to_ghcr_path, setup_logger, COLOR_GREEN, COLOR_YELLOW, COLOR_RED, COLOR_CYAN, COLOR_RESET


def parse_version_tag(tag: str) -> Optional[Tuple[int, int, int]]:
    """解析版本标签，返回 (major, minor, patch)"""
    match = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', tag)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    
    match = re.match(r'^v?(\d+)\.(\d+)$', tag)
    if match:
        return (int(match.group(1)), int(match.group(2)), 0)
    
    return None


def get_major_version(tag: str) -> Optional[int]:
    """获取主版本号"""
    parsed = parse_version_tag(tag)
    return parsed[0] if parsed else None


class ImageCleanup:
    """镜像清理管理器"""
    
    def __init__(self, owner: str, token: str, logger=None, max_workers: int = 3):
        self.owner = owner
        self.token = token
        self.logger = logger
        self.max_workers = max_workers
        self.ghcr_api = GHCRRegistryAPI(logger, token=token)
        self.deleted_packages = []
        self.deleted_versions = []
        self.failed_deletions = []
    
    def get_expected_packages(self, manifest_file: Path) -> Set[str]:
        """从清单文件获取预期的 package 名称
        
        Args:
            manifest_file: 清单文件路径
            
        Returns:
            预期的 package 名称集合（使用新格式 /）
        """
        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
        
        expected = set()
        
        for img in manifest.get('images', []):
            if not img.get('enabled', True):
                continue
            
            source = img['source']
            image_name = source.split(':')[0]
            
            if source.startswith('ghcr.io/'):
                parts = source.replace('ghcr.io/', '').split('/')
                if len(parts) >= 2:
                    repo = '/'.join(parts[1:]).split(':')[0]
                    expected.add(repo)
            else:
                ghcr_path = convert_to_ghcr_path(image_name)
                expected.add(ghcr_path)
        
        return expected
    
    def get_all_packages(self) -> List[str]:
        """获取 GHCR 中所有的 package 名称
        
        Returns:
            package 名称列表
        """
        return self.ghcr_api.get_all_repositories(self.owner)
    
    def classify_packages(self, all_packages: List[str], expected_packages: Set[str]) -> Tuple[List[str], List[str]]:
        """分类 package：需要删除的 vs 需要保留的
        
        Args:
            all_packages: 所有 package 列表
            expected_packages: 预期保留的 package 集合（新格式，不包含域名前缀）
            
        Returns:
            (需要删除的 package 列表, 需要保留的 package 列表)
        """
        to_delete = []
        to_keep = []
        
        for pkg in all_packages:
            # 新格式：直接匹配
            if pkg in expected_packages:
                to_keep.append(pkg)
            # 新格式：双下划线格式
            elif pkg.replace('__', '/') in expected_packages:
                to_keep.append(pkg)
            # 旧格式：包含域名前缀的 package（需要删除）
            # 例如：docker-io/library/elasticsearch 应该被删除
            # 因为新格式是 library/elasticsearch
            elif self._is_old_format(pkg, expected_packages):
                to_delete.append(pkg)
            else:
                to_delete.append(pkg)
        
        return to_delete, to_keep
    
    def _is_old_format(self, pkg: str, expected_packages: Set[str]) -> bool:
        """检查 package 是否是旧格式（包含域名前缀）
        
        Args:
            pkg: package 名称
            expected_packages: 预期保留的 package 集合
            
        Returns:
            True 如果是旧格式，False 否则
        """
        # 旧的域名前缀列表
        old_prefixes = [
            'docker-io/', 'gcr-io/', 'quay-io/', 'registry-k8s-io/',
            'docker-io__', 'gcr-io__', 'quay-io__', 'registry-k8s-io__'
        ]
        
        # 检查是否以旧的域名前缀开头
        for prefix in old_prefixes:
            if pkg.startswith(prefix):
                # 移除前缀后检查是否在预期集合中
                new_pkg = pkg[len(prefix):]
                if new_pkg in expected_packages or new_pkg.replace('__', '/') in expected_packages:
                    return True
        
        return False
    
    def get_old_format_packages(self, expected_packages: Set[str]) -> List[str]:
        """获取使用旧命名格式的 package（需要迁移/删除）
        
        Args:
            expected_packages: 预期保留的 package 集合（新格式）
            
        Returns:
            使用旧格式的 package 列表
        """
        all_packages = self.get_all_packages()
        old_format = []
        
        for pkg in all_packages:
            # 检查是否是旧格式
            if self._is_old_format(pkg, expected_packages):
                old_format.append(pkg)
        
        return old_format
    
    def cleanup_old_packages(self, packages_to_delete: List[str], dry_run: bool = True) -> Dict:
        """清理不需要的 package
        
        Args:
            packages_to_delete: 需要删除的 package 列表
            dry_run: 是否为预演模式
            
        Returns:
            清理结果统计
        """
        print(f"\n{COLOR_CYAN}{'='*60}{COLOR_RESET}")
        print(f"{COLOR_YELLOW}清理不需要的 Package{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}\n")
        
        if not packages_to_delete:
            print(f"{COLOR_GREEN}没有需要删除的 Package{COLOR_RESET}")
            return {'deleted': 0, 'failed': 0}
        
        print(f"发现 {len(packages_to_delete)} 个需要删除的 Package:")
        for pkg in packages_to_delete:
            print(f"  - {pkg}")
        
        if dry_run:
            print(f"\n{COLOR_YELLOW}[预演模式] 不会实际删除{COLOR_RESET}")
            return {'deleted': len(packages_to_delete), 'failed': 0, 'dry_run': True}
        
        success = 0
        failed = 0
        
        for pkg in packages_to_delete:
            print(f"\n🗑️  删除 Package: {pkg}")
            if self.ghcr_api.delete_package(self.owner, pkg):
                print(f"   {COLOR_GREEN}✓ 成功{COLOR_RESET}")
                self.deleted_packages.append(pkg)
                success += 1
            else:
                print(f"   {COLOR_RED}✗ 失败{COLOR_RESET}")
                self.failed_deletions.append({'type': 'package', 'name': pkg})
                failed += 1
        
        return {'deleted': success, 'failed': failed}
    
    def cleanup_old_versions(
        self,
        manifest_file: Path,
        dry_run: bool = True,
        retention_config: Dict = None
    ) -> Dict:
        """清理保留 package 中不符合规则的旧版本
        
        Args:
            manifest_file: 清单文件路径
            dry_run: 是否为预演模式
            retention_config: 保留策略配置
            
        Returns:
            清理结果统计
        """
        print(f"\n{COLOR_CYAN}{'='*60}{COLOR_RESET}")
        print(f"{COLOR_YELLOW}清理旧版本{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}\n")
        
        with open(manifest_file, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
        
        global_retention = manifest.get('config', {}).get('retention', {})
        default_max_versions = global_retention.get('max_versions', 3)
        default_strategy = global_retention.get('strategy', 'max_versions')
        
        versions_to_delete = []
        
        for img in manifest.get('images', []):
            if not img.get('enabled', True):
                continue
            
            source = img['source']
            image_name = source.split(':')[0]
            tag_pattern = img.get('tag_pattern')
            exclude_pattern = img.get('exclude_pattern')
            local_retention = img.get('retention', {})
            
            strategy = local_retention.get('strategy', default_strategy)
            max_versions = local_retention.get('max_versions', default_max_versions)
            major_versions = local_retention.get('major_versions', [])
            
            if source.startswith('ghcr.io/'):
                parts = source.replace('ghcr.io/', '').split('/')
                if len(parts) >= 2:
                    repo = '/'.join(parts[1:]).split(':')[0]
                    ghcr_path = repo
                else:
                    continue
            else:
                ghcr_path = convert_to_ghcr_path(image_name)
            
            print(f"\n📦 检查 {ghcr_path}...")
            print(f"   策略: {strategy}")
            print(f"   max_versions: {max_versions}")
            print(f"   major_versions: {major_versions}")
            print(f"   条件判断: strategy='latest_per_major'={strategy == 'latest_per_major'}, major_versions非空={bool(major_versions)}")
            
            versions = self.ghcr_api.get_package_versions(self.owner, ghcr_path)
            
            if not versions:
                print(f"   {COLOR_YELLOW}未找到版本{COLOR_RESET}")
                continue
            
            valid_versions = []
            for v in versions:
                tags = v.get('tags', [])
                if not tags:
                    continue
                
                for tag in tags:
                    if tag_pattern:
                        try:
                            if not re.match(tag_pattern, tag):
                                if self.logger:
                                    self.logger.debug(f"标签 {tag} 不匹配模式 {tag_pattern}")
                                versions_to_delete.append({
                                    'package': ghcr_path,
                                    'version_id': v['id'],
                                    'tag': tag,
                                    'reason': '不匹配 tag_pattern'
                                })
                                continue
                        except re.error:
                            pass
                    
                    if exclude_pattern:
                        try:
                            if re.search(exclude_pattern, tag):
                                if self.logger:
                                    self.logger.debug(f"标签 {tag} 匹配排除模式 {exclude_pattern}")
                                versions_to_delete.append({
                                    'package': ghcr_path,
                                    'version_id': v['id'],
                                    'tag': tag,
                                    'reason': '匹配 exclude_pattern'
                                })
                                continue
                        except re.error:
                            pass
                    
                    valid_versions.append({'version': v, 'tag': tag})
            
            # Apply retention strategy
            if strategy == 'latest_per_major' and major_versions:
                versions_to_delete.extend(
                    self._apply_latest_per_major_strategy(
                        ghcr_path, valid_versions, major_versions
                    )
                )
            elif strategy == 'latest_per_minor' and local_retention.get('keep_minor_versions'):
                versions_to_delete.extend(
                    self._apply_latest_per_minor_strategy(
                        ghcr_path, valid_versions, local_retention.get('keep_minor_versions', [])
                    )
                )
            elif strategy == 'max_versions':
                versions_to_delete.extend(
                    self._apply_max_versions_strategy(
                        ghcr_path, valid_versions, max_versions
                    )
                )
        
        unique_deletions = []
        seen = set()
        for item in versions_to_delete:
            key = (item['package'], item['version_id'])
            if key not in seen:
                seen.add(key)
                unique_deletions.append(item)
        
        if not unique_deletions:
            print(f"\n{COLOR_GREEN}没有需要删除的旧版本{COLOR_RESET}")
            return {'deleted': 0, 'failed': 0}
        
        print(f"\n发现 {len(unique_deletions)} 个需要删除的版本:")
        for item in unique_deletions[:20]:
            print(f"  - {item['package']}/{item['version_id']} ({item['tag']}) - {item['reason']}")
        if len(unique_deletions) > 20:
            print(f"  ... 还有 {len(unique_deletions) - 20} 个")
        
        if dry_run:
            print(f"\n{COLOR_YELLOW}[预演模式] 不会实际删除{COLOR_RESET}")
            return {'deleted': len(unique_deletions), 'failed': 0, 'dry_run': True}
        
        success = 0
        failed = 0
        
        for item in unique_deletions:
            print(f"\n🗑️  删除版本: {item['package']}/{item['version_id']} ({item['tag']})")
            if self.ghcr_api.delete_package_version(self.owner, item['package'], item['version_id']):
                print(f"   {COLOR_GREEN}✓ 成功{COLOR_RESET}")
                self.deleted_versions.append(item)
                success += 1
            else:
                print(f"   {COLOR_RED}✗ 失败{COLOR_RESET}")
                self.failed_deletions.append({'type': 'version', **item})
                failed += 1
        
        return {'deleted': success, 'failed': failed}
    
    def _apply_latest_per_major_strategy(
        self,
        ghcr_path: str,
        valid_versions: List[Dict],
        major_versions: List[int]
    ) -> List[Dict]:
        """应用每个大版本只保留最新小版本的策略
        
        Args:
            ghcr_path: package 路径
            valid_versions: 有效版本列表
            major_versions: 需要保留的大版本列表
            
        Returns:
            需要删除的版本列表
        """
        versions_by_major = defaultdict(list)
        
        for item in valid_versions:
            tag = item['tag']
            major = get_major_version(tag)
            if major and major in major_versions:
                parsed = parse_version_tag(tag)
                if parsed:
                    versions_by_major[major].append({
                        'version': item['version'],
                        'tag': tag,
                        'major': parsed[0],
                        'minor': parsed[1],
                        'patch': parsed[2]
                    })
        
        to_delete = []
        
        for major, versions in versions_by_major.items():
            # 按小版本号排序，保留最新的
            versions.sort(key=lambda x: (x['minor'], x['patch']), reverse=True)
            
            print(f"   大版本 {major}: 找到 {len(versions)} 个版本")
            
            # 保留最新的一个
            if len(versions) > 1:
                latest = versions[0]
                print(f"   {COLOR_GREEN}保留: {latest['tag']} (最新){COLOR_RESET}")
                
                for v in versions[1:]:
                    print(f"   {COLOR_YELLOW}标记删除: {v['tag']}{COLOR_RESET}")
                    to_delete.append({
                        'package': ghcr_path,
                        'version_id': v['version']['id'],
                        'tag': v['tag'],
                        'reason': f'大版本 {major} 只保留最新版本 {latest["tag"]}'
                    })
        
        return to_delete
    
    def _apply_max_versions_strategy(
        self,
        ghcr_path: str,
        valid_versions: List[Dict],
        max_versions: int
    ) -> List[Dict]:
        """应用最大版本数策略
        
        Args:
            ghcr_path: package 路径
            valid_versions: 有效版本列表
            max_versions: 最大保留版本数
            
        Returns:
            需要删除的版本列表
        """
        valid_versions.sort(
            key=lambda x: x['version'].get('created_at') or '', 
            reverse=True
        )
        
        to_delete = []
        
        if len(valid_versions) > max_versions:
            for item in valid_versions[max_versions:]:
                to_delete.append({
                    'package': ghcr_path,
                    'version_id': item['version']['id'],
                    'tag': item['tag'],
                    'reason': f'超出 max_versions ({max_versions})'
                })
        
        return to_delete
    
    def _apply_latest_per_minor_strategy(
        self,
        ghcr_path: str,
        valid_versions: List[Dict],
        keep_minor_versions: List[str]
    ) -> List[Dict]:
        """应用每个小版本系列只保留最新补丁版本的策略
        
        Args:
            ghcr_path: package 路径
            valid_versions: 有效版本列表
            keep_minor_versions: 需要保留的小版本系列列表，如 ['2.28', '2.27']
            
        Returns:
            需要删除的版本列表
        """
        versions_by_minor = defaultdict(list)
        
        for item in valid_versions:
            tag = item['tag']
            parsed = parse_version_tag(tag)
            if parsed:
                minor_key = f"{parsed[0]}.{parsed[1]}"
                if minor_key in keep_minor_versions or not keep_minor_versions:
                    versions_by_minor[minor_key].append({
                        'version': item['version'],
                        'tag': tag,
                        'major': parsed[0],
                        'minor': parsed[1],
                        'patch': parsed[2]
                    })
        
        to_delete = []
        
        for minor_key, versions in versions_by_minor.items():
            # 按补丁版本号排序，保留最新的
            versions.sort(key=lambda x: x['patch'], reverse=True)
            
            print(f"   小版本 {minor_key}: 找到 {len(versions)} 个版本")
            
            # 保留最新的一个
            if len(versions) > 1:
                latest = versions[0]
                print(f"   {COLOR_GREEN}保留: {latest['tag']} (最新){COLOR_RESET}")
                
                for v in versions[1:]:
                    print(f"   {COLOR_YELLOW}标记删除: {v['tag']}{COLOR_RESET}")
                    to_delete.append({
                        'package': ghcr_path,
                        'version_id': v['version']['id'],
                        'tag': v['tag'],
                        'reason': f'小版本 {minor_key} 只保留最新版本 {latest["tag"]}'
                    })
        
        return to_delete
    
    def run_cleanup(self, manifest_file: Path, dry_run: bool = True) -> Dict:
        """执行完整的清理流程
        
        Args:
            manifest_file: 清单文件路径
            dry_run: 是否为预演模式
            
        Returns:
            清理结果统计
        """
        print(f"\n{COLOR_CYAN}{'='*60}{COLOR_RESET}")
        print(f"{COLOR_GREEN}镜像清理工具{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}")
        print(f"Owner: {self.owner}")
        print(f"模式: {'预演 (不会实际删除)' if dry_run else '实际删除'}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}\n")
        
        expected_packages = self.get_expected_packages(manifest_file)
        print(f"清单中定义的 Package 数量: {len(expected_packages)}")
        
        all_packages = self.get_all_packages()
        print(f"GHCR 中实际存在的 Package 数量: {len(all_packages)}")
        
        packages_to_delete, packages_to_keep = self.classify_packages(all_packages, expected_packages)
        
        result = {
            'packages': {},
            'versions': {},
            'total_deleted_packages': 0,
            'total_deleted_versions': 0,
            'total_failed': 0
        }
        
        if packages_to_delete:
            pkg_result = self.cleanup_old_packages(packages_to_delete, dry_run)
            result['packages'] = pkg_result
            result['total_deleted_packages'] = pkg_result.get('deleted', 0)
            result['total_failed'] += pkg_result.get('failed', 0)
        
        version_result = self.cleanup_old_versions(manifest_file, dry_run)
        result['versions'] = version_result
        result['total_deleted_versions'] = version_result.get('deleted', 0)
        result['total_failed'] += version_result.get('failed', 0)
        
        print(f"\n{COLOR_CYAN}{'='*60}{COLOR_RESET}")
        print(f"{COLOR_GREEN}清理完成{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}")
        print(f"删除的 Package: {result['total_deleted_packages']}")
        print(f"删除的版本: {result['total_deleted_versions']}")
        print(f"失败: {result['total_failed']}")
        if dry_run:
            print(f"{COLOR_YELLOW}注意: 这是预演模式，未实际删除{COLOR_RESET}")
        print(f"{COLOR_CYAN}{'='*60}{COLOR_RESET}\n")
        
        return result