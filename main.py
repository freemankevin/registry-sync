#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker 镜像同步工具 - 主入口
"""

import sys

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

from scripts.cli import main

if __name__ == "__main__":
    sys.exit(main())