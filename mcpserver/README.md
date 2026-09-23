# MCP 测试服务器

本目录包含基于 [mcp](https://github.com/modelcontextprotocol/python-sdk) 官方库的 MCP 测试服务器，用于开发和测试 `explore_mcp` / `exe_mcp` 功能。

## 目录结构

```
mcpserver/
├── README.md                    # 本文件
├── calculator_server.py         # 计算器 MCP 服务器 (端口 8101)
├── datetime_server.py           # 日期时间 MCP 服务器 (端口 8103)
└── run_all.py                   # 一键启动所有服务器
```

## 启动服务器

### 一键启动所有服务器

```bash
python3 -m mcpserver.run_all
```

### 分别启动

```bash
python3 -m mcpserver.calculator_server    # 端口 8101
python3 -m mcpserver.datetime_server      # 端口 8103
```

## 新增 MCP 服务器

### 1. 创建服务器文件

在 `mcpserver/` 下新建 `.py` 文件，使用 `mcp` 库的 `MCPServer` 定义工具：

```python
# mcpserver/example_server.py
from mcp.server import MCPServer

mcp = MCPServer("example")

@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone"""
    return f"Hello, {name}!"

@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers"""        # 描述会作为工具说明展示给 LLM
    return a + b

if __name__ == "__main__":
    # 可选 transport: "stdio"（默认）, "sse", "streamable-http"
    mcp.run(transport="sse", host="0.0.0.0", port=8200)
```

### 2. 注册到配置文件

编辑 `config/mcp_servers.yaml`，添加服务器信息：

```yaml
# SSE 远程服务
mcp_servers:
  - name: "example"
    description: "Example tools: hello, add"
    transport: "sse"
    url: "http://localhost:8200/sse"

# stdio 本地子进程
  - name: "example_stdio"
    description: "Example tools via local process"
    transport: "stdio"
    command: "python3"
    args: ["-m", "mcpserver.example_server"]
```

- `name`: 唯一标识，`explore_mcp` / `exe_mcp` 通过此名称引用
- `description`: 可选，帮助 LLM 理解服务器用途
- `transport`: 传输方式，`"sse"`（远程 HTTP）或 `"stdio"`（本地子进程）
- `url`: SSE 端点地址（仅 `sse` 传输需要）
- `command` / `args`: 启动命令及参数（仅 `stdio` 传输需要）

### 3. 更新 MCP Brief

编辑 `agent/tools/base_knowledge/knowledge_docs/mcp_brief.md`，在 Server List 中添加新服务器描述，以便 LLM 在 `explore_mcp` 时了解可用服务器。

### 4. 添加到启动脚本（可选）

在 `mcpserver/run_all.py` 的 `SERVERS` 列表中添加条目：

```python
SERVERS = [
    ("calculator", 8101, ...),
    ("datetime",   8103, ...),
    ("example",    8200, ["python", "-m", "mcpserver.example_server"]),
]
```

## 开发指南

- 工具函数类型注解中的参数名和类型会作为 `inputSchema` 自动生成，LLM 据此构造参数
- 工具函数的 `"""docstring"""` 会作为工具的描述展示给 LLM，建议写清楚功能和参数含义
- 支持 Python 原生类型：`str`, `int`, `float`, `bool`, `list[type]`, `dict` 等
- 可通过 `config/mcp_servers.yaml` 中的 `enable_mcp` 开关控制是否启用 MCP 功能
- 启动时对 `sse` 传输的服务器进行端口可达性检查（`main.py`），不可达会输出 `[WARNING]`；`stdio` 服务器无端口检查