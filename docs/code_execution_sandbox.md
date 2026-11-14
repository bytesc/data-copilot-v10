# LLM 生成代码执行沙箱

LLM 生成的 Python 代码在一个**一次性子进程**中执行：代码先经 AST 审查，再送进与主进程
完全隔离的子进程运行，结果通过一条窄的 JSON-lines 通道传回，并叠加超时与资源上限。
不依赖 Docker，零新增依赖，全部使用标准库，Windows / Linux / macOS 共用同一套代码。

> **开关**：整个沙箱由主配置 `config/config.yaml` 的 **`enable_code_sandbox`** 控制（默认
> `true`）。设为 `false` 时不走沙箱，改为在主进程内直接 `exec` 生成代码（旧行为：**无隔离、无
> 资源限制、无文件/网络管控**，仅限完全可信的单租户部署）。下方各层仅在开关为 `true` 时生效。

## 一、五层防线

| 层 | 位置 | 作用 |
|----|------|------|
| 1 代码审查 | `sandbox/policy.py` | 用 `ast` 解析代码，限制可 import 的模块、危险的调用（`eval/exec/open/...`）与逃逸属性（`__globals__/__class__/...`）。不合规即报错回传，代码不执行 |
| 2 独立进程 | `sandbox/executor.py` + `sandbox/runner.py` | 每次执行新开一个子进程，跑完销毁；崩溃、卡死、内存泄漏与主进程互不影响；matplotlib 为全新环境，figure/rcParams 随进程消亡，并发天然隔离 |
| 3 白名单环境 | `sandbox/runner.py` + 每次生成的最小沙箱配置 | 子进程内 `exec` 使用手工构造的命名空间，只含白名单工具函数与预注入库；子进程读到的是最小化的独立配置，数据库身份只有只读账号 |
| 4 限时限量强杀 | `sandbox/limits.py` | 总超时到点强杀整棵进程树；内存/CPU/进程数/文件大小硬限；父进程退出则子进程自杀 |
| 5 输出收口 | 协议（`runner.py` ↔ `executor.py`） | 结果只经 stdout 的 JSON-lines 协议传回；DataFrame 转 CSV 传回后在主进程还原；单行与行数有上限 |
| 6 运行期管控 | `sandbox/guard.py`（子进程内 `sys.addaudithook`） | 运行期按白名单拦 `open`/`socket`：生成代码只能读写 `tmp_imgs` 等允许路径、只能连白名单主机；`config/config.yaml`、`agent/utils/llm_access/*` 等敏感文件被拒。密钥不回传子进程（见下） |

## 二、执行流水线

```
LLM 生成代码 → 提取 ```python 块
            → AST 审查
                 ├─ 不合规 → 报错回传 LLM 重写（代码不执行）
                 └─ 通过 → 主进程写 job 与最小沙箱配置到临时目录
                        → spawn 子进程：python -E -s -u runner.py <job>（最小环境变量）
                        → runner：MPLBACKEND=Agg → 中文字体 → rlimit/看门狗
                                  → 白名单命名空间 exec
                        → 迭代 func() 的 yield 项 → JSON-lines 逐行传回
                        → 主进程还原 yield 项 → 既有 SSE 事件流推送
                        → 超时/异常/异常退出 → kill_tree → 错误文本进入重试链路
```

主进程侧 `execute_in_sandbox()` 返回生成器：调用方开始迭代时才启动子进程，迭代提前结束
时子进程被强杀。生成代码只在子进程内执行。

## 三、组件

沙箱实现位于 `agent/tools/copilot/utils/sandbox/`：

| 文件 | 职责 |
|------|------|
| `policy.py` | AST 审查规则与检查函数 |
| `limits.py` | 跨平台资源限制 + `kill_tree` + 孤儿看门狗（平台差异收敛于此，能力探测、不支持则降级） |
| `runner.py` | 沙箱入口：环境设置、白名单命名空间、LLM 代理、执行、序列化 |
| `executor.py` | 主进程侧：审查、渲染最小沙箱配置、spawn、deadline 读行、LLM 代理应答、超时强杀、协议解码 |
| `guard.py` | 子进程内运行期管控：`sys.addaudithook` 拦 `open`/`socket`，按 `sandbox.yaml` 白名单放行（文件访问 + 网络出口） |

若干相关模块的行为：

- `agent/tools/copilot/utils/code_executor.py` 的 `execute_py_code()` 委托沙箱执行，返回可迭代的结果生成器。
- `agent/tools/tools_def.py` 的 `get_save_image_path` 示例不含 import 语句。
- `data_access/db_conn.py` 的 `engine`、`data_access/sys_db_conn.py` 的 `sys_engine` 均为
  “配置存在才建，否则为 None”；主进程配置齐全，二者照常构建；沙箱不提供对应配置，
  因此子进程内不构建这两个特权 engine。
- `config/get_config.py` 的配置路径优先取 `CODE_EXEC_CONFIG` 环境变量；主进程不设置它。

## 四、沙箱配置：独立、最小

沙箱子进程不读取主配置 `config.yaml`。主进程每次执行前只写一份最小配置到临时目录，内容
是白名单工具真正会读取的几个值：

```python
data = {
    "mysql_readonly": config_data.get("mysql_readonly") or "",  # 唯一的数据库身份（只读）
    "static_path":    config_data.get("static_path", ""),       # 图片/CSV 链接前缀
    "llm_models":     config_data.get("llm_models") or [],      # explain_data / predict_hdb_price 用
}
# 写入 workdir/sandbox_config.yaml，路径经 CODE_EXEC_CONFIG 传给子进程
```

这三项对应子进程导入链里真正被读取的配置：

- `mysql_readonly`：`tools_def` 用它建 `read_engine`；沙箱内被白名单工具使用的数据库访问只有只读这一条。
- `static_path`：`tools_def` / `custom_tools_def` 拼图片、CSV 的 URL。
- `llm_models`：`explain_data`、`predict_hdb_price` 在子进程里构造请求参数用（**不含密钥**：子进程不读 key 文件，见下）。

其余配置项不写入该文件：特权库 `mysql`、系统库 `mysql_sys` 在沙箱内不被使用；`enable_*`、
`server_*`、`code_exec`（现已移至 `config/sandbox.yaml`）等也不被子进程读取。该文件随 workdir
一起删除；写入失败即中止（fail-closed），不回退到特权 `config.yaml`。

### 密钥不回传子进程（LLM 代理）

子进程**不再持有 API key**：`runner.py` 在 `exec` 前把 `LLM._get_client` 替换为代理，子进程内
`explain_data` / `predict_hdb_price` 发起的每次 LLM 调用都被转发给父进程（协议通道的
`llm_request` 行），父进程用自己内存里的 key 完成真实请求，再把回复经子进程 stdin 的
`llm_response` 行回传。因此 `agent/utils/llm_access/*.txt` 在子进程内被禁止读取（见 `guard`），
且不影响这两个工具正常工作。

除最小配置外，本次请求选中的模型 / Depth / Style（以及 use_images）由主进程在 spawn 时读取
当前上下文，随 `job.json` 的 `llm_selection` 字段传给子进程；子进程在执行前调用
`apply_request_selection` 还原，使 `explain_data`、`predict_hdb_price` 等自带 LLM 调用的工具
与前端选择一致（新进程的 contextvar 会复位为默认，故必须显式传递）。

## 五、配置项与超限行为（`config/sandbox.yaml`）

沙箱全部配置集中在 `config/sandbox.yaml`（由 `config/sandbox_config.py` 读取），与主配置
`config/config.yaml` 分离：

```yaml
# 资源上限
code_exec:
  timeout: 600        # 总超时秒数（主进程墙钟计时，10 分钟）
  max_memory_mb: 1536 # 内存上限
  cpu_rate: 120       # CPU 秒数上限
  max_processes: 64   # 进程/线程数上限
  max_file_mb: 64     # 单文件大小上限
  max_df_rows: 50000  # DataFrame 超过此行数则截断后再传回
  max_line_mb: 20     # 单条协议行硬上限

# 运行期文件访问管控（子进程 audit hook）—— 全部在此定义，沙箱代码不含内置放行
file_access:
  allow_write_dirs: ["tmp_imgs"]   # 可读写目录（相对项目根/绝对）
  allow_read_dirs: ["assets"]      # 只读目录（写被拒）
  allow_read_files: ["config/mcp_servers.yaml"]  # 只读单文件
  deny_paths:                      # 始终拒绝（读+写，优先级最高）；支持 glob
    - "config/config.yaml"
    - "config/sandbox.yaml"
    - "agent/utils/llm_access/*.txt"
  code_exts: [".py", ".pyc", ".pyd", ".so", ".dll", ".whl"]  # 项目根内源码后缀（只读）
  python_libs: true                # 允许读 Python 安装目录（stdlib/site-packages，import 必需）
  matplotlib_cache: true           # 允许读写 matplotlib 缓存目录

# 运行期网络白名单（子进程 audit hook）
network:
  allow_hosts: ["localhost", "127.0.0.1", "onemap.gov.sg", "openstreetmap.org",
                "streetdirectory.com", "duckduckgo.com"]   # "*" = 放行全部主机
  allow_ports: [80, 443, 3306]                             # "*" = 放行全部端口
```

> `network.allow_hosts` / `allow_ports` 会自动追加：只读库主机与端口、各 LLM API 主机与端口、
> SSE MCP 主机与端口（`executor._guard_config()`）。`fetch_webpage` 抓取的任意外部站点默认不在
> 白名单内，需要按需把域名加入 `allow_hosts`。若要放行全部，把 `allow_hosts` 或 `allow_ports`
> 写成 `["*"]` 即可（仅建议受信环境）。
> 主机名按"完全相等或子域后缀"匹配（`openstreetmap.org` 覆盖 `tile.openstreetmap.org`）；`*` 是
> 整轴放行，不是 `*.` 后缀。

| 配置 | 生效范围 | 超过时 |
|------|----------|--------|
| `timeout` | 全平台（主进程计时） | 强杀整棵进程树 → `SandboxError` → 重试链路 |
| `max_memory_mb` | Linux/macOS: `RLIMIT_AS`；Windows: Job Object | POSIX 抛 `MemoryError`；Windows 被 OS 杀进程（转为报错）；均进入重试链路 |
| `cpu_rate` | 仅 POSIX（`RLIMIT_CPU`，CPU 秒） | 触顶被信号终止（转为报错）→ 重试链路；Windows 不生效 |
| `max_processes` | 仅 POSIX（`RLIMIT_NPROC`） | fork/建线程失败 → `OSError` → 重试链路；Windows 不生效 |
| `max_file_mb` | 仅 POSIX（`RLIMIT_FSIZE`，单文件） | `SIGXFSZ` 终止或 `OSError`（转为报错）→ 重试链路；Windows 不生效 |
| `max_df_rows` | 全平台（runner 序列化） | 静默截断到该行数 |
| `max_line_mb` | 全平台（runner，仅 DataFrame 的 CSV） | 继续减行；连 1 行都超则替换为占位字符串；不报错 |

平台不支持的限制项自动跳过并记一条 warning。子进程若未发出结束消息即退出（被资源限制
杀掉或崩溃），主进程按“异常退出”抛出 `SandboxError`，进入重试链路，而不是当作成功。

### 沙箱错误类型（`SandboxError.kind`）

`SandboxError` 除消息外还带一个稳定的机器可读 `kind`（`executor.py`），使调用方能记录、
展示并把具体类型回喂 LLM，而不必解析自然语言文案：

| `kind` | 触发点 |
|--------|--------|
| `config_error` | 渲染最小沙箱配置失败（fail-closed） |
| `syntax_error` | AST 解析失败（`policy.py` 抛 `PolicyViolation(kind="syntax_error")`） |
| `policy_violation` | AST 审查命中禁用 import/调用/属性 |
| `timeout` | 超过 `timeout` 强杀整棵进程树 |
| `resource_limit` | 子进程未发结束消息即退出（内存/CPU/文件超限或崩溃） |
| `no_func` | 代码未定义可调用的 `func`（子进程 `runner.py` 上报） |
| `runtime_error` | 生成代码执行时抛异常（子进程上报，含 traceback） |
| `environment_error` | 沙箱工具函数加载等执行前环境准备失败 |
| `job_error` | 子进程读取 job 文件失败 |

生成层还有 `code_format_error`（未能在回复中解析出代码块）。这些 `kind` 会经
`code_exe_error` / `code_gen_error` chunk 与终端 `error` 事件的 `error_kind` 字段向上传递，
并记入 `generate_and_execute` 的 act 条目，供下一步（Observe）读取。

## 六、跨平台

- 主流程零平台判断；差异只在 `limits.py` 内。
- 解释器以 `python -E -s -u` 启动：忽略 `PYTHON*` 环境变量、不加载用户 site-packages、输出无缓冲。
- 超时强杀：POSIX 杀进程组（`killpg`，含 MCP stdio 孙进程）；Windows 用 ctypes 的 Job Object
  整树终止（stdlib，无 pywin32），Job 不可用时回退 `taskkill /T /F`。
- 孤儿防护：POSIX 侧 runner 的看门狗在父进程消失后自杀；Windows 侧靠 Job 的 `KILL_ON_JOB_CLOSE`。

## 七、可选宿主机加固（部署期手动，不影响应用代码）

防火墙封禁沙箱出站、配置 ACL 锁定，按需执行：

Linux（nftables 示例）：

```bash
sudo nft add table inet code_sandbox
sudo nft add chain inet code_sandbox output '{ type filter hook output priority 0; }'
sudo nft add rule inet code_sandbox output tcp dport { 3306 } accept
sudo nft add rule inet code_sandbox output drop
# 主配置只读锁定（编辑时先解锁；沙箱配置为每次生成的临时文件，无需锁定）
sudo chattr +i config/config.yaml || true
```

macOS（pf 示例）：

```bash
# /etc/pf.anchors/code_sandbox: 仅放行数据库端口，其余阻断
sudo pfctl -a code_sandbox -f /etc/pf.anchors/code_sandbox
sudo chflags uchg config/config.yaml || true
```

Windows（PowerShell 示例）：

```powershell
New-NetFirewallRule -DisplayName "code_sandbox_block_outbound" -Direction Outbound `
  -Program "C:\Path\To\python.exe" -Action Block
New-NetFirewallRule -DisplayName "code_sandbox_allow_mysql" -Direction Outbound `
  -Program "C:\Path\To\python.exe" -Protocol TCP -RemotePort 3306 -Action Allow
icacls config\config.yaml /deny "%USERNAME%:(W,M)"
```

## 八、能力边界

| 能防住 | 防不住（需容器才能防） |
|--------|----------------------|
| 主程序被拖垮/挂死/资源耗尽；特权对象引用泄露；配置密钥被读（含 API key 不进子进程）；运行期按白名单拦任意文件读写与任意联网（`guard.py` audit hook）；死循环与内存炸弹 | 同账户内核级逃逸（理论存在）；C 扩展里不触发 audit 事件的极端路径；工具函数本身被滥用刷配额（靠数据库侧超时/限流缓解）；真正的网络物理隔离（firewall/容器） |

`guard.py` 是在**运行期**拦截，而非文本期：无论读文件/联网来自 `open`、`pd.read_csv` 还是
`np.load`，底层都会触发同一个 audit 事件，因此覆盖了 AST 审查看不到的库内 I/O。它仍是
**同进程、同 OS 用户**的防护，不能替代容器/独立低权账户。

其它已知边界：`max_line_mb` 只作用于 DataFrame 的 CSV，生成代码 `yield` 的超大普通字符串
不受其约束；`max_processes` 基于 `RLIMIT_NPROC`，按用户(UID)计进程/线程数。

## 九、验证要点

1. 全链路：画图 / 查数 / 文档生成，图片路径与 DataFrame 渲染正确。
2. `while True` → 超时强杀 → 进入重试链路。
3. `import os` / `from agent... import engine` / `open("config.yaml")` → policy violation（不执行）。
4. `print(engine)` → `NameError`。
5. 并发多个画图请求互不串扰、无字体异常。
6. 三平台各跑一遍：强杀后无孤儿进程。
7. 生成的沙箱配置只含 `mysql_readonly / static_path / llm_models`；子进程内 `engine`、`sys_engine` 均为 None。
8. `perf_log.csv` 的 `code_exec_time` 含沙箱冷启动开销（约 1s）。
