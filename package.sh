#!/bin/bash

# --- 配置 ---
PROJECT_DIR="/www/wwwroot/tg_monitor"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_$TIMESTAMP.zip"
STATIC_DIR="$PROJECT_DIR/web/static"
DB_FILE="db_full_backup.sql"

# 获取 IP (用于生成链接)
SERVER_IP=$(curl -s ifconfig.me)

cd $PROJECT_DIR

echo "📦 开始打包项目..."

# 1. 导出数据库 (需要读取 .env 里的配置，这里简单假设是用 monitor 用户)
# 如果提示输入密码，请输入数据库密码
echo ">> 正在导出数据库结构与数据..."
# 尝试从 .env 读取数据库配置
DB_USER=$(grep DB_USER .env | cut -d '=' -f2)
DB_NAME=$(grep DB_NAME .env | cut -d '=' -f2)
# 导出
PGPASSWORD=$(grep DB_PASSWORD .env | cut -d '=' -f2) pg_dump -h 127.0.0.1 -U $DB_USER $DB_NAME > $DB_FILE

if [ $? -eq 0 ]; then
    echo "✅ 数据库导出成功: $DB_FILE"
else
    echo "⚠️ 数据库导出失败 (可能是密码错误或pg_dump未安装)，跳过DB备份..."
fi

# 2. 安装 zip 工具 (如果没装)
if ! command -v zip &> /dev/null; then
    echo ">> 安装 zip 工具..."
    apt-get update && apt-get install -y zip
fi

# 3. 压缩文件
echo ">> 正在压缩文件 (排除 venv 和日志)..."
# 排除 venv, __pycache__, logs, session文件, 旧的zip
zip -r $BACKUP_NAME . \
    -x "venv/*" \
    -x "__pycache__/*" \
    -x "*.log" \
    -x "*.session*" \
    -x "*.session-journal" \
    -x "backup_*.zip" \
    -x ".git/*"

# 4. 移动到静态资源目录 (以便下载)
mv $BACKUP_NAME $STATIC_DIR/

# 5. 清理临时 SQL 文件
rm -f $DB_FILE

echo ""
echo "========================================================"
echo "🎉 打包完成！"
echo "📂 文件名: $BACKUP_NAME"
echo "🌍 下载地址: http://$SERVER_IP:7000/static/$BACKUP_NAME"
echo "========================================================"
echo "⚠️  注意: 下载完成后，建议删除该文件以防泄露配置！"
echo "👉 删除命令: rm $STATIC_DIR/$BACKUP_NAME"