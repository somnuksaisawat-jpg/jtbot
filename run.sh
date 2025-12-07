#!/bin/bash
echo ">>> 安装依赖..."
# 确保安装了 Redis 库
pip install -r requirements.txt

echo ">>> 启动 SaaS 系统..."
python main.py