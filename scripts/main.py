#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker 镜像同步工具 - 主入口
支持镜像同步、版本更新、JSON生成
"""

import sys
import argparse
from pathlib import Path

if sys.platform == 'win32':
    import codecs
    try:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except Exception:
        pass

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from scripts.utils import load_env_files
    load_env_files(project_root)
except Exception:
    pass


def show_help():
    """显示帮助信息"""
    help_text = """
================================================================================
                    Docker Hub Mirror - 命令行工具
================================================================================

【项目简介】
Docker 镜像同步工具，将 Docker Hub、GCR、Quay 等镜像同步到 GHCR。

【项目结构】
项目根目录/
├── index.html           # Web 前端入口
├── css/                 # 样式文件
├── js/                  # JavaScript 文件
├── images.json          # 镜像列表数据
├── images-manifest.yml  # 镜像清单配置
├── package.json         # Node.js 配置
├── startup.sh           # 一键启动脚本
└── scripts/             # Python 脚本目录
    ├── main.py          # Python 主入口
    ├── requirements.txt # Python 依赖
    ├── api/             # API 客户端模块
    ├── core/            # 核心业务逻辑
    ├── cli/             # CLI 命令处理
    └── utils/           # 工具函数

【可用命令】

1. 镜像同步命令 (sync):
   python scripts/main.py sync --owner <owner> [--registry ghcr.io]
   
   参数: --owner, --registry, --max-workers, --max-retries, --retry-delay

2. 更新清单命令 (update):
   python scripts/main.py update [--dry-run]
   
   参数: --dry-run, --max-workers

3. 完整流程命令 (run):
   python scripts/main.py run --owner <owner>
   
   执行顺序: update -> sync

4. 生成JSON命令 (generate):
   python scripts/main.py generate --owner <owner>

5. 显示帮助 (help):
   python scripts/main.py help

6. 清理旧镜像 (cleanup):
   python scripts/main.py cleanup --owner <owner>
   python scripts/main.py cleanup --owner <owner> --force  # 实际执行删除

【使用示例】

# 更新镜像清单
python scripts/main.py update

# 同步镜像到 GHCR
python scripts/main.py sync --owner freemankevin

# 完整流程
python scripts/main.py run --owner freemankevin

【前端开发】

# 启动前端开发服务器
./startup.sh
# 或
npm run start

【环境变量】
GHCR_TOKEN           GitHub Personal Access Token
DOCKER_HUB_USERNAME  Docker Hub 用户名 (可选)
DOCKER_HUB_TOKEN     Docker Hub Token (可选)

================================================================================
"""
    print(help_text)


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description='Docker 镜像同步工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False
    )
    
    parser.add_argument('command', nargs='?', default='help',
                        help='可用命令: sync, update, run, generate, help')
    parser.add_argument('-h', '--help', action='store_true',
                        help='显示帮助信息')
    parser.add_argument('-D', '--debug', action='store_true',
                        help='启用调试模式')
    
    try:
        args, remaining = parser.parse_known_args()
    except SystemExit:
        return 1
    
    if args.help or args.command == 'help':
        show_help()
        return 0
    
    command_map = {
        'sync': 'scripts.cli.cli:cmd_sync',
        'update': 'scripts.cli.cli:cmd_update',
        'run': 'scripts.cli.cli:cmd_run',
        'generate': 'scripts.core.generate_images_json:main',
        'cleanup': 'scripts.cli.cli:cmd_cleanup',
    }
    
    if args.command not in command_map:
        print(f"❌ 未知命令: {args.command}")
        print("💡 使用 'python scripts/main.py help' 查看可用命令")
        return 1
    
    module_path, func_name = command_map[args.command].split(':')
    import importlib
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    
    new_args = argparse.Namespace(command=args.command, debug=args.debug)
    for arg in remaining:
        if arg.startswith('--'):
            key = arg.lstrip('-').replace('-', '_')
            if '=' in arg:
                key, value = key.split('=')
            else:
                value = True
            setattr(new_args, key, value)
    
    return func(new_args)


if __name__ == "__main__":
    sys.exit(main())