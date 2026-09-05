# Data Copilot v10

✨ **基于代码生成的多智能体数据分析平台**

通过自然语言与数据库交互，自动理解用户意图，将复杂问题拆解为子任务，通过 T-A-A-O 自主循环（Think → Action → Act → Observe）逐步完成 SQL 查询、代码生成执行、图表绘制与报告生成。支持多源知识库蒸馏、联网搜索、CSV 一键导入与全链路可观测。

🚩 [English Readme](./README.en.md)

### 相关项目
- [基于大语言模型的可解释型自然语言数据库查询系统](https://github.com/bytesc/data-copilot-steps)
- [基于大语言模型和并发预测模型的自然语言数据库查询系统](https://github.com/bytesc/data-copilot-v2)

[个人网站：www.bytesc.top](http://www.bytesc.top)

## 功能简介

- **自然语言驱动分析**：直接提问，自动生成并执行 SQL 和 Python 代码完成查询与可视化
- **T-A-A-O 自主闭环**：Think（规划）→ Action（决策）→ Act（执行）→ Observe（审查），循环直到任务完成
- **多智能体角色分工**：规划、执行、审查等角色分离，协同完成复杂任务流水线
- **代码生成与执行**：动态生成 Python 代码，安全沙箱执行，支持 SQL 查询、图表绘制、数据变换
- **智能图表绘制**：自动选择图表类型（matplotlib/seaborn），支持对比图、数据标注
- **知识蒸馏与检索**：多源知识库（业务规则、查询指南、思维策略、代码范例），动态注入上下文
- **上下文智能裁剪**：按类别独立保留策略，避免长对话上下文溢出
- **文档自动生成**：一键生成 Markdown / DOCX / PDF 格式分析报告，含图表的智能排版
- **任意 CSV 导入**：上传 CSV 自动建表，上传文档自动生成数据注释
- **联网搜索**：支持 DuckDuckGo 联网搜索，结合外部信息分析
- **全链路可观测**：每一步 LLM 调用、代码执行、结果均记录到数据库，支持会话回溯
- **SSE 实时流式**：生成代码、执行结果、规划更新实时推送到前端

## 技术架构

### 核心循环：T-A-A-O

```
┌─────────┐     ┌──────────┐     ┌──────┐     ┌──────────┐
│  THINK  │────▶│  ACTION  │────▶│  ACT │────▶│  OBSERVE │
│ (规划)   │     │ (决策)    │     │(执行) │     │ (审查)    │
└─────────┘     └──────────┘     └──────┘     └──────────┘
     ▲                                              │
     └──────────────────────────────────────────────┘
                    (循环直到任务完成)
```

每个阶段对应独立的 LLM 调用和专用提示词：

1. **THINK（思考）**：LLM 接收用户问题、数据库结构、函数目录、知识库，输出 JSON 规划 `{"description": "...", "todo": ["task1", ...]}`
2. **ACTION（决策）**：LLM 根据当前规划选择一个动作（探索表结构、生成代码、搜索知识库、搜索网页、反问用户、生成文档等）
3. **ACT（执行）**：执行所选动作——生成并执行代码、查询数据库、绘制图表、搜索网页等
4. **OBSERVE（审查）**：LLM 审查执行结果，更新任务列表，处理错误，决定继续或终止

### 组件架构

| 组件 | 说明 |
|------|------|
| **LLM 主干** | 支持 DeepSeek、Qwen、GLM、GPT-4o 等，通过 OpenAI 兼容接口接入 |
| **函数图谱** | 预定义工具函数（SQL 查询、图表绘制、数据分析、网页搜索等），LLM 动态选择组合 |
| **知识库** | 多源知识：业务规则（DB + 文件）、查询指南、思维策略、代码范例、数据库摘要 |
| **代码引擎** | 生成 Python 代码 → 沙箱执行 → 结果流式返回 |
| **数据库层** | 用户数据 DB（MySQL）+ 系统 DB（会话日志、知识库、操作审计） |
| **文档生成器** | 大纲规划 → 逐节生成 → 多格式导出（MD/DOCX/PDF） |
| **前端** | Vue 3 + Vite，SSE 流式渲染，T-A-A-O 状态机 |

### 工作流程

```
用户提问 → [THINK] 规划任务列表
            → [ACTION] 决策动作
              → [ACT] 执行动作（探索/查询/画图/搜索/生成文档等）
                → [OBSERVE] 审查结果，更新任务列表
                  → 循环直到任务全部完成
```

### 工具函数

| 函数 | 功能 |
|------|------|
| `exe_sql(sql)` | 执行原始 SQL 查询 |
| `query_database(question, columns)` | 自然语言转 SQL 查询 |
| `explain_data(question, data)` | 自然语言数据分析说明 |
| `load_data(url)` | 从 CSV 链接加载数据 |
| `search_web(query)` | DuckDuckGo 网页搜索 |
| `fetch_webpage(url)` | 抓取网页内容 |

## 配置与使用

### 环境要求

- Python 3.10
- MySQL 数据库

### 安装依赖

```bash
pip install -r requirement.txt
```

### 配置文件

`./config/config.yaml`

```yaml
server_port: 8009
server_host: "0.0.0.0"

# 用户数据数据库
mysql: "mysql+pymysql://root:123456@localhost:3306/data_copilot_v10"

# 系统数据库（会话日志、知识库等）
mysql_sys: "mysql+pymysql://root:123456@localhost:3306/data_copilot_v10_sys"

# 静态文件服务地址
static_path: "http://127.0.0.1:8009/"
# 静态文件存储目录
static_folder: "tmp_imgs"

# 大模型配置
model_name: "deepseek-v4-flash"
model_url: "https://tokenhub.tencentmaas.com/v1"
```

### 前端配置

`vue-front/.env`

```env
VITE_SERVER_URL=http://127.0.0.1:8009
VITE_API_BASE=/api
```

### API Key 配置

新建文件 `agent/utils/llm_access/api_key_openai.txt`，填入 API Key。

获取方式：
- [阿里云百炼](https://bailian.console.aliyun.com/)
- [DeepSeek](https://api-docs.deepseek.com/)
- [智谱 GLM](https://open.bigmodel.cn/)
- [OpenAI](https://platform.openai.com/)

### 启动

```bash
python ./main.py
```

## 开源许可

MIT License

Copyright (c) 2025 bytesc