#!/bin/bash

echo "🛑 正在停止所有 TG 监控服务..."

# 1. 杀掉 Web/Main
fuser -k 7000/tcp > /dev/null 2>&1
echo "- 主程序 (Main) 已停止"

# 2. 杀掉 Worker
pkill -f "python worker.py" > /dev/null 2>&1
echo "- 监听进程 (Worker) 已停止"

echo "✅ 全部停止完毕。"