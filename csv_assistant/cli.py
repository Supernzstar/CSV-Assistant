#!/usr/bin/env python3
import os
import sys
import webbrowser
from pathlib import Path
import uvicorn

def main():
    # 确保在项目根目录
    project_dir = Path(__file__).parent
    os.chdir(project_dir)

    # 检查前端构建产物是否存在
    dist_dir = project_dir / "frontend" / "dist"
    print("正在构建前端...")
    # 确保 node_modules 存在
    if not (project_dir / "frontend" / "node_modules").exists():
        os.system("cd frontend && npm install")
    # 构建前端
    build_result = os.system("cd frontend && npm run build")
    if build_result != 0:
        print("前端构建失败！")
        sys.exit(1)
    print("前端构建完成！")

    # 再次检查构建产物
    if not dist_dir.exists() or not (dist_dir / "index.html").exists():
        print("错误：前端构建产物不存在！")
        sys.exit(1)

    # 启动服务器
    port = int(os.getenv("API_PORT", "8000"))
    print(f"启动服务器在 http://127.0.0.1:{port}")
    
    # 自动打开浏览器
    webbrowser.open(f"http://127.0.0.1:{port}")
    
    # 启动 FastAPI
    uvicorn.run(
        "api_server:app",
        host="127.0.0.1",
        port=port,
        reload=True,
    )

if __name__ == "__main__":
    main() 