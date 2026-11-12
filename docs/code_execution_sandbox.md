# LLM 生成代码执行沙箱

LLM 生成的 Python 代码在一个**一次性子进程**中执行：代码先经 AST 审查，再送进与主进程
完全隔离的子进程运行，结果通过一条窄的 JSON-lines 通道传回，并叠加超时与资源上限。
不依赖 Docker，零新增依赖，全部使用标准库，Windows / Linux / macOS 共用同一套代码。

## 一、五层防线

| 层 | 位置 | 作用 |
|----|------|------|
| 1 代码审查 | `sandbox/policy.py` | 用 `ast` 解析代码，限制可 import 的模块、危险的调用（`eval/exec/open/...`）与逃逸属性（`__globals__/__class__/...`）。不合规即报错回传，代码不执行 |
| 2 独立进程 | `sandbox/executor.py` + `sandbox/runner.py` | 每次执行新开一个子进程，跑完销毁；崩溃、卡死、内存泄漏与主进程互不影响；matplotlib 为全新环境，figure/rcParams 随进程消亡，并发天然隔离 |
| 3 白名单环境 | `sandbox/runner.py` + 每次生成的最小沙箱配置 | 子进程内 `exec` 使用手工构造的命名空间，只含白名单工具函数与预注入库；子进程读到的是最小化的独立配置，数据库身份只有只读账号 |
| 4 限时限量强杀 | `sandbox/limits.py` | 总超时到点强杀整棵进程树；内存/CPU/进程数/文件大小硬限；父进程退出则子进程自杀 |
| 5 输出收口 | 协议（`runner.py` ↔ `executor.py`） | 结果只经 stdout 的 JSON-lines 协议传回；DataFrame 转 CSV 传回后在主进程还原；单行与行数有上限 |

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
| `runner.py` | 沙箱入口：环境设置、白名单命名空间、执行、序列化 |
| `executor.py` | 主进程侧：审查、渲染最小沙箱配置、spawn、deadline 读行、超时强杀、协议解码 |

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
- `llm_models`：`explain_data`、`predict_hdb_price` 在子进程里自建 LLM 客户端。

其余配置项不写入该文件：特权库 `mysql`、系统库 `mysql_sys` 在沙箱内不被使用；`enable_*`、
`server_*`、`code_exec` 等也不被子进程读取。该文件随 workdir 一起删除；写入失败即中止
（fail-closed），不回退到特权 `config.yaml`。

## 五、配置项与超限行为（`config/config.yaml` → `code_exec`）

```yaml
code_exec:
  timeout: 120        # 总超时秒数（主进程墙钟计时）
  max_memory_mb: 1536 # 内存上限
  cpu_rate: 120       # CPU 秒数上限
  max_processes: 64   # 进程/线程数上限
  max_file_mb: 64     # 单文件大小上限
  max_df_rows: 50000  # DataFrame 超过此行数则截断后再传回
  max_line_mb: 20     # 单条协议行硬上限
```

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
| 主程序被拖垮/挂死/资源耗尽；特权对象引用泄露；配置密钥被读；文件写失控；网络库被 import；死循环与内存炸弹 | 同账户内核级逃逸（理论存在）；工具函数本身被滥用刷配额（靠数据库侧超时/限流缓解）；强网络物理隔离（靠可选防火墙补） |

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
