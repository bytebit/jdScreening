# 猎聘智能简历筛选系统

一键连接你已打开搜索结果的 Edge，自动采集候选人 → 三阶段流水线分析 → 输出 Excel 报告。

---

## 快速开始（5 分钟）

### 第 1 步：安装

```bash
cd liepin-screener
pip install -r requirements.txt --break-system-packages
playwright install chromium
mkdir -p data/{cookies,resumes,results,reports,logs,jd,sessions}
# 在 .env 中填入 DeepSeek API Key（从 https://platform.deepseek.com 获取）
echo "DEEPSEEK_API_KEY=sk-你的Key" > .env
```

### 第 2 步：以调试模式启动 Edge

```bash
python -m collector.chrome_launcher
```

> 这会自动关闭已有的 Edge 和 Chrome，以调试模式重新启动 Edge。启动后浏览器右上角会显示 **"Edge 正由自动化测试软件控制"**，这是正常的调试模式标志。

### 第 3 步：登录猎聘并搜索

1. 在刚启动的 Edge 中访问 `https://lpt.liepin.com` → 扫码登录
2. 进入「人才搜索」→ 设好筛选条件（工作年限、学历、技能等）→ 点「搜索」
3. **保持这个标签页打开，不要关闭**

### 第 4 步：调查页面结构（首次必做）

```bash
python main.py survey
```

系统会自动连接到你打开的 Edge，分析搜索结果页的卡片结构和 API 请求模式，并输出推荐配置。将输出的选择器复制到 `config.py` 的 `LIEPIN` 字典中。

> 如果猎聘页面改版，重新运行 `survey` 即可，不需要改代码。

### 第 5 步：准备好 JD 描述

把岗位描述保存为一个文本文件（如 `jd.txt`），后续每次运行直接引用这个文件，不用反复粘贴：

```bash
# jd.txt 内容示例：
职位：高级Java工程师
学历要求：本科及以上
工作经验：3-5年
必备技能：Java、Spring Boot、MySQL、Redis
```

### 第 6 步：一键运行

```bash
python main.py run --jd-file jd.txt
```

系统会连接 Edge → 读取当前搜索页的候选人 → 自动翻页 → 规则引擎 + 语义匹配 + DeepSeek 深度分析 → 生成 Excel 报告。

---

## 使用方法

### 基础采集

```bash
# 采 30 份（卡片摘要信息）
python main.py collect --max 30
```

### 深度采集（推荐）

逐条打开每份简历的详情页，获取完整的教育经历、工作描述等信息：

```bash
python main.py collect --max 30 --deep
```

每采完一份立即写入 JSON 文件，不会等全部采完才保存。

### 采集 + 分析一步完成

```bash
# JD 描述写在命令行（简短时用）
python main.py run --jd-text "JD描述..." --max 30

# JD 描述写在文件里（推荐，方便复用）
python main.py run --jd-file jd.txt --max 30

# 带深度采集
python main.py run --jd-file jd.txt --max 30 --deep
```

### 更换 JD 重新分析已有缓存

```bash
python main.py analyze --jd-file jd_doc.txt --resume-dir data/resumes/liepin/20260616
```

### 重新生成报告

```bash
python main.py report --job-id "JD-xxx"
```

---

## 架构

```
你的 Edge（已打开猎聘搜索结果页）
    │ CDP 连接（无需重新登录，无需传 URL）
    ▼
Playwright 读取当前页 → 逐页采集候选人 → 可选深度采集详情
    │
    ▼
三阶段分析流水线：
  Stage 1: 规则引擎（零成本，筛 60-70%）
  Stage 2: 向量语义匹配（零成本，BGE 本地模型）
  Stage 3: DeepSeek 深度分析（仅对 Top 候选人）
    │
    ▼
Excel 报告（总览 + 详细评估）
```

---

## 命令速查

```bash
# 启动 Edge（调试模式）
python -m collector.chrome_launcher

# 调查页面结构（首次）
python main.py survey

# 仅采集
python main.py collect --max 30
python main.py collect --max 30 --deep    # 带深度详情

# 采集+分析+报告（推荐用 --jd-file）
python main.py run --jd-file jd.txt
python main.py run --jd-file jd.txt --deep        # 带深度采集

# 简短 JD 可以直接写 --jd-text
python main.py run --jd-text "JD描述..."

# 重新分析已有缓存
python main.py analyze --jd-file jd.txt --resume-dir data/resumes/liepin/20260616

# 生成报告
python main.py report --job-id "xxx"
```

---

## 常见问题

### Edge 连接失败（ECONNREFUSED）
→ Edge 没有以调试模式启动 → 运行 `python -m collector.chrome_launcher` 一键启动

### 找不到猎聘标签页
→ 确认 Edge 中已打开猎聘并点过搜索，标签页没有关闭

### 采集到 0 份简历
→ 去猎聘页面上确认搜索条件能搜出候选人，把条件放宽试试

### DeepSeek 报错
→ 检查 `.env` 中的 API Key 是否正确，账户是否有余额
→ 登录 https://platform.deepseek.com 查看

### 深度采集没有拿到完整内容
→ 确认猎聘详情页能正常打开（有些简历设置了权限限制）
→ 详情采集每份约等 5 秒，耐心等待

---

## 项目结构

```
liepin-screener/
├── main.py                     # CLI 入口
├── config.py                   # 配置文件（选择器、阈值等）
├── .env                        # DeepSeek API Key
├── requirements.txt
│
├── collector/
│   ├── liepin_collector.py     # 采集核心（Playwright CDP 驱动）
│   ├── page_survey.py          # 页面结构调查工具
│   ├── cdp_connector.py        # CDP 连接管理
│   ├── chrome_launcher.py      # Edge/Chrome 一键启动（调试模式）
│   └── browser.py              # 扫码登录（备用）
│
├── analyzer/
│   ├── stage1_rules.py         # 规则引擎（零成本过滤）
│   ├── stage2_vector.py        # 向量语义匹配（本地模型）
│   ├── stage3_deepseek.py      # DeepSeek 深度分析
│   └── pipeline.py             # 三阶段流水线编排
│
├── models/                     # 数据模型
├── storage/store.py            # JSON 文件存储
├── reporter/excel.py           # Excel 报告生成
└── data/                       # 运行时数据（自动生成）
```
