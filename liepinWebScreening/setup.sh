#!/bin/bash
# ==========================================
# 猎聘智能简历筛选系统 — 一键安装脚本
# ==========================================

set -e

echo "========================================"
echo "  猎聘智能简历筛选系统 — 安装"
echo "========================================"
echo ""

# 1. 检查 Python
echo "[1/5] 检查 Python..."
python3 --version || { echo "❌ 需要 Python 3.10+"; exit 1; }

# 2. 安装依赖
echo "[2/5] 安装 Python 依赖..."
pip install -r requirements.txt --break-system-packages

# 3. 安装 Playwright 浏览器
echo "[3/5] 安装 Playwright Chromium 浏览器..."
playwright install chromium

# 4. 创建目录结构
echo "[4/5] 创建数据目录..."
mkdir -p data/{cookies,resumes,results,reports,logs,jd,sessions}

# 5. .env 文件
if [ ! -f .env ]; then
    echo "[5/5] 创建 .env 配置文件..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件，填入你的 DeepSeek API Key"
else
    echo "[5/5] .env 已存在，跳过"
fi

echo ""
echo "========================================"
echo "  ✅ 安装完成!"
echo "========================================"
echo ""
echo "首次使用步骤："
echo "  1. 编辑 .env 填入 DEEPSEEK_API_KEY"
echo "  2. 运行: python main.py survey --url '你的搜索结果URL'"
echo "     → 将输出粘贴到 config.py 的 LIEPIN 配置中"
echo "  3. 运行: python main.py login"
echo "     → 扫码登录猎聘 HR 后台"
echo "  4. 运行: python main.py run --search-url 'URL' --jd-text 'JD描述'"
echo ""
echo "详细文档: docs/setup_guide.md"
echo ""
