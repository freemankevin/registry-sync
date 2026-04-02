#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地开发服务器 - 支持 Docker Sync Engine 前端开发
"""

import http.server
import socketserver
import os
from pathlib import Path
from urllib.parse import unquote

PORT = 7886
PROJECT_ROOT = Path(__file__).parent

class DevHandler(http.server.SimpleHTTPRequestHandler):
    """开发服务器处理器 - 模拟 Vercel 的 URL 映射规则"""
    
    def translate_path(self, path):
        """重写路径以符合项目结构"""
        path = unquote(path.split('?',1)[0].split('#',1)[0])
        
        # 模拟 Vercel 的 rewrites 规则
        if path == '/images.json':
            return str(PROJECT_ROOT / 'images.json')
        elif path.startswith('/css/'):
            return str(PROJECT_ROOT / 'web' / path.lstrip('/'))
        elif path.startswith('/js/'):
            return str(PROJECT_ROOT / 'web' / path.lstrip('/'))
        elif path == '/' or not Path(PROJECT_ROOT / 'web' / path.lstrip('/')).exists():
            # 默认指向 index.html
            return str(PROJECT_ROOT / 'web' / 'index.html')
        else:
            return str(PROJECT_ROOT / 'web' / path.lstrip('/'))
    
    def end_headers(self):
        """添加必要的 CORS 头和缓存控制"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        if self.path == '/images.json':
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"\033[36m[Dev Server]\033[0m {format % args}")

def main():
    """启动开发服务器"""
    os.chdir(PROJECT_ROOT)
    
    with socketserver.TCPServer(("", PORT), DevHandler) as httpd:
        print(f"\n{'='*60}")
        print(f"🚀 Docker Sync Engine 开发服务器")
        print(f"{'='*60}")
        print(f"📁 项目目录: {PROJECT_ROOT}")
        print(f"🔗 访问地址: http://localhost:{PORT}")
        print(f"{'='*60}")
        print("✨ 特性:")
        print("   • 自动处理 /images.json -> ./images.json")
        print("   • 自动处理 /css/* -> ./web/css/*")
        print("   • 自动处理 /js/* -> ./web/js/*")
        print("   • 其他路径 -> ./web/index.html")
        print("   • 支持 CORS 跨域请求")
        print(f"{'='*60}\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n⚠️  服务器已停止")

if __name__ == '__main__':
    main()
