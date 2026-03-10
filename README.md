# PRManager - 智能PR审查助手


## 📖 项目简介

PRManager 是一个智能代码审查系统，支持两种使用模式：
1. **飞书机器人模式** - 通过飞书与团队成员交互，自动分析Git分支合并
2. **CLI本地模式** - 命令行本地使用，无需飞书配置，适合个人开发

支持两种LLM后端：
- **本地模式 (Ollama)** - 所有AI推理在本地运行，保护代码隐私
- **API模式 (OpenRouter)** - 使用OpenRouter API调用云端大模型，无需本地GPU


## 🚀 快速开始

### 前置要求

| 工具 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.11.14 | 运行环境 |
| Git | 2.51.1 | 代码仓库管理 |

### 1️⃣ 安装项目

```bash
# 克隆项目
git clone git@github.com:Ryan-Suilove/PR-Agent.git
cd PRManger

# 安装Python依赖
pip install -r requirements.txt
```

### 2️⃣ 安装LLM后端

#### 选项A: 本地Ollama模式（推荐有GPU的用户）

```bash
# 安装Ollama（参考 https://ollama.ai/download）
ollama pull qwen2.5-coder:32b  # 或其他模型
```

#### 选项B: API模式（推荐无GPU的用户）

1. 注册 [OpenRouter](https://openrouter.ai/) 账号
2. 获取API密钥: https://openrouter.ai/keys
3. 在配置文件中设置API密钥

### 3️⃣ 安装ripgrep

```bash
# Windows
choco install ripgrep

# macOS
brew install ripgrep

# Ubuntu/Debian
sudo apt-get install ripgrep

# CentOS/RHEL
sudo yum install ripgrep
```

### 4️⃣ 配置系统

编辑 `config/config.yaml`：

```yaml
# 选择LLM模式
llm:
  mode: "local"  # 或 "api"

  # 本地模式配置
  model: "qwen2.5-coder:32b"
  base_url: "http://localhost:11434"

  # API模式配置（当mode为api时）
  # api_key: "sk-or-v1-xxxxxxxx"
  # api_base_url: "https://openrouter.ai/api/v1"
  # api_model: "anthropic/claude-3.5-sonnet"

# Git仓库配置
git_repo:
  repo_path: "/path/to/your/repo"
  base_branch: "main"
  repo_name: "MyProject"
```

### 5️⃣ 启动系统

#### CLI本地模式

```bash
# 审查指定分支
python main_cli.py review feature/login main

# 进入交互模式
python main_cli.py interactive

# 监听仓库push事件
python main_cli.py watch
```

#### 飞书机器人模式

```bash
python main.py
```


## 📱 使用说明

### CLI模式使用

#### 1. 分支审查

```bash
# 审查 feature/login 分支合并到 main
python main_cli.py review feature/login main

# 审查 feature/api 分支合并到默认基础分支
python main_cli.py review feature/api
```

#### 2. 交互模式

```bash
python main_cli.py interactive
```

进入交互模式后可以：
- 输入分支名进行审查
- 使用 `branches` 查看所有分支
- 使用 `status` 查看系统状态
- 使用 `config` 查看当前配置
- 使用 `help` 查看帮助
- 使用 `quit` 退出

#### 3. Git钩子模式

将以下内容添加到 Git 仓库的 `.git/hooks/post-receive` 文件：

```bash
#!/bin/bash
cd /path/to/PRManger
python main_cli.py hook
```

这样每次push时会自动进行代码审查。

#### 4. 监听模式

```bash
python main_cli.py watch
```

持续监控Git仓库的push事件，自动审查更新的分支。

### 飞书模式使用

#### 1. 添加机器人

在飞书中搜索你的机器人名称并添加到对话

#### 2. 触发PR审查

发送以下格式的消息：

```
修改分支 merge 原分支
```

#### 3. 等待审查结果

系统会：
1. ✅ 确认收到请求
2. 📊 推送详细审查报告


## 🔧 配置详解

### LLM模式选择

| 模式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| local (Ollama) | 数据不出本地、无API费用 | 需要GPU、模型下载慢 | 有GPU、对隐私要求高 |
| api (OpenRouter) | 无需本地GPU、模型丰富 | 需要联网、有API费用 | 无GPU、需要使用特定模型 |

### API模式支持的模型

OpenRouter支持多种模型，推荐：

| 模型 | 特点 | 价格 |
|------|------|------|
| anthropic/claude-3.5-sonnet | 综合能力最强 | 中等 |
| openai/gpt-4o | 通用性好 | 中等 |
| google/gemini-pro-1.5 | 超长上下文 | 低 |
| meta-llama/llama-3.1-70b | 开源模型 | 低 |

完整模型列表: https://openrouter.ai/models


### 核心组件

#### 📁 目录结构

```
PRManger/
├── main.py                 # 飞书模式入口
├── main_cli.py             # CLI模式入口
├── config/
│   ├── config.yaml.example  # 配置模板
│   ├── config.yaml          # 系统配置
│   └── code_rules.yaml      # 编码规范
├── src/
│   ├── agents/            # 智能体模块
│   │   ├── listener_agent.py        # 消息监听
│   │   ├── decision_agent.py        # 策略决策
│   │   ├── code_analyzer_agent.py   # 代码分析
│   │   ├── context_collector_agent.py # 上下文收集
│   │   ├── feedback_agent.py        # 报告生成
│   │   └── git_review_agent.py      # Git操作
│   ├── analyzers/         # 分析器
│   │   └── project_analyzer/
│   │       ├── ast_parser.py           # Tree-sitter解析
│   │       ├── fast_file_searcher.py   # ripgrep搜索
│   │       └── code_parser.py          # 正则解析
│   ├── adapters/          # 外部适配器
│   │   ├── feishu_adapter.py  # 飞书SDK
│   │   ├── cli_adapter.py     # CLI接口
│   │   └── git_adapter.py     # Git操作
│   ├── core/              # 核心逻辑
│   │   ├── workflow.py    # LangGraph工作流
│   │   └── state.py       # 状态管理
│   └── utils/             # 工具函数
│       ├── llm.py         # LLM调用（支持Ollama/API）
│       ├── config.py      # 配置加载
│       └── thread_safe_logger.py # 日志
└── logs/                  # 运行日志
```

#### 🔄 工作流程

1. **监听阶段** - 接收用户请求（CLI/飞书）
2. **解析阶段** - 提取分支信息
3. **决策阶段** - 评估diff规模，选择审查策略
4. **分析阶段** - 迭代分析代码变更和影响范围
   - 第1轮：分析直接变更
   - 第2轮：收集相关上下文
   - 第3轮：深度影响评估
5. **报告阶段** - 生成结构化审查报告
6. **提交阶段** - 输出结果（CLI打印/飞书推送）


## 🛠️ 高级功能

### 自定义代码规范

编辑 `config/code_rules.yaml` 添加自定义规范：

```yaml
规范列表:
  - 名称: "命名规范"
    描述: "检查变量、函数命名是否符合规范"
    检查点: "使用驼峰命名或下划线命名"
```

### Git钩子集成

在 `.git/hooks/post-receive` 中添加：

```bash
#!/bin/bash
# 自动审查push的代码
cd /path/to/PRManger
python main_cli.py hook
```

### CI/CD集成

在CI/CD流水线中添加审查步骤：

```yaml
# GitHub Actions 示例
- name: Code Review
  run: |
    pip install -r requirements.txt
    python main_cli.py review ${{ github.head_ref }} ${{ github.base_ref }}
```


## 📝 常见问题

### Q: 如何切换LLM模式？

A: 修改 `config/config.yaml` 中的 `llm.mode` 字段：
- `local`: 使用本地Ollama
- `api`: 使用OpenRouter API

### Q: API模式提示"API密钥未配置"？

A: 确保在配置文件中设置了 `api_key`，或通过环境变量设置：
```bash
export OPENROUTER_API_KEY="sk-or-v1-xxxxx"
```

### Q: CLI模式如何查看所有分支？

A: 进入交互模式后输入 `branches` 命令，或使用：
```bash
python main_cli.py interactive
# 然后输入 branches
```

### Q: 审查结果保存在哪里？

A: CLI模式的审查报告保存在 `logs/review_reports/` 目录下。


## 📄 License

MIT License