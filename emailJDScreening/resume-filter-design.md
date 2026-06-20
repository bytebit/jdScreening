# AI 简历自动筛选系统 — 技术设计方案

> 版本: v1.0  
> 部署环境: AlmaLinux  
> AI 模型: DeepSeek API  
> 数据流: 招聘邮箱(IMAP) → 简历解析 → AI匹配 → 邮件分类归档

---

## 一、系统架构总览

```
                    ┌─────────────────────────────────────────────┐
                    │              PM2 (守护进程)                  │
                    │         main.py --daemon --interval 5       │
                    │                  │                           │
                    │    ┌─────────────▼──────────────┐            │
                    │    │     主循环 (每5分钟一轮)     │            │
                    │    │                             │            │
                    │    │  ① 连接邮箱获取未读邮件       │            │
                    │    │  ② 下载附件(PDF/DOCX/TXT)    │            │
                    │    │  ③ 解析简历 → 纯文本         │            │
                    │    │  ④ 根据邮件主题判定匹配的JD   │            │
                    │    │  ⑤ 调用 DeepSeek API 评估    │            │
                    │    │  ⑥ 将邮件移动到对应文件夹     │            │
                    │    │  ⑦ 记录日志 + CSV 报表       │            │
                    │    └─────────────┬──────────────┘            │
                    │                  │                           │
                    │    ┌─────────────▼──────────────┐            │
                    │    │   config.yaml (配置文件)     │            │
                    │    │   - 邮箱 IMAP 信息          │            │
                    │    │   - DeepSeek API Key        │            │
                    │    │   - JD 描述文件路径          │            │
                    │    │   - 邮件文件夹映射规则        │            │
                    │    └────────────────────────────┘            │
                    └─────────────────────────────────────────────┘
```

---

## 二、模块详细设计

### 2.1 配置文件 (config.yaml)

配置文件集中管理所有可变参数，部署时只需修改这一个文件。

```yaml
# config.yaml

email:
  imap_server: "imap.company.com"
  imap_port: 993
  account: "hr@company.com"
  password: "your-password"          # 或从环境变量读取 EMAIL_PASSWORD
  inbox_folder: "INBOX"              # 收件箱
  processed_folder: "已处理"          # 处理完成后的归档文件夹
  folders:
    pass: "通过筛选"                  # 通过的邮件移到这里
    pending: "待定"                   # 待定的邮件移到这里
    fail: "未通过筛选"                 # 不通过的邮件移到这里

deepseek:
  api_key: "${DEEPSEEK_API_KEY}"     # 优先从环境变量读取
  api_url: "https://api.deepseek.com/v1/chat/completions"
  model: "deepseek-chat"
  temperature: 0.1                   # 低温度，保证一致性
  max_tokens: 512

jobs:
  jd_dir: "./jds/"                   # JD 文件目录，每个文件一个岗位
  # 邮件主题关键词 → JD 文件的映射规则
  # 系统会按顺序匹配，命中的第一个作为该邮件的 JD
  subject_rules:
    - keywords: ["前端", "前端开发", "frontend", "front-end"]
      jd_file: "frontend_engineer.txt"
    - keywords: ["后端", "后端开发", "Java", "Go", "backend"]
      jd_file: "backend_engineer.txt"
    - keywords: ["产品经理", "产品", "PM", "product"]
      jd_file: "product_manager.txt"
    - keywords: ["测试", "QA", "测试工程师"]
      jd_file: "qa_engineer.txt"
  default_jd: "general.txt"           # 未匹配到关键词时的默认JD

resume:
  max_text_length: 8000              # 简历文本最大长度（字符数），超出截断
  supported_formats: [".pdf", ".docx", ".doc", ".txt"]

logging:
  level: "INFO"
  file: "./logs/resume_filter.log"
  report_dir: "./reports/"           # CSV 报表输出目录
```

### 2.2 JD 文件格式

`./jds/` 目录下每个岗位一个 Markdown 文件，内容自由编写，示例：

```markdown
# 后端开发工程师

## 岗位职责
- 负责公司核心业务系统的设计与开发
- 参与系统架构设计和性能优化

## 硬性要求（必需满足）
- 统招本科及以上学历，计算机相关专业
- 3 年以上后端开发经验
- 精通 Java 或 Go

## 加分项
- 有分布式系统开发经验
- 熟悉 Kubernetes / Docker
- 有高并发项目经验

## 工作地点
北京 / 上海
```

### 2.3 邮件接入模块 (`email_handler.py`)

| 功能 | 实现方式 |
|------|---------|
| 连接 | `imaplib.IMAP4_SSL`，端口 993 |
| 收件 | `INBOX` 中搜索 `UNSEEN` 标记的邮件 |
| 解析 | `email.message_from_bytes` 解析 MIME |
| 附件提取 | 识别 `Content-Disposition: attachment`，支持 filename 解码（中英文） |
| 主题提取 | 从 Subject 头中提取，UTF-8 解码 |
| 邮件移动 | `IMAP.copy` + `STORE +FLAGS \Deleted` 实现「移动到文件夹」 |

**关键逻辑：**
- 一次连接处理完所有未读邮件后断开
- 每条邮件处理成功后再移动到对应分类文件夹
- 如果处理失败（如 API 超时），邮件保留在 INBOX 下次重试

### 2.4 简历解析模块 (`resume_parser.py`)

| 格式 | 库 | 方案 |
|------|---|------|
| PDF | `PyMuPDF (fitz)` | 提取纯文本，保留换行和段落 |
| DOCX | `python-docx` | 遍历段落提取文本 |
| TXT | 直接读取 | 按 UTF-8 读取 |

**注意：** 不支持图片简历（已确认不需解析图片类型）。

### 2.5 岗位匹配判定模块 (`jd_matcher.py`)

根据邮件主题判断投递的是哪个岗位：

1. 遍历 `subject_rules` 中的每条规则
2. 检查邮件主题是否包含任一关键词（大小写不敏感）
3. 命中第一条规则即停止，加载对应的 JD 文件
4. 若无规则命中，使用 `default_jd`

### 2.6 AI 评估模块 (`ai_analyzer.py`)

调用 DeepSeek API 进行匹配评估。

**Prompt 设计：**

```
你是一位资深的HR招聘专家。请根据以下【岗位描述】严格评估【候选人简历】是否满足招聘要求。

【岗位描述】
{JD_TEXT}

【候选人简历】
{RESUME_TEXT}

请严格按以下 JSON 格式输出，不要包含其他内容：
{
  "decision": "通过" | "待定" | "不通过",
  "reason": "20字以内说明核心判断依据",
  "matched_requirements": ["匹配点1", "匹配点2"],
  "unmatched_requirements": ["不匹配点1"]
}
```

**决策标准（通过 prompt 约束）：**

| 分类 | 条件 |
|------|------|
| ✅ 通过 | 硬性要求全部满足（学历、年限、核心技能均达标） |
| ⏳ 待定 | 硬性要求基本满足但部分模糊，或 JD 匹配度在 60%-80% 之间 |
| ❌ 不通过 | 明显不满足硬性要求（如学历不符、经验严重不足、技能完全不匹配） |

**异常处理：**
- API 超时 → 重试 2 次 → 标记为「待定」并记录错误日志
- 返回格式异常 → 重试 1 次 → 标记为「待定」
- Token 超出 → 自动截断简历文本（保留开头和结尾的工作经历部分）

### 2.7 结果处理模块 (`result_handler.py`)

1. 根据 AI 决策结果，将邮件从 INBOX **移动**到对应文件夹：
   - `通过筛选` — ✅ 通过
   - `待定` — ⏳ 待定
   - `未通过筛选` — ❌ 不通过
2. 追加记录到 CSV 报表文件（每日一个文件）
3. 记录详细日志

**CSV 报表格式：**

```csv
时间,投递人,邮件主题,投递岗位,分类,理由,附件名
2026-06-15 10:30,张三,应聘前端开发工程师,frontend_engineer,通过,3年前端经验+React技能匹配,张三_前端_简历.pdf
```

---

## 三、AlmaLinux 部署方案

### 3.1 环境准备

```bash
# 安装 Python 3 + pip
yum install -y python3 python3-pip

# 安装系统依赖（PyMuPDF 需要）
yum install -y gcc python3-devel

# 安装 OCR 相关（如果有图片简历需求）
# yum install -y tesseract tesseract-langpack-chi_sim
```

### 3.2 Python 依赖

```txt
# requirements.txt
PyMuPDF>=1.23.0
python-docx>=1.1.0
PyYAML>=6.0
requests>=2.31.0
```

创建虚拟环境：
```bash
python3 -m venv /opt/resume-filter/venv
source /opt/resume-filter/venv/bin/activate
pip install -r requirements.txt
```

### 3.3 项目目录结构

```
/opt/resume-filter/
├── config.yaml              # 配置文件
├── main.py                  # 主入口
├── requirements.txt
├── jds/                     # JD 文件目录
│   ├── frontend_engineer.txt
│   ├── backend_engineer.txt
│   ├── product_manager.txt
│   └── general.txt
├── logs/                    # 日志目录
└── reports/                 # CSV 报表目录
```

### 3.4 API Key 配置

```bash
# 方法一：环境变量（推荐）
echo 'export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"' >> /etc/profile.d/deepseek.sh

# 方法二：直接写入 config.yaml（不推荐，存在泄露风险）
```

### 3.5 PM2 进程管理（替代 cron）

使用 PM2 管理守护进程，比 cron 更可靠（崩溃自动重启、日志管理、开机自启）。

**PM2 配置文件 (`ecosystem.config.js`)：**

```javascript
module.exports = {
  apps: [{
    name: 'resume-filter',
    script: 'main.py',
    interpreter: './venv/bin/python3',
    args: '--daemon --interval 5',    // 每 5 分钟执行一轮
    autorestart: true,                 // 崩溃自动重启
    max_restarts: 10,
    restart_delay: 10000,
    max_memory_restart: '500M',
    kill_timeout: 30000,               // 给 30 秒优雅退出
    error_file: './logs/pm2_error.log',
    out_file: './logs/pm2_out.log',
  }]
};
```

**PM2 常用命令：**

```bash
pm2 status                        # 查看状态
pm2 logs resume-filter            # 查看实时日志
pm2 restart resume-filter         # 重启
pm2 stop resume-filter            # 停止
pm2 startup                       # 配置开机自启
```

---

## 四、运行流程（一次 cron 执行的完整链路）

```
cron触发
  │
  ▼
main.py 启动
  │
  ├─ 1. 加载 config.yaml
  │
  ├─ 2. 连接 IMAP 邮箱，搜索未读邮件
  │     └─ 无未读邮件 → 退出（无事可做）
  │
  ├─ 3. 遍历每封未读邮件:
  │     │
  │     ├─ 3.1 提取 Subject、发件人
  │     ├─ 3.2 下载附件简历
  │     │     └─ 无附件或格式不支持 → 跳过（日志记录）
  │     │
  │     ├─ 3.3 解析简历文本
  │     │
  │     ├─ 3.4 根据 Subject 匹配对应 JD
  │     │
  │     ├─ 3.5 调用 DeepSeek API 评估
  │     │     ├─ ✅ 通过 → 移动到「通过筛选」
  │     │     ├─ ⏳ 待定 → 移动到「待定」
  │     │     └─ ❌ 不通过 → 移动到「未通过筛选」
  │     │
  │     └─ 3.6 追加 CSV 报表记录
  │
  ├─ 4. 断开 IMAP 连接
  │
  └─ 5. 输出本次运行汇总到日志
```

---

## 五、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 触发方式 | PM2 守护进程 (--daemon) | 崩溃自动重启、开机自启、日志轮转，比 cron 更可靠 |
| 进程管理 | PM2 | 自动重启、内存限制、优雅关闭 |
| 配置文件 | YAML | 易读易改，支持环境变量引用 |
| API Key 管理 | 环境变量 | 避免密钥硬编码到配置文件 |
| 邮件归档 | IMAP 移动到文件夹 | HR 在邮箱里直接可见，无需额外工具 |
| 报表输出 | CSV | 简单通用，Excel 可直接打开 |
| 模型 | DeepSeek Chat (deepseek-chat) | 性价比高，中英文能力强 |
| API 温度 | 0.1 | 低温度保证评判一致性和可复现性 |
| 附件支持 | PDF + DOCX + TXT | 覆盖 95%+ 简历投递场景 |
| 每封邮件独立处理 | 是 | 单封失败不影响其他邮件处理 |

---

## 六、使用流程（HR 视角）

```
1. HR 将 JD 文件放入 /opt/resume-filter/jds/
       │
2. 编辑 config.yaml 中的 subject_rules，
   确保邮件主题关键词能匹配到对应 JD
       │
3. 在邮箱中提前建好三个文件夹：
   「通过筛选」「待定」「未通过筛选」
       │
4. 系统启动后自动运行
       │
5. HR 每天查看邮箱 →
   「通过筛选」文件夹 = 建议面试的候选人
   「待定」文件夹 = 需人工复核
   「未通过筛选」文件夹 = 可忽略或发拒信
```

---

## 七、注意事项与扩展方向

### 注意事项
1. **邮箱文件夹需提前创建**，脚本不会自动创建 IMAP 文件夹
2. **密码安全**：建议使用应用专用密码（而非邮箱登录密码），部分邮箱（如 163/Gmail）需要单独开启 IMAP
3. **简历大小限制**：附件超过 10MB 的跳过处理
4. **API 费用**：deepseek-chat 模型非常便宜，每千次评估约几元钱
5. **JD 质量**：JD 写得越清晰（特别是硬性要求），AI 判断越准确

### 可选扩展
- **拒信自动回复**：对「未通过筛选」的邮件自动发送委婉拒信
- **面试邀约**：对「通过筛选」的候选人自动发送面试邀请模板
- **Web 看板**：Flask 搭建简易看板，按时间线展示所有候选人状态
- **企业微信/钉钉通知**：有「通过」的候选人时推送到 HR 群
