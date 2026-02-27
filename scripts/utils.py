#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用工具函数
"""

import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Tuple

# ANSI 颜色代码
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_BLUE = "\033[94m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"


def parse_image_name(image: str) -> Tuple[str, str, str]:
    """解析镜像名称，提取仓库主机名、命名空间和镜像名
    
    Args:
        image: 镜像地址，如 'docker.io/library/elasticsearch:9.3.1' 或 
               'gcr.io/kubeflow-images-public/katib/v1beta1/katib-controller:v0.9.0'
    
    Returns:
        Tuple[registry_host, namespace, image_name]:
        - registry_host: 仓库主机名，如 'docker.io', 'gcr.io', 'quay.io'
        - namespace: 命名空间路径，如 'library', 'kubeflow-images-public/katib/v1beta1'
        - image_name: 镜像名称，如 'elasticsearch', 'katib-controller'
    """
    # 移除标签部分
    if ':' in image:
        image = image.rsplit(':', 1)[0]
    
    # 检测仓库类型
    if image.startswith('docker.io/'):
        registry = 'docker.io'
        path = image[len('docker.io/'):]
    elif image.startswith('gcr.io/'):
        registry = 'gcr.io'
        path = image[len('gcr.io/'):]
    elif image.startswith('quay.io/'):
        registry = 'quay.io'
        path = image[len('quay.io/'):]
    elif image.startswith('ghcr.io/'):
        registry = 'ghcr.io'
        path = image[len('ghcr.io/'):]
    elif image.startswith('registry.k8s.io/'):
        registry = 'registry.k8s.io'
        path = image[len('registry.k8s.io/'):]
    else:
        # 默认为 docker.io，且可能是官方镜像（无斜杠）或用户镜像
        registry = 'docker.io'
        if '/' not in image:
            # 官方镜像，添加 library 前缀
            path = f'library/{image}'
        else:
            path = image
    
    # 分割路径，提取命名空间和镜像名
    parts = path.split('/')
    if len(parts) >= 2:
        namespace = '/'.join(parts[:-1])
        name = parts[-1]
    else:
        namespace = ''
        name = parts[0]
    
    return registry, namespace, name


def convert_to_ghcr_path(image: str) -> str:
    """将源镜像名称转换为 GHCR 路径格式
    
    新的命名规则：
    - 将源仓库的主机名中的 '.' 替换为 '-' (docker.io -> docker-io, gcr.io -> gcr-io)
    - 保持命名空间结构，使用 '/' 分隔
    - 这样既能区分来源仓库，又能保持简洁的命名结构
    
    Args:
        image: 源镜像地址，如 'docker.io/library/elasticsearch:9.3.1'
    
    Returns:
        GHCR 路径部分，如 'docker-io/library/elasticsearch'
    
    示例：
        - docker.io/library/elasticsearch:9.3.1 -> docker-io/library/elasticsearch
        - gcr.io/kubeflow-images-public/katib/v1beta1/katib-controller:v0.9.0 
          -> gcr-io/kubeflow-images-public/katib/v1beta1/katib-controller
        - quay.io/prometheus/prometheus:v3.10.0 -> quay-io/prometheus/prometheus
        - registry.k8s.io/pause:3.9 -> registry-k8s-io/pause
    """
    registry, namespace, name = parse_image_name(image)
    
    # 将主机名中的 '.' 替换为 '-'
    registry_normalized = registry.replace('.', '-')
    
    # 构建 GHCR 路径
    if namespace:
        return f"{registry_normalized}/{namespace}/{name}"
    else:
        return f"{registry_normalized}/{name}"


def get_ghcr_image_name(source_image: str, owner: str, tag: str = None) -> str:
    """生成完整的 GHCR 镜像名称
    
    Args:
        source_image: 源镜像地址
        owner: GHCR 仓库所有者
        tag: 标签（可选，如果不提供则使用源镜像的标签）
    
    Returns:
        完整的 GHCR 镜像名称，如 'ghcr.io/freemankevin/docker-io/library/elasticsearch:9.3.1'
    """
    # 提取标签
    if tag is None:
        if ':' in source_image:
            _, tag = source_image.rsplit(':', 1)
        else:
            tag = 'latest'
    
    # 转换为 GHCR 路径
    ghcr_path = convert_to_ghcr_path(source_image)
    
    return f"ghcr.io/{owner}/{ghcr_path}:{tag}"


def load_env_files(project_root: Path = None) -> bool:
    """加载环境变量文件
    
    按以下顺序加载：
    1. .env.local (本地开发环境，优先级最高)
    2. .env (通用环境配置)
    
    Args:
        project_root: 项目根目录路径
        
    Returns:
        是否成功加载了任何环境变量文件
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        # python-dotenv 未安装
        return False
    
    if project_root is None:
        project_root = Path(__file__).parent.parent
    
    loaded = False
    
    # 按优先级顺序加载 .env 文件
    env_files = ['.env.local', '.env']
    
    for env_file in env_files:
        env_path = project_root / env_file
        if env_path.exists():
            # override=False 确保已存在的环境变量（如系统环境变量）不会被覆盖
            load_dotenv(dotenv_path=env_path, override=False)
            loaded = True
            # 打印调试信息（仅用于排查问题）
            # print(f"[DEBUG] Loaded env file: {env_path}")
    
    return loaded


def get_env_variable(name: str, default: str = None, required: bool = False) -> str:
    """获取环境变量，支持调试输出
    
    Args:
        name: 环境变量名称
        default: 默认值
        required: 是否为必需变量
        
    Returns:
        环境变量值或默认值
    """
    import os
    value = os.environ.get(name, default)
    
    if required and not value:
        raise ValueError(f"Required environment variable '{name}' is not set")
    
    return value


def setup_logger(name: str, debug: bool = False, log_dir: Path = None) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.handlers.clear()
    
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    
    # 控制台处理器（带颜色）
    formatter = logging.Formatter(
        f'{COLOR_CYAN}%(asctime)s{COLOR_RESET} - '
        f'{COLOR_YELLOW}%(levelname)s{COLOR_RESET} - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（无颜色）
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    logger.propagate = False
    return logger