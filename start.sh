#!/bin/bash

# 定义项目路径 (请确保这是你真实的路径)
PROJECT_DIR="/www/wwwroot/tg_monitor"

# 进入项目目录
cd $PROJECT_DIR

# 1. 清理旧进程 (防止重复启动)
echo "🧹 正在清理旧进程..."
# 杀掉占用 7000 端口的主程序
fuser -k 7000/tcp > /dev/null 2>&1
# 杀掉 worker 进程
pkill -f "python worker.py" > /dev/null 2>&1

# 等待 1 秒确保释放
sleep 1

# 2. 启动主程序 (Web + Bot)
echo "🚀 正在启动主程序 (Main)..."
# nohup: 后台运行, > main.log: 日志写入文件, &: 立即返回终端
nohup python main.py > main.log 2>&1 &

# 3. 启动监听进程 (Worker)
echo "🛰 正在启动监听进程 (Worker)..."
nohup python worker.py > worker.log 2>&1 &

echo "---------------------------------------"
echo "✅ 所有服务已在后台启动！"
echo "🌐 Web后台: http://你的服务器IP:7000"
echo "📄 查看主程序日志: tail -f main.log"
echo "📄 查看监听日志:   tail -f worker.log"
echo "---------------------------------------"
nohup python payment_monitor.py > payment.log 2>&1 &