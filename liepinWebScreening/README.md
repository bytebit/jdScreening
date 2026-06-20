# 猎聘智能简历筛选系统

从猎聘搜索结果页自动采集候选人 → AI 智能分析匹配度 → 输出 Excel 报告。

> 💡 全程双击操作，不需要记命令，不需要敲键盘。

---

## 快速开始

### 首次使用（只需做一次）

| 步骤 | 操作 | 说明 |
|------|------|------|
| ① | 双击 **`install.bat`** | 自动安装 Python 依赖和浏览器引擎（约 3-5 分钟） |
| ② | 用记事本打开 `.env` | 填入 DeepSeek API Key（[点此获取](https://platform.deepseek.com/api_keys)） |

> .env 文件打开后长这样，把 `sk-your-key-here` 替换成你的 Key 即可：
> ```
> DEEPSEEK_API_KEY=sk-你的Key
> ```

### 每次使用流程

```
双击「启动浏览器.bat」→ 打开猎聘扫码登录 → 设条件点搜索
→ 双击「一键运行.bat」→ 等几分钟 → 打开 Excel 报告
```

#### 第 1 步：启动浏览器

双击 **`启动浏览器.bat`**

- 会自动关掉旧的 Edge，以调试模式重新打开
- Edge 窗口右上角会显示「Edge 正由自动化测试软件控制」— 这是正常的
- **不要关这个 Edge**，后续操作都在它里面做

#### 第 2 步：登录猎聘并搜索

1. 在刚打开的 Edge 中访问 [https://lpt.liepin.com](https://lpt.liepin.com)
2. 扫码登录猎聘 HR 后台
3. 进入「人才搜索」→ 设好筛选条件（工作年限、学历、技能等）→ 点「搜索」
4. **保持这个搜索结果页打开，不要关闭**

#### 第 3 步：一键运行

双击 **`一键运行.bat`**

按照提示操作：
1. 选一个 JD 文件（或粘贴 JD 描述）
2. 输入采集份数（默认 30 份）
3. 回车后自动开始采集和分析

系统会自动完成：
- ✅ 读取搜索结果页的候选人
- ✅ 自动翻页采集
- ✅ 规则引擎 + DeepSeek AI 匹配分析
- ✅ 生成 Excel 报告

> 报告会保存在 `data/reports/` 目录下

---

## 用命令行操作（进阶）

如果想更灵活地控制参数，可以手动运行：

```bash
# 采集+分析+报告（从文件读取 JD）
python main.py run --jd-file jd.txt --max 30

# 带深度采集（逐条打开简历详情）
python main.py run --jd-file jd.txt --max 30 --deep

# 仅采集不分析
python main.py collect --max 50

# 更换 JD 重新分析已有缓存
python main.py analyze --jd-file jd.txt --resume-dir data/resumes/liepin

# 重新生成报告
python main.py report --job-id "JD-xxx"
```

---

## 架构

```
你的 Edge（已打开猎聘搜索结果页）
    │ CDP 连接（无需重新登录）
    ▼
采集候选人 → 实时保存 JSON
    │
    ▼
三阶段分析流水线：
  Stage 1: 规则引擎（学历/经验/关键词，零成本）
  Stage 2: 向量语义匹配（可选，本地模型）
  Stage 3: DeepSeek 深度分析（仅对通过前两轮的候选人）
    │
    ▼
Excel 报告（S/A/B/C/D 分级）
```

---

## 项目文件说明

| 文件 | 作用 |
|------|------|
| `install.bat` | 🖱️ 双击安装（首次使用） |
| `启动浏览器.bat` | 🖱️ 双击启动 Edge 调试模式 |
| `一键运行.bat` | 🖱️ 双击采集+分析+出报告 |
| `jd.txt` | 📝 岗位描述文件（可修改） |
| `config.py` | ⚙️ 配置文件（一般不需要动） |
| `data/reports/` | 📊 生成的 Excel 报告 |
|