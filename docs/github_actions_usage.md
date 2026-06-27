# GitHub Actions 使用说明

本项目包含两个 GitHub Actions 工作流：

1. `Python CI`：每次 push 或 pull request 自动运行，只做轻量语法检查。
2. `OSS to ClickHouse Pipeline`：手动触发，用于从 OSS 导入 ClickHouse、计算指数、生成图表并回传 OSS。

## 1. 配置 GitHub Secrets

进入 GitHub 仓库：

```text
Settings -> Secrets and variables -> Actions -> New repository secret
```

需要添加以下 Secrets：

```text
OSS_ACCESS_KEY_ID
OSS_ACCESS_KEY_SECRET
OSS_ENDPOINT
OSS_BUCKET

CLICKHOUSE_HOST
CLICKHOUSE_PORT
CLICKHOUSE_USER
CLICKHOUSE_PASSWORD
CLICKHOUSE_DB
CLICKHOUSE_SECURE
CLICKHOUSE_VERIFY
```

本项目当前云 ClickHouse 使用 HTTPS 时可参考：

```text
CLICKHOUSE_PORT=8443
CLICKHOUSE_DB=price_index
CLICKHOUSE_SECURE=true
CLICKHOUSE_VERIFY=false
```

`CLICKHOUSE_VERIFY=false` 是因为本机 Python 环境没有导入阿里云 ClickHouse 的 CA 证书。它仍然走 HTTPS 加密，只是跳过证书链校验。若后续接入 CA 证书，可改为 `true`。

## 2. 手动触发数据管道

进入 GitHub 仓库：

```text
Actions -> OSS to ClickHouse Pipeline -> Run workflow
```

推荐先小规模 smoke：

```text
run_import=true
daily_limit=5
run_compute=true
upload_result=true
```

确认成功后，如果确实要跑全量：

```text
daily_limit=0
```

`daily_limit=0` 表示导入 OSS `raw/daily_price/` 下全部日文件，会写入约 2600 万行，运行时间和云资源费用都会增加。

## 3. 白名单注意事项

如果工作流使用 GitHub 托管 Runner，访问云 ClickHouse 的公网 IP 不是本机 `120.199.34.116`，而是 GitHub Runner 的出口 IP。因此当前只允许本机 IP 的白名单会导致 Actions 连接失败。

如果工作流使用本机 self-hosted runner，访问云 ClickHouse 的出口 IP 仍然取决于当前宽带公网出口。这个 IP 可能随网络、重拨或运营商 NAT 变化。若日志中出现：

```text
ConnectionRefusedError: [WinError 10061]
HTTPSConnectionPool(...): Failed to establish a new connection
```

优先检查 Actions 日志里 `Diagnose ClickHouse network` 步骤打印的 `Runner public IP`，并将该 IP 加入阿里云 ClickHouse 的白名单或安全组。当前仓库的 workflow 会在 TCP 端口连不通时提前失败，避免拖到 `init_clickhouse.py` 才输出很长的 Python 栈。

可选处理方式：

1. 使用本机或云服务器作为 GitHub self-hosted runner，使运行环境出口 IP 固定。
2. 演示时临时放宽 ClickHouse 白名单，工作流跑完后立即恢复。
3. 只在 Actions 中运行 `Python CI`，云端全量管道仍由本机手动执行。

出于安全考虑，不建议长期开放 `0.0.0.0/0`。

## 4. 本地等价命令

云端工作流与本地命令等价：

```powershell
py scripts\init_clickhouse.py
py scripts\load_from_oss_to_clickhouse.py --limit 5
py scripts\compute_index.py
py scripts\plot_index.py
py scripts\upload_result_to_oss.py
```

全量导入：

```powershell
py scripts\load_from_oss_to_clickhouse.py --full
```
