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
    # timeout: 30                 # 可选：握手/列表等一般请求的等待秒数，默认 30
    # call_timeout: 120           # 可选：tools/call 的等待秒数，默认 120

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
| `transport` | 否 | `"sse"`（HTTP 端点）或 `"stdio"`（子进程管道）；缺省为 `"stdio"` |
| `url` | 仅 `sse` | SSE 端点地址 |
| `command` | 仅 `stdio` | 启动命令 |
| `args` | 否 | 参数列表 |
| `timeout` | 否 | 握手 / 工具列表等一般请求的等待秒数；缺省 30 |
| `call_timeout` | 否 | `tools/call`（实际调用工具）的等待秒数；缺省 120，慢速外部工具应调大 |

> `timeout` / `call_timeout` 由 `MCPClient` 读取（`agent/tools/mcp_client/mcp_client.py`）；非正数或缺省时回退到默认值（一般请求 30s，`tools/call` 120s）。`tools/call` 也可在代码中通过 `call_tool(..., timeout=...)` 逐次覆盖。

> 功能总开关为 `config/config.yaml` 的 `enable_mcp`（默认 `true`），设为 `false` 时 `explore_mcp` / `exe_mcp` 两个 action 被禁用（注意：`enable_mcp` 只门控 action，`FUNCTION_DICT` 中的 `exe_mcp` 函数本身仍对代码生成可见）。

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
try:
    # mcp 2.x re-exports MCPServer at the package root.
    from mcp.server import MCPServer
except ImportError:  # 部分 mcp 2.x 构建仅在子模块中导出
    from mcp.server.mcpserver import MCPServer

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
    # 可选 transport: "stdio"（默认）, "sse"（客户端仅支持这两种）
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

编辑 `agent/tools/base_knowledge/knowledge_docs/mcp_brief.md`（默认不存在，可自行创建 Server List 小节；该目录被 `.gitignore` 忽略）或系统库 `brief_info` 表的 `mcp_brief` 行，添加新服务器描述（两者内容会合并），以便 LLM 在 `explore_mcp` 时了解可用服务器。

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
