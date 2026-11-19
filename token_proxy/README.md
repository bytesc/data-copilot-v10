# token_proxy

一个轻量的 **OpenAI 兼容转发代理**。对外暴露 `/v1/*` 接口，把请求转发到真实的上游
provider，并在转发时注入真实 token。调用方（例如主系统）只持有代理自己签发的
**代理 key**，看不到真实 token。

- 基于 FastAPI + httpx。
- 支持流式（`"stream": true` / SSE）与非流式，响应体、状态码、响应头按原样透传。
- 每个代理 key 可单独限制：允许的目标、客户端 IP 白名单、模型名白名单。

## 目录结构

```
token_proxy/
├── proxy.py            # 程序主体，入口
├── config.yaml         # 配置 2：服务设置 + 每个代理 key 的策略
├── targets.yaml        # 配置 1：真实上游列表（名称 / url / key 文件名）
├── requirements.txt
├── .gitignore
├── keys/               # 真实 token（被 .gitignore 忽略，仅 .gitkeep 入库）
│   └── api_key_main.txt
└── proxy_keys/         # 对外代理 key（被 .gitignore 忽略，仅 .gitkeep 入库）
    └── proxy_key_1.txt
```

> 真实 token 和对外代理 key **都不写进 YAML**，各自以纯文本文件形式存在（一个文件一个值），
> 在配置里只写文件名。两个目录下的 `*.txt` 均被 `token_proxy/.gitignore` 忽略，做法与主项目
> `agent/utils/llm_access/*.txt` 一致。

## 安装与启动

```bash
cd token_proxy
pip install -r requirements.txt   # fastapi / uvicorn / httpx / PyYAML
python proxy.py
```

可选参数：

```bash
python proxy.py --host 127.0.0.1 --port 8080 \
                --config config.yaml --targets targets.yaml --log-level info
```

默认监听 `config.yaml` 里的 `server.host` / `server.port`。

## 配置 1：`targets.yaml`

定义真实上游列表，以及真实 token 文件所在目录。

```yaml
keys_dir: "keys"            # 真实 token 文件目录（相对本文件）

targets:
  - name: main                                  # 目标名，被 config.yaml 引用，也可用请求头选择
    url: "https://tokenhub.tencentmaas.com/v1"  # 真实上游 OpenAI 兼容 base url
    key_file: "api_key_main.txt"                # keys_dir 下存放真实 token 的文件名
  - name: backup
    url: "https://api.deepseek.com/v1"
    key_file: "api_key_backup.txt"
```

**url 拼接规则**：代理会剥掉调用方路径里开头的 `/v1`，再把剩余部分接到 `url` 上。
因此 `url` 通常要包含版本段（如 `/v1`）：

```
上游 url = https://api.openai.com/v1
调用方   = /v1/chat/completions
实际请求 = https://api.openai.com/v1/chat/completions
```

真实 token 文件内容就是一行 token：

```
keys/api_key_main.txt  ->  sk-真实token
```

## 配置 2：`config.yaml`

服务设置 + 每个对外代理 key 的策略。

```yaml
server:
  host: "0.0.0.0"
  port: 8080

proxy_keys_dir: "proxy_keys"   # 对外代理 key 文件目录（相对本文件）

strategy: round_robin          # round_robin（轮询+故障转移）| first（优先第一个）
timeout: 600                   # 上游读写超时（秒），流式建议调大
trust_proxy: false             # 是否信任 X-Forwarded-For 作为客户端 IP

keys:
  - key_file: "proxy_key_1.txt"          # proxy_keys_dir 下的代理 key 文件
    targets: ["main", "backup"]          # 该 key 可用的目标；省略 = 全部
    ip_whitelist: ["127.0.0.1", "::1"]   # 允许的客户端 IP/CIDR；空 = 不限
    model_whitelist: ["deepseek-v4.1-flash", "glm-5.3-flash"]  # 空 = 不限
```

- `ip_whitelist` 支持单个 IP（`127.0.0.1`）与 CIDR（`192.168.0.0/16`），IPv4/IPv6 均可。
- `trust_proxy` 仅在代理前有可信反向代理时设为 `true`；否则 `X-Forwarded-For` 可被伪造。
- `keys` 列表为空 = 不鉴权（开放代理，不推荐）。
- 兼容内联 `key: "sk-xxx"`，但会记 warning，推荐用 `key_file`。

代理 key 文件内容同样是一行：

```
proxy_keys/proxy_key_1.txt  ->  sk-proxy-xxx
```

## 调用方式

鉴权用 `Authorization: Bearer <代理key>`，也支持 `api-key` / `x-api-key` 头。

```bash
# 非流式
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-proxy-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}]}'

# 流式
curl -N http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer sk-proxy-xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"stream":true}'

# 指定目标（须在该 key 的 targets 内）
curl http://127.0.0.1:8080/v1/models \
  -H "Authorization: Bearer sk-proxy-xxx" \
  -H "X-Proxy-Target: backup"
```

除 `/v1/*` 外还提供：

| 路径      | 说明                          |
| --------- | ----------------------------- |
| `/health` | 健康检查，无需鉴权            |
| `/`       | 返回目标名列表与 key 数量     |

## 请求流程与行为

1. **鉴权**：取 `Authorization: Bearer` / `api-key` / `x-api-key`，按 `keys` 匹配代理 key。
   未知 key → `401`。
2. **IP 白名单**：按该 key 的 `ip_whitelist` 校验客户端 IP，不符 → `403 ip_not_allowed`。
3. **模型白名单**：若请求体为 JSON 且含 `model`，按该 key 的 `model_whitelist` 校验，
   不符 → `403 model_not_allowed`。
4. **选目标**：在该 key 的 `targets` 子集内选择；`X-Proxy-Target` 只能选其中的目标，
   越权 → `400 target_not_allowed`；无可用目标 → `403 no_target`。
   - `round_robin`：轮询，连接失败自动切下一个。
   - `first`：始终用第一个，失败再切下一个。
5. **转发**：注入真实 token（默认 `Authorization: Bearer <真实token>`），去掉逐跳头、
   客户端鉴权头、`Host`/`Content-Length` 后发往上游；响应流式回传。

其他错误：所有上游都连不上 → `502 upstream_unavailable`。
错误响应体为 OpenAI 风格：`{"error": {"message", "type", "code", "param"}}`。

## 安全说明

- `keys/*.txt` 与 `proxy_keys/*.txt` 已被 `token_proxy/.gitignore` 忽略，**不要**提交真实密钥。
- `config.yaml` / `targets.yaml` 只放非敏感信息（url、白名单、策略、文件名）。
- 生产部署建议：把 `ip_whitelist` 收窄到调用方网段；仅在可信反向代理后开启 `trust_proxy`；
  为不同调用方分配不同代理 key 以隔离权限。
