#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
镜像描述翻译工具
"""

IMAGE_DESCRIPTION_ZH = {
    'amazoncorretto': 'Amazon 官方维护的 OpenJDK 发行版（Amazon Linux 2023）',
    'elasticsearch': '分布式、RESTful 搜索和分析引擎',
    'nacos-server': '动态服务发现、配置和服务管理平台',
    'nginx': '官方构建的高性能 HTTP 和反向代理服务器',
    'rabbitmq': '开源消息代理软件，支持多种消息协议',
    'redis': '高性能内存数据结构存储，用作数据库、缓存和消息代理',
    'geoserver': '开源地理信息系统服务器',
    'postgresql-postgis': 'PostgreSQL 数据库，包含 PostGIS 空间数据扩展',
    'postgresql-backup': 'PostgreSQL 数据库备份工具',
    'harbor-export': 'Harbor 镜像仓库指标导出器',
    'harbor-export-ui': 'Harbor 镜像仓库指标导出器 UI',
    'java-local': 'Java 开发环境，包含常用工具',
    'python-local': 'Python 开发环境，包含 PyTorch',
    'netkit': '容器化环境的网络诊断工具集（curl、wget、ping、nslookup、dig、telnet、nc、tcpdump）',
    'freemankevin': '个人 GitHub Pages 站点容器',
    'etcd': '分布式键值存储，用于共享配置和服务发现',
    'minio': '高性能对象存储服务器，兼容 Amazon S3 API',
}

def translate_description(description: str, image_name: str = '') -> str:
    if not description:
        return ''
    
    if image_name in IMAGE_DESCRIPTION_ZH:
        return IMAGE_DESCRIPTION_ZH[image_name]
    
    if '/' in image_name:
        short_name = image_name.split('/')[-1]
        if short_name in IMAGE_DESCRIPTION_ZH:
            return IMAGE_DESCRIPTION_ZH[short_name]
    
    return ''

def add_chinese_description(image_data: dict) -> dict:
    description = image_data.get('description', '')
    image_name = image_data.get('name', '')
    
    description_zh = translate_description(description, image_name)
    
    if description_zh:
        image_data['description_zh'] = description_zh
    
    return image_data