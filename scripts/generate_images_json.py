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
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.ghcr_api import GHCRRegistryAPI
from scripts.utils import setup_logger


def normalize_source_image(image_name: str) -> str:
    """规范化镜像名称，添加完整的仓库地址前缀
    
    Args:
        image_name: 镜像名称，如 'nginx', 'kartoza/geoserver', 'library/nginx', 'ghcr.io/freemankevin/network-tools'
        
    Returns:
        规范化后的镜像名称，如 'docker.io/library/nginx', 'docker.io/kartoza/geoserver', 'ghcr.io/freemankevin/network-tools'
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
    logger=None
) -> Dict:
    """从 GHCR 生成镜像列表 JSON（包含所有版本）
    
    Args:
        manifest_file: 清单文件路径
        output_file: 输出文件路径
        registry: 镜像仓库地址
        owner: 仓库所有者
        token: GitHub Personal Access Token (可选)
        logger: 日志记录器
        
    Returns:
        生成的镜像数据
    """
    if not logger:
        logger = setup_logger('generate', False, project_root / 'logs')
    
    # 加载清单文件
    with open(manifest_file, 'r', encoding='utf-8') as f:
        manifest = yaml.safe_load(f)
    
    # 初始化 GHCR API 客户端
    ghcr_api = GHCRRegistryAPI(logger, token)
    
    # 收集所有镜像信息
    images = []
    total_versions = 0
    
    for img in manifest.get('images', []):
        if not img.get('enabled', True):
            continue
        
        source = img['source']
        description = img.get('description', '')
        tag_pattern = img.get('tag_pattern')
        exclude_pattern = img.get('exclude_pattern')
        
        # 提取镜像名和版本
        if ':' in source:
            image_name, version = source.rsplit(':', 1)
        else:
            image_name = source
            version = 'latest'
        
        # 检查源镜像是否来自 GHCR
        is_ghcr_source = source.startswith('ghcr.io/')
        
        if is_ghcr_source:
            # 对于 GHCR 源镜像，直接从源镜像获取标签信息
            # 提取 GHCR 仓库的所有者和仓库名
            # 格式: ghcr.io/{owner}/{repo}:{tag}
            parts = source.replace('ghcr.io/', '').split('/')
            if len(parts) >= 2:
                source_owner = parts[0]
                # 剩余部分是仓库名（可能包含斜杠），需要将斜杠替换为双下划线
                source_repo = '/'.join(parts[1:]).split(':')[0]
                source_repo_name = source_repo.replace('/', '__')
                
                print(f"\n🔍 获取 GHCR 源镜像 {source_owner}/{source_repo_name} 的所有标签...")
                logger.debug(f"原始源: {source}")
                logger.debug(f"标签匹配模式: {tag_pattern}")
                logger.debug(f"排除模式: {exclude_pattern}")
                tags = ghcr_api.get_repository_tags(source_owner, source_repo_name)
                
                if tags:
                    logger.debug(f"找到 {len(tags)} 个标签")
                    
                    # 根据 tag_pattern 和 exclude_pattern 过滤标签
                    filtered_tags = filter_tags_by_pattern(
                        tags,
                        tag_pattern=tag_pattern,
                        exclude_pattern=exclude_pattern,
                        logger=logger
                    )
                    
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
                            'target': full_source,  # GHCR 源镜像本身就是目标
                            'source': full_source,
                            'size': tag.get('size', ''),  # 镜像大小
                            'layers': tag.get('layers', 0)  # 层数
                        })
                    
                    total_versions += len(versions)
                    
                    # 添加镜像信息（包含所有版本）
                    images.append({
                        'name': image_name,
                        'description': description,
                        'repository': source_repo_name,
                        'total_versions': len(versions),
                        'latest_version': versions[0]['version'] if versions else None,
                        'updated': versions[0]['created_at'] if versions else '',  # 更新时间
                        'size': versions[0]['size'] if versions else '',  # 最新版本大小
                        'layers': versions[0]['layers'] if versions else 0,  # 层数
                        'stars': 0,  # 星标数（暂不支持）
                        'platforms': ['AMD64', 'ARM64'],  # 支持的平台
                        'versions': versions
                    })
                    
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
            # 转换为 GHCR 仓库名
            repo_name = image_name.replace('/', '__')
            
            # 获取 GHCR 中的所有标签信息
            print(f"\n🔍 获取 {owner}/{repo_name} 的所有标签...")
            logger.debug(f"完整镜像路径: {registry}/{owner}/{repo_name}")
            logger.debug(f"原始源: {source}")
            logger.debug(f"标签匹配模式: {tag_pattern}")
            logger.debug(f"排除模式: {exclude_pattern}")
            tags = ghcr_api.get_repository_tags(owner, repo_name)
            
            if tags:
                logger.debug(f"找到 {len(tags)} 个标签")
                
                # 根据 tag_pattern 和 exclude_pattern 过滤标签
                filtered_tags = filter_tags_by_pattern(
                    tags,
                    tag_pattern=tag_pattern,
                    exclude_pattern=exclude_pattern,
                    logger=logger
                )
                
                logger.debug(f"过滤后剩余 {len(filtered_tags)} 个标签")
                
                # 按版本号语义排序（最新的版本在前）
                tags_sorted = sort_tags_by_version(filtered_tags, logger)
                
                # 收集所有版本信息
                versions = []
                for tag in tags_sorted:
                    # 生成完整的源镜像地址
                    full_source = f"{normalize_source_image(image_name)}:{tag['name']}"
                    versions.append({
                        'version': tag['name'],
                        'digest': tag.get('digest', ''),
                        'created_at': tag.get('created_at'),
                        'synced_at': tag.get('created_at'),  # 使用创建时间作为同步时间
                        'target': f"{registry}/{owner}/{repo_name}:{tag['name']}",
                        'source': full_source,
                        'size': tag.get('size', ''),  # 镜像大小
                        'layers': tag.get('layers', 0)  # 层数
                    })
                
                total_versions += len(versions)
                
                # 添加镜像信息（包含所有版本）
                images.append({
                    'name': image_name,
                    'description': description,
                    'repository': repo_name,
                    'total_versions': len(versions),
                    'latest_version': versions[0]['version'] if versions else None,
                    'updated': versions[0]['created_at'] if versions else '',  # 更新时间
                    'size': versions[0]['size'] if versions else '',  # 最新版本大小
                    'layers': versions[0]['layers'] if versions else 0,  # 层数
                    'stars': 0,  # 星标数（暂不支持）
                    'platforms': ['AMD64', 'ARM64'],  # 支持的平台
                    'versions': versions
                })
                
                print(f"   ✅ 找到 {len(versions)} 个版本")
                print(f"   📌 最新版本: {versions[0]['version'] if versions else 'N/A'}")
            else:
                print(f"   ⚠️  未找到任何标签")
                logger.warning(f"仓库 {owner}/{repo_name} 可能不存在或需要认证")
    
    # 生成输出数据
    output_data = {
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'registry': registry,
        'owner': owner,
        'total_images': len(images),
        'total_versions': total_versions,
        'images': images
    }
    
    # 保存到文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 已生成 {output_file}")
    print(f"📊 总计: {len(images)} 个镜像，{total_versions} 个版本")
    
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
