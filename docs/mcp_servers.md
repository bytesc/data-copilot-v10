# MCP 服务器指南

MCP（Model Context Protocol）服务器为 LLM 提供外部工具，通过 `explore_mcp` / `exe_mcp` action 调用。本文独立说明 MCP 服务器的配置与启动，供开发和部署参考。

## 1. 配置文件 `config/mcp_servers.yaml`

后端启动时读取该文件注册可用的 MCP 服务器。

```yaml
mcp_servers:
  - name: "calculator"            # 唯一标识，explore_mcp / exe_mcp 通过此名称引用
    description: "Math expression evaluator"  # 可选，展示给 LLM 的服务器描述
    transport: "sse"              # "sse"（远程 HTTP）或 "stdio"（本地子进程）
    url: "http://localhost:8101/sse"  # SSE 传输必填

  - name: "filesystem"
    description: "文件系统访问"
    transport: "stdio"
    command: "npx"                           # stdio 传输必填
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]  # 可选参数
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 服务器唯一标识 |
| `description` | 否 | 展示给 LLM 的描述文本 |
| `transport` | 是 | `"sse"`（HTTP 端点）或 `"stdio"`（子进程管道）|
| `url` | 仅 `sse` | SSE 端点地址 |
| `command` | 仅 `stdio` | 启动命令 |
| `args` | 否 | 参数列表 |

> 功能总开关为 `config/config.yaml` 的 `enable_mcp`（默认 `true`），设为 `false` 时 `explore_mcp` / `exe_mcp` 被禁用。

## 2. 启动 MCP 服务器

项目内置测试服务器位于 `mcpserver/` 目录。

### 一键启动所有服务器

```bash
python3 -m mcpserver.run_all
```

### 分别启动

```bash
python3 -m mcpserver.calculator_server    # 端口 8101
python3 -m mcpserver.datetime_server      # 端口 8103
```

### 启动检查

后端（`main.py`）启动时对 `sse` 传输的服务器做端口可达性检查，不可达会输出 `[WARNING]`；`stdio` 服务器无端口检查。

## 3. 新增 MCP 服务器

### 3.1 创建服务器文件

在 `mcpserver/` 下新建 `.py` 文件，使用 `mcp` 官方库定义工具：

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

### 3.2 注册到 `config/mcp_servers.yaml`

```yaml
mcp_servers:
  - name: "example"
    description: "Example tools: hello, add"
    transport: "sse"
    url: "http://localhost:8200/sse"
```

### 3.3 更新 MCP Brief

编辑 `agent/tools/base_knowledge/knowledge_docs/mcp_brief.md`，在 Server List 中添加新服务器描述，以便 LLM 在 `explore_mcp` 时了解可用服务器。

### 3.4 添加到启动脚本（可选）

在 `mcpserver/run_all.py` 的 `SERVERS` 列表中添加条目：

```python
SERVERS = [
    ("calculator", 8101, ...),
    ("datetime",   8103, ...),
    ("example",    8200, ["python", "-m", "mcpserver.example_server"]),
]
```

## 4. 开发指南

- 工具函数类型注解中的参数名和类型会作为 `inputSchema` 自动生成，LLM 据此构造参数
- 工具函数的 `"""docstring"""` 会作为工具的描述展示给 LLM，建议写清楚功能和参数含义
- 支持 Python 原生类型：`str`, `int`, `float`, `bool`, `list[type]`, `dict` 等
- 客户端实现位于 `agent/tools/mcp_client/mcp_client.py`
