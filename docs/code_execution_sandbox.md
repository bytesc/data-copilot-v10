# LLM 生成代码执行安全方案（沙箱）

LLM 生成的 Python 代码不再在 FastAPI 主进程内直接 `exec`，而是经过五层防线的
一次性子进程沙箱执行。方案不依赖 Docker、零新增依赖，全部使用标准库，Windows /
Linux / macOS 共用同一套代码。

## 一、为什么需要它

原实现 `agent/tools/copilot/utils/code_executor.py` 在主进程内执行
`exec(code, globals(), ...)`，且因 `from agent.tools.tools_def import *`，
`globals()` 暴露了特权对象（`engine`、`llm` 等）：生成代码可读写任意文件、发起
任意网络请求、直接操作特权数据库；同时没有超时与资源上限（死循环会永久挂死
SSE）。matplotlib 的全局状态（figure、rcParams）也会跨请求泄漏，且非线程安全。

## 二、五层防线

| 层 | 位置 | 作用 |
|----|------|------|
| 1 代码审查 | `sandbox/policy.py` | 用 `ast` 解析代码，封锁危险/项目模块 import、危险调用（`eval/exec/open/...`）、逃逸属性（`__globals__/__class__/...`）。违规直接报错回传 LLM 重写（`code_exe_error` 重试链路），代码不执行 |
| 2 独立进程 | `sandbox/executor.py` + `sandbox/runner.py` | 每次新开一次性子进程执行，跑完销毁；崩溃/卡死/内存泄漏与主进程解耦；matplotlib 全新环境，figure/rcParams 随进程消亡，并发天然隔离 |
| 3 白名单环境 | `sandbox/runner.py` + 每次渲染的沙箱配置 | `exec` 不再传 `globals()`，只传手工构造的白名单命名空间（工具函数 + 预注入库）；沙箱进程读到的配置数据库账号已替换为只读账号，特权密码不进沙箱 |
| 4 限时限量强杀 | `sandbox/limits.py` | 总超时（默认 120s）到点强杀整棵进程树；内存/CPU/进程数/文件大小硬限；父进程退出则子进程自杀 |
| 5 输出收口 | 协议 | 结果只经 stdout 的 JSON-lines 协议传回；DataFrame 转 CSV 传回，主进程 `pd.read_csv` 还原；单行 20MB、5 万行截断上限 |

## 三、执行流水线

```
LLM 生成代码 → 提取 ```python 块（既有逻辑）
            → AST 审查（毫秒级）
                 ├─ 不合规 → 报错回传 LLM 重写（代码不执行）
                 └─ 通过 → 主进程写 job 临时文件
                        → spawn 子进程：python -E -s -u runner.py <job>（最小环境变量）
                        → runner：MPLBACKEND=Agg → 中文字体 → rlimit/看门狗
                                  → 白名单命名空间 exec
                        → 迭代 func() 的 yield 项 → JSON-lines 逐行传回
                        → 主进程还原 yield 项 → 既有 SSE 事件流照常推送
                        → 超时/异常 → kill_tree → 错误文本进入重试链路
```

主进程侧 `execute_in_sandbox()` 返回生成器：在调用方开始迭代时才启动子进程，迭代
提前结束时子进程被强杀。**不存在任何主进程内 `exec` 的 fallback 路径。**

## 四、文件清单

新建（`agent/tools/copilot/utils/sandbox/`）：

| 文件 | 职责 |
|------|------|
| `policy.py` | AST 审查规则与检查函数 |
| `limits.py` | 跨平台资源限制 + `kill_tree` + 孤儿看门狗（平台差异全部收敛于此，能力探测、不支持则降级） |
| `runner.py` | 沙箱入口：环境设置、白名单命名空间、执行、序列化 |
| `executor.py` | 主进程侧：审查、spawn、deadline 读行、超时强杀、协议解码 |

修改：

| 文件 | 改动 |
|------|------|
| `agent/tools/copilot/utils/code_executor.py` | 删除 `from agent.tools.tools_def import *` 与 `exec(...)`，委托沙箱；`execute_py_code` 签名不变 |
| `agent/agent.py` | 注入收窄：不再注入 `function_import` 与字体两行；`THIRD_MODULE` 去掉 `os`（`os` 被策略封锁） |
| `agent/tools/tools_def.py` | `get_save_image_path` 示例代码删除 import 行（避免 LLM 照抄被拦截） |
| `config/get_config.py` | 支持 `CODE_EXEC_CONFIG` 环境变量（主进程把每次渲染的沙箱配置路径传给它；主进程自身不受影响） |
| `config/config.yaml` | 新增 `code_exec` 段（timeout / max_memory_mb / cpu_rate / ...） |
| `data_access/db_conn.py` | `engine` 改为“有 `mysql` 才建，否则 None”：沙箱不提供 `mysql`，子进程里不建特权 engine |
| `data_access/sys_db_conn.py` | `sys_engine` 同理：沙箱不提供 `mysql_sys`，子进程里不建特权系统库 engine |

零改动：`agent.py` 主流程、`act.py`、`main.py`、前端、图片链路、重试机制、`perf_log`
计时。

### 沙箱配置：独立、最小、只传必要的

沙箱子进程**不读主配置**，也不复制主配置。主进程 (`sandbox/executor.py`) 只写一份
**最小**配置给子进程，内容就是白名单工具真正会读的几个值：

```python
data = {
    "mysql_readonly": config_data.get("mysql_readonly") or "",  # 唯一的数据库身份（只读）
    "static_path":    config_data.get("static_path", ""),       # 图片/CSV 链接前缀
    "llm_models":     config_data.get("llm_models") or [],      # explain_data / predict_hdb_price 用
}
# 写入 workdir/sandbox_config.yaml，路径经 CODE_EXEC_CONFIG 传给子进程
```

为什么只需要这三项（即子进程导入链真正读取的配置）：

- `mysql_readonly`：`tools_def` 用它建 `read_engine`；沙箱内被白名单工具使用的
  数据库访问**只有只读这一条**。
- `static_path`：`tools_def` / `custom_tools_def` 拼图片、CSV 的 URL。
- `llm_models`：`explain_data`、`predict_hdb_price` 会在子进程里自建 LLM 客户端。

其余一律**不传、也不处理**：

- 特权库 `mysql`、系统库 `mysql_sys`：沙箱内的工具根本不用（改造后
  `db_conn.engine` 与 `sys_db_conn.sys_engine` 均为“有配置才建、否则 None”），
  所以这两项直接被省略，子进程里**不存在**任何特权 engine。
- `enable_*` / `server_*` / `code_exec` 等：沙箱导入链不读它们，传了也没用，故不传。

这样主进程与子进程在配置上**解耦**：子进程拿到的是一份目的单一、最小化的输入，而不是
主配置的副本或镜像。文件写入 workdir、随执行结束一并删除；写入失败即中止
（fail-closed），绝不回退到特权 `config.yaml`。

## 五、配置项（`config/config.yaml` → `code_exec`）

```yaml
code_exec:
  timeout: 120        # 总超时秒数，到点强杀整棵进程树
  max_memory_mb: 1536 # 内存上限（POSIX RLIMIT_AS / Windows Job Object）
  cpu_rate: 120       # CPU 秒数上限（POSIX RLIMIT_CPU）
  max_processes: 64   # 进程/线程数上限（POSIX RLIMIT_NPROC）
  max_file_mb: 64     # 单文件大小上限（POSIX RLIMIT_FSIZE）
  max_df_rows: 50000  # DataFrame 超过此行数则截断后再传回
  max_line_mb: 20     # 单条协议行硬上限
```

平台不支持的限制项会被自动跳过（记一条 warning），不会导致崩溃。

## 六、跨平台说明

- 主流程零平台判断；差异只在 `limits.py` 内。
- 解释器加固 `python -E -s -u`（忽略 PYTHON* 环境变量与用户 site-packages，
  无缓冲输出），三端同义。
- 超时强杀：POSIX 杀进程组（`killpg`，MCP stdio 孙进程一并终结）；Windows 用
  ctypes 的 Job Object 整树终止（stdlib，无 pywin32），Job 不可用时回退
  `taskkill /T /F`。
- 孤儿防护：POSIX 侧 runner 的看门狗检测父进程消失后自杀；Windows 侧靠 Job 的
  `KILL_ON_JOB_CLOSE`。

## 七、可选宿主机加固（部署期手动，代码零改动）

防火墙封禁沙箱出站、目录 ACL 锁定配置，按需执行：

Linux（nftables，示例：限制沙箱用户出站）:

```bash
# 建议为沙箱单独运行用户，或直接限制解释器到仅允许回环/数据库白名单
sudo nft add table inet code_sandbox
sudo nft add chain inet code_sandbox output '{ type filter hook output priority 0; }'
sudo nft add rule inet code_sandbox output tcp dport { 3306 } accept
sudo nft add rule inet code_sandbox output drop
# 主配置只读锁定（编辑时先解锁；沙箱配置为每次渲染的临时文件，无需锁定）
sudo chattr +i config/config.yaml || true
```

macOS（pf，示例）：

```bash
# /etc/pf.anchors/code_sandbox: 仅放行数据库端口，其余阻断
sudo pfctl -a code_sandbox -f /etc/pf.anchors/code_sandbox
# 主配置只读
sudo chflags uchg config/config.yaml || true
```

Windows（PowerShell，示例：封禁解释器出站、只读配置）：

```powershell
New-NetFirewallRule -DisplayName "code_sandbox_block_outbound" -Direction Outbound `
  -Program "C:\Path\To\python.exe" -Action Block
New-NetFirewallRule -DisplayName "code_sandbox_allow_mysql" -Direction Outbound `
  -Program "C:\Path\To\python.exe" -Protocol TCP -RemotePort 3306 -Action Allow
# 主配置只读锁定（去掉可写 ACE）
icacls config\config.yaml /deny "%USERNAME%:(W,M)"
```

## 八、能力边界（诚实声明）

| 能防住 | 防不住（需容器才能防） |
|--------|----------------------|
| 主程序被拖垮/挂死/资源耗尽；特权对象引用泄露；配置密钥被读；文件写失控；网络库被 import；死循环与内存炸弹 | 同账户内核级逃逸（理论存在）；工具函数本身被滥用刷配额（靠数据库侧超时/限流缓解）；强网络物理隔离（靠可选防火墙补） |

## 九、验收用例

1. 全链路回归：画图/查数/文档生成，图片路径与 DataFrame 渲染不变。
2. `while True` → 超时强杀 → `code_exe_error` → LLM 重生成成功。
3. `import os` / `from agent... import engine` / `open("config.yaml")` → policy violation（代码不执行）。
4. `print(engine)` → `NameError`；沙箱内 `engine` 为只读身份。
5. 并发 5 个画图请求互不串扰、无字体异常。
6. 三平台各跑一遍：强杀后无孤儿进程。
7. 主进程执行路径清零：`grep -rn "exec(" agent/` 仅剩 `sandbox/runner.py`（沙箱内部执行）。
8. `perf_log.csv` 的 `code_exec_time` 增加约 1s（沙箱冷启动）。
