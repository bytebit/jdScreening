# AI 简历自动筛选系统

自动连接公司招聘邮箱，解析简历附件，调用 DeepSeek AI 评估匹配度，将邮件按「通过/待定/不通过」自动归档到不同文件夹。

---

## 工作流程

```
招聘邮箱 ──→ 下载附件 ──→ 解析简历 ──→ AI 评估 ──→ 邮件分类归档
 (IMAP)     (PDF/DOCX)    (纯文本)    (DeepSeek)   (通过/待定/不通过)
                                              └──→ CSV 日报表
```

## 快速开始

### 前置条件

- AlmaLinux / CentOS / RHEL 系统
- DeepSeek API Key
- 招聘邮箱开启 IMAP 服务

### 1. 配置

编辑 `config.yaml`：

```yaml
email:
  imap_server: "imap.company.com"
  imap_port: 993
  account: "hr@company.com"
  password: "${EMAIL_PASSWORD}"      # 或直接填密码

deepseek:
  api_key: "${DEEPSEEK_API_KEY}"     # 或直接填 key

jobs:
  subject_rules:
    - keywords: ["前端", "frontend"]
      jd_file: "frontend_engineer.txt"
    # ... 更多岗位
```

### 2. 设置 API Key

```bash
export DEEPSEEK_API_KEY='sk-xxxxxxxxxxxxxxxx'
export EMAIL_PASSWORD='your-email-password'
```

### 3. 部署

```bash
cd 项目目录
sudo bash deploy.sh
```

脚本会自动安装 Python 虚拟环境、Node.js、PM2，并启动守护进程。

### 4. 在邮箱中创建文件夹

在邮箱中创建三个文件夹（名称与 config.yaml 保持一致）：

- `通过筛选`
- `待定`
- `未通过筛选`

### 5. 编写岗位描述

编辑 `jds/` 目录下的文件，每个岗位一个 Markdown 文件。

---

## 日常使用

### 查看状态

```bash
pm2 status                    # 进程是否运行
pm2 logs resume-filter        # 实时日志
```

### 查看结果

| 方式 | 说明 |
|------|------|
| 邮箱文件夹 | 打开邮箱，「通过筛选」= 建议面试 |
| CSV 报表 | `reports/筛选报告_YYYY-MM-DD.csv` |

### 手动运行

```bash
venv/bin/python main.py                  # 单次运行
venv/bin/python main.py --daemon         # 守护模式
venv/bin/python main.py --dry-run        # 试运行（不调 API）
venv/bin/python main.py --debug          # 调试模式
```

### PM2 管理

```bash
pm2 restart resume-filter          # 重启
pm2 stop resume-filter             # 停止
pm2 start ecosystem.config.js      # 启动
pm2 logs resume-filter             # 日志
```

---

## 目录结构

```
.
├── config.yaml              # 主配置文件
├── main.py                  # 主入口
├── email_handler.py         # 邮件接入模块
├── resume_parser.py         # 简历解析模块
├── jd_matcher.py            # 岗位匹配模块
├── ai_analyzer.py           # AI 评估模块
├── result_handler.py        # 结果处理模块
├── ecosystem.config.js      # PM2 配置
├── deploy.sh                # 部署脚本
├── requirements.txt         # Python 依赖
├── jds/                     # 岗位描述目录
│   ├── frontend_engineer.txt
│   ├── backend_engineer.txt
│   ├── product_manager.txt
│   └── general.txt
├── logs/                    # 日志目录（自动创建）
├── reports/                 # CSV 报表（自动创建）
├── temp/                    # 临时文件（自动创建）
└── venv/                    # Python 虚拟环境（自动创建）
```

## 分类规则

| 分类 | AI 判断条件 |
|------|------------|
| ✅ **通过** | 硬性要求全部满足（学历、经验年限、核心技能均达标） |
| ⏳ **待定** | 硬性要求基本满足但部分模糊，或信息不足以判定 |
| ❌ **不通过** | 明显不满足硬性要求，或技能完全不匹配 |

> API 调用失败时自动归为「待定」，避免因系统异常误判淘汰候选人。

## 支持的简历格式

- PDF (`.pdf`)
- Word (`.docx` / `.doc`)
- 纯文本 (`.txt`)

> 不支持图片格式的简历（如需支持可自行扩展 OCR 模块）。

## 配置文件说明

### config.yaml 主要字段

| 字段 | 说明 |
|------|------|
| `email.imap_server` | 邮箱 IMAP 服务器地址 |
| `email.password` | 支持 `${环境变量名}` 语法 |
| `deepseek.api_key` | 同上，建议用环境变量 |
| `jobs.subject_rules` | 邮件主题关键词 → JD 文件映射 |
| `jobs.default_jd` | 未匹配关键词时的默认 JD |
| `resume.max_text_length` | 简历截断长度（控制 token 消耗） |
| `logging.level` | 日志级别：DEBUG / INFO / WARNING |

## License

MIT
