#!/bin/bash
#
# AI简历筛选系统 - 部署脚本
# 用法: cd 项目目录 && sudo bash deploy.sh
# 部署在脚本所在目录（无需提前指定路径）
#

set -e

# 项目根目录 = 脚本所在目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "========================================"
echo "  AI简历筛选系统 - 部署"
echo "  目录: $PROJECT_DIR"
echo "========================================"

# 1. 检查 Python3
echo "[1/7] 检查 Python3..."
if ! command -v python3 &> /dev/null; then
    echo "安装 Python3..."
    yum install -y python3 python3-pip python3-devel gcc
fi

# 2. 创建必要目录
echo "[2/7] 创建项目目录..."
mkdir -p logs reports temp

# 3. 创建 Python 虚拟环境
echo "[3/7] 创建 Python 虚拟环境..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate

# 4. 设置权限
echo "[4/7] 设置权限..."
chmod 750 "$PROJECT_DIR"
chmod 640 config.yaml
chmod 750 jds logs reports temp

# 5. 安装 PM2
echo "[5/7] 安装 PM2..."
if ! command -v node &> /dev/null; then
    echo "安装 Node.js..."
    curl -sL https://rpm.nodesource.com/setup_20.x | bash -
    yum install -y nodejs
fi

if ! command -v pm2 &> /dev/null; then
    npm install -g pm2
fi

# 6. 配置开机自启
echo "[6/7] 配置开机自启..."
pm2 startup systemd -u root --hp /root 2>/dev/null || true

# 7. 启动应用
echo "[7/7] 启动应用..."
pm2 start ecosystem.config.js
pm2 save

echo ""
echo "========================================"
echo "  部署完成！"
echo "========================================"
echo ""
echo "  PM2 管理 (在项目目录下运行):"
echo "  pm2 status               查看状态"
echo "  pm2 logs resume-filter   查看日志"
echo "  pm2 restart resume-filter  重启"
echo "  pm2 stop resume-filter   停止"
echo ""
echo "  首次使用前需要："
echo "  1. 编辑配置:  vi config.yaml"
echo "  2. 设置 Key:  export DEEPSEEK_API_KEY='sk-xxx'"
echo "  3. 添加 JD:   vi jds/frontend_engineer.md"
echo "  4. 手动测试:  venv/bin/python main.py"
echo ""
