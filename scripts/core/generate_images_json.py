#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 GitHub Container Registry 生成镜像列表 JSON
"""

import json
import yaml
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

# 设置标准输出编码为 UTF-8（解决 Windows 终端编码问题）
if sys.platform == 'win32':
    import codecs
    try:
        # 尝试直接设置编码
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        # 如果失败，跳过编码设置
        pass

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.api.ghcr_api import GHCRRegistryAPI
from scripts.utils import setup_logger, convert_to_ghcr_path, parse_image_name
from scripts.utils.translations import add_chinese_description
from scripts.core.mirror_sync import apply_retention_strategy


def normalize_source_image(image_name: str) -> str:
    """规范化镜像名称，添加完整的仓库地址前缀
    
    Args:
        image_name: 镜像名称，如 'nginx', 'kartoza/geoserver', 'library/nginx', 'ghcr.io/freemankevin/netkit'
        
    Returns:
        规范化后的镜像名称，如 'docker.io/library/nginx', 'docker.io/kartoza/geoserver', 'ghcr.io/freemankevin/netkit'
    """
    if not image_name:
        return ''
    
    # 如果已经包含协议前缀（如 docker://, https://），直接返回
    if '://' in image_name:
        return image_name
    
    # 如果已经包含 docker.io/，直接返回
    if image_name.startswith('docker.io/'):
        return image_name
    
    # 如果已经包含 ghcr.io/，直接返回（GHCR 镜像已经是完整地址）
    if image_name.startswith('ghcr.io/'):
        return image_name
    
    # 如果包含其他仓库前缀（如 gcr.io/, quay.io/），直接返回
    if '/' in image_name and '.' in image_name.split('/')[0]:
        return image_name
    
    # 检查是否是官方镜像（不包含斜杠或以 library/ 开头）
    if '/' not in image_name:
        return f'docker.io/library/{image_name}'
    
    # 对于其他镜像，添加 docker.io/ 前缀
    return f'docker.io/{image_name}'


def filter_tags_by_pattern(
    tags: List[Dict],
    tag_pattern: Optional[str] = None,
    exclude_pattern: Optional[str] = None,
    logger=None
) -> List[Dict]:
    """根据 tag_pattern 和 exclude_pattern 过滤标签
    
    Args:
        tags: 标签列表
        tag_pattern: 包含标签的正则表达式模式
        exclude_pattern: 排除标签的正则表达式模式
        logger: 日志记录器
        
    Returns:
        过滤后的标签列表
    """
    filtered_tags = []
    
    for tag in tags:
        tag_name = tag['name']
        
        # 如果有 tag_pattern，检查标签是否匹配
        if tag_pattern:
            try:
                if not re.match(tag_pattern, tag_name):
                    if logger:
                        logger.debug(f"标签 '{tag_name}' 不匹配模式 '{tag_pattern}'，已过滤")
                    continue
            except re.error as e:
                if logger:
                    logger.warning(f"tag_pattern 正则表达式错误: {e}")
                continue
        
        # 如果有 exclude_pattern，检查标签是否需要排除
        if exclude_pattern:
            try:
                if re.search(exclude_pattern, tag_name):
                    if logger:
                        logger.debug(f"标签 '{tag_name}' 匹配排除模式 '{exclude_pattern}'，已过滤")
                    continue
            except re.error as e:
                if logger:
                    logger.warning(f"exclude_pattern 正则表达式错误: {e}")
                continue
        
        # 标签通过所有过滤条件
        filtered_tags.append(tag)
    
    return filtered_tags


def sort_tags_by_version(tags: List[Dict], logger=None) -> List[Dict]:
    """按版本号语义排序标签（最新的在前）
    
    Args:
        tags: 标签列表
        logger: 日志记录器
        
    Returns:
        排序后的标签列表
    """
    def version_key(tag):
        """生成用于排序的键值"""
        tag_name = tag['name']
        
        # 特殊处理 'latest' 标签，让它排在最后
        if tag_name.lower() == 'latest':
            return (0, 0, 0, 0, tag.get('created_at') or '')
        
        # 尝试解析版本号
        try:
            # 移除开头的 'v' 或 'V'
            clean_name = re.sub(r'^[vV]+', '', tag_name)
            
            # 提取数字版本部分（如 18.1, 17.7, 16.11）
            version_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', clean_name)
            if version_match:
                major = int(version_match.group(1)) if version_match.group(1) else 0
                minor = int(version_match.group(2)) if version_match.group(2) else 0
                patch = int(version_match.group(3)) if version_match.group(3) else 0
                # 按版本号降序排序（大版本在前）
                return (1, major, minor, patch, tag.get('created_at') or '')
            
            # 如果无法解析版本号，使用原始字符串排序
            return (2, tag_name, tag.get('created_at') or '')
        except Exception as e:
            if logger:
                logger.debug(f"解析版本号失败: {tag_name}, 错误: {e}")
            return (3, tag_name, tag.get('created_at') or '')
    
    # 按键值排序（降序：最新的在前）
    return sorted(tags, key=version_key, reverse=True)


def generate_images_json(
    manifest_file: Path,
    output_file: Path,
    registry: str = "ghcr.io",
    owner: str = "",
    token: str = None,
    logger=None,
    failed_images: List[Dict] = None
) -> Dict:
    """从 GHCR 生成镜像列表 JSON（包含所有版本）
    
    Args:
        manifest_file: 清单文件路径
        output_file: 输出文件路径
        registry: 镜像仓库地址
        owner: 仓库所有者
        token: GitHub Personal Access Token (可选)
        logger: 日志记录器
        failed_images: 同步失败的镜像列表
        
    Returns:
        生成的镜像数据
    """
    if not logger:
        logger = setup_logger('generate', False, project_root / 'logs')
    
    failed_images = failed_images or []
    
    with open(manifest_file, 'r', encoding='utf-8') as f:
        manifest = yaml.safe_load(f)
    
    global_retention = manifest.get('config', {}).get('retention', {})
    default_strategy = global_retention.get('strategy', 'max_versions')
    default_max_versions = global_retention.get('max_versions', 3)
    
    ghcr_api = GHCRRegistryAPI(logger, token)
    
    # 收集所有镜像信息（按 image_name 分组，合并相同镜像的不同版本）
    image_groups = {}
    total_versions = 0
    
    for img in manifest.get('images', []):
        if not img.get('enabled', True):
            continue
        
        source = img['source']
        description = img.get('description', '')
        tag_pattern = img.get('tag_pattern')
        exclude_pattern = img.get('exclude_pattern')
        retention = img.get('retention', {})
        sync_all = img.get('sync_all_matching', False)
        
        if ':' in source:
            image_name, version = source.rsplit(':', 1)
        else:
            image_name = source
            version = 'latest'
        
        if image_name not in image_groups:
            image_groups[image_name] = {
                'description': description,
                'source': source,
                'tag_patterns': [],
                'exclude_pattern': exclude_pattern,
                'retention': retention,
                'sync_all': sync_all,
                'current_version': version,
            }
        if tag_pattern:
            image_groups[image_name]['tag_patterns'].append(tag_pattern)
    
    # 处理每个镜像组
    images = []
    for image_name, group_info in image_groups.items():
        description = group_info['description']
        source = group_info['source']
        tag_patterns = group_info['tag_patterns']
        exclude_pattern = group_info['exclude_pattern']
        retention = group_info['retention']
        sync_all = group_info.get('sync_all', False)
        current_version = group_info.get('current_version', 'latest')
        
        strategy = retention.get('strategy', default_strategy)
        max_versions = retention.get('max_versions', default_max_versions)
        major_versions = retention.get('major_versions', [])
        keep_minor_versions = retention.get('keep_minor_versions', [])
        
        # 检查源镜像是否来自 GHCR
        is_ghcr_source = source.startswith('ghcr.io/')
        
        if is_ghcr_source:
            # 对于 GHCR 源镜像，直接从源镜像获取标签信息
            # 提取 GHCR 仓库的所有者和仓库名
            # 格式: ghcr.io/{owner}/{repo}:{tag}
            parts = source.replace('ghcr.io/', '').split('/')
            if len(parts) >= 2:
                source_owner = parts[0]
                # 剩余部分是仓库名（可能包含斜杠）
                source_repo = '/'.join(parts[1:]).split(':')[0]
                # GHCR 源镜像保持原有格式（ghcr.io 已经是友好格式）
                source_repo_name = source_repo.replace('/', '__')  # API 调用需要双下划线格式
                
                print(f"\n🔍 获取 GHCR 源镜像 {source_owner}/{source_repo_name} 的所有标签...")
                logger.debug(f"原始源: {source}")
                logger.debug(f"标签匹配模式: {tag_patterns}")
                logger.debug(f"排除模式: {exclude_pattern}")
                tags = ghcr_api.get_repository_tags(source_owner, source_repo_name)
                
                if tags:
                    logger.debug(f"找到 {len(tags)} 个标签")
                    
                    # 根据多个 tag_patterns 和 exclude_pattern 过滤标签
                    # 合并多个 pattern 的结果（OR 逻辑）
                    filtered_tags = []
                    seen_tags = set()
                    for pattern in tag_patterns:
                        batch = filter_tags_by_pattern(
                            tags,
                            tag_pattern=pattern,
                            exclude_pattern=exclude_pattern,
                            logger=logger
                        )
                        for tag in batch:
                            if tag['name'] not in seen_tags:
                                seen_tags.add(tag['name'])
                                filtered_tags.append(tag)
                    
                    # 如果没有指定 tag_patterns，保留所有标签
                    if not tag_patterns:
                        filtered_tags = tags
                    
                    logger.debug(f"过滤后剩余 {len(filtered_tags)} 个标签")
                    
                    # 按版本号语义排序（最新的版本在前）
                    tags_sorted = sort_tags_by_version(filtered_tags, logger)
                    
                    # 收集所有版本信息
                    versions = []
                    for tag in tags_sorted:
                        # 对于 GHCR 源镜像，源和目标都是 GHCR 地址
                        full_source = f"{normalize_source_image(image_name)}:{tag['name']}"
                        versions.append({
                            'version': tag['name'],
                            'digest': tag.get('digest', ''),
                            'created_at': tag.get('created_at'),
                            'synced_at': tag.get('created_at'),
                            'target': full_source,
                            'source': full_source,
                            'size': tag.get('size', ''),
                            'layers': tag.get('layers', 0)
                        })
                    
                    if sync_all:
                        version_names = [v['version'] for v in versions]
                        retained_names = apply_retention_strategy(
                            version_names,
                            strategy,
                            max_versions,
                            major_versions,
                            keep_minor_versions
                        )
                        versions = [v for v in versions if v['version'] in retained_names]
                    else:
                        versions = [v for v in versions if v['version'] == current_version]
                    
                    if versions:
                        if sync_all:
                            versions.sort(key=lambda x: retained_names.index(x['version']) if x['version'] in retained_names else len(retained_names))
                    
                    total_versions += len(versions)
                    
                    # 添加镜像信息（包含所有版本）
                    image_info = {
                        'name': image_name,
                        'description': description,
                        'repository': source_repo_name,
                        'total_versions': len(versions),
                        'latest_version': versions[0]['version'] if versions else None,
                        'updated': versions[0]['created_at'] if versions else '',
                        'size': versions[0]['size'] if versions else '',
                        'layers': versions[0]['layers'] if versions else 0,
                        'stars': 0,
                        'platforms': ['AMD64', 'ARM64'],
                        'versions': versions
                    }
                    # 添加中文描述
                    image_info = add_chinese_description(image_info)
                    images.append(image_info)
                    
                    print(f"   ✅ 找到 {len(versions)} 个版本")
                    print(f"   📌 最新版本: {versions[0]['version'] if versions else 'N/A'}")
                else:
                    print(f"   ⚠️  未找到任何标签")
                    logger.warning(f"GHCR 仓库 {source_owner}/{source_repo_name} 可能不存在或需要认证")
            else:
                print(f"   ⚠️  无法解析 GHCR 源镜像: {source}")
                logger.warning(f"GHCR 源镜像格式不正确: {source}")
        else:
            # 对于非 GHCR 源镜像，从目标仓库获取标签信息
            # 使用新的命名规则转换为 GHCR 路径（移除域名前缀）
            # 示例: docker.io/library/elasticsearch -> library/elasticsearch
            ghcr_path = convert_to_ghcr_path(image_name)
            
            # 获取 GHCR 中的所有标签信息
            # GitHub API 使用带斜杠的包名路径（不是双下划线）
            print(f"\n🔍 获取 {owner}/{ghcr_path} 的所有标签...")
            logger.debug(f"完整镜像路径: {registry}/{owner}/{ghcr_path}")
            logger.debug(f"原始源: {source}")
            logger.debug(f"标签匹配模式: {tag_patterns}")
            logger.debug(f"排除模式: {exclude_pattern}")
            tags = ghcr_api.get_repository_tags(owner, ghcr_path)
            
            if tags:
                logger.debug(f"找到 {len(tags)} 个标签")
                
                # 根据多个 tag_patterns 和 exclude_pattern 过滤标签
                # 合并多个 pattern 的结果（OR 逻辑）
                filtered_tags = []
                seen_tags = set()
                for pattern in tag_patterns:
                    batch = filter_tags_by_pattern(
                        tags,
                        tag_pattern=pattern,
                        exclude_pattern=exclude_pattern,
                        logger=logger
                    )
                    for tag in batch:
                        if tag['name'] not in seen_tags:
                            seen_tags.add(tag['name'])
                            filtered_tags.append(tag)
                
                # 如果没有指定 tag_patterns，保留所有标签
                if not tag_patterns:
                    filtered_tags = tags
                
                logger.debug(f"过滤后剩余 {len(filtered_tags)} 个标签")
                
                # 按版本号语义排序（最新的版本在前）
                tags_sorted = sort_tags_by_version(filtered_tags, logger)
                
                # 收集所有版本信息
                versions = []
                for tag in tags_sorted:
                    # 生成完整的源镜像地址
                    full_source = f"{normalize_source_image(image_name)}:{tag['name']}"
                    # 使用新的命名规则生成目标镜像地址（带斜杠格式，更友好）
                    target_image = f"{registry}/{owner}/{ghcr_path}:{tag['name']}"
                    versions.append({
                        'version': tag['name'],
                        'digest': tag.get('digest', ''),
                        'created_at': tag.get('created_at'),
                        'synced_at': tag.get('created_at'),
                        'target': target_image,
                        'source': full_source,
                        'size': tag.get('size', ''),
                        'layers': tag.get('layers', 0)
                    })
                
                if sync_all:
                    version_names = [v['version'] for v in versions]
                    retained_names = apply_retention_strategy(
                        version_names,
                        strategy,
                        max_versions,
                        major_versions,
                        keep_minor_versions
                    )
                    versions = [v for v in versions if v['version'] in retained_names]
                else:
                    versions = [v for v in versions if v['version'] == current_version]
                
                if versions:
                    if sync_all:
                        versions.sort(key=lambda x: retained_names.index(x['version']) if x['version'] in retained_names else len(retained_names))
                
                total_versions += len(versions)
                
                # 添加镜像信息（包含所有版本）
                image_info = {
                    'name': image_name,
                    'description': description,
                    'repository': ghcr_path,
                    'total_versions': len(versions),
                    'latest_version': versions[0]['version'] if versions else None,
                    'updated': versions[0]['created_at'] if versions else '',
                    'size': versions[0]['size'] if versions else '',
                    'layers': versions[0]['layers'] if versions else 0,
                    'stars': 0,
                    'platforms': ['AMD64', 'ARM64'],
                    'versions': versions
                }
                # 添加中文描述
                image_info = add_chinese_description(image_info)
                images.append(image_info)
                
                print(f"   ✅ 找到 {len(versions)} 个版本")
                print(f"   📌 最新版本: {versions[0]['version'] if versions else 'N/A'}")
            else:
                print(f"   ⚠️  未找到任何标签")
                logger.warning(f"仓库 {owner}/{ghcr_path} 可能不存在或需要认证")
    
    failed_images_data = []
    for failed in failed_images:
        failed_info = {
            'name': failed.get('name', ''),
            'source': failed.get('source', ''),
            'target': failed.get('target', ''),
            'version': failed.get('version', ''),
            'description': failed.get('description', ''),
            'sync_status': 'failed',
            'failed_at': datetime.now(timezone.utc).isoformat()
        }
        # 添加中文描述
        failed_info = add_chinese_description(failed_info)
        failed_images_data.append(failed_info)
    
    output_data = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'registry': registry,
        'owner': owner,
        'total_images': len(images),
        'total_versions': total_versions,
        'total_failed': len(failed_images_data),
        'images': images,
        'failed_images': failed_images_data
    }
    
    # 保存到文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 已生成 {output_file}")
    print(f"📊 总计: {len(images)} 个镜像成功，{total_versions} 个版本")
    if failed_images_data:
        print(f"❌ 失败: {len(failed_images_data)} 个镜像")
    
    return output_data


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='从 GHCR 生成镜像列表 JSON')
    parser.add_argument('--owner',
                       type=str,
                       required=True,
                       help='GitHub 仓库所有者')
    parser.add_argument('--registry',
                       type=str,
                       default='ghcr.io',
                       help='镜像仓库地址 (默认: ghcr.io)')
    parser.add_argument('--manifest',
                       type=Path,
                       default=project_root / 'images-manifest.yml',
                       help='清单文件路径')
    parser.add_argument('--output',
                       type=Path,
                       default=project_root / 'images.json',
                       help='输出文件路径')
    parser.add_argument('--token',
                       type=str,
                       help='GitHub Personal Access Token (可选)')
    parser.add_argument('-D', '--debug',
                       action='store_true',
                       help='启用调试模式')
    
    args = parser.parse_args()
    
    logger = setup_logger('generate', args.debug, project_root / 'logs')
    
    try:
        generate_images_json(
            args.manifest,
            args.output,
            args.registry,
            args.owner,
            args.token,
            logger
        )
        sys.exit(0)
    except Exception as e:
        logger.error(f"生成镜像列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
