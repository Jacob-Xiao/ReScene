# ReScene 高并发应对方案

> 目标：让 `lib/run/app_DB.py` 在多客户端并发访问下保持稳定、可观测、不烧穿
> OpenAI 配额；前端杜绝重复提交。单机（Windows）部署优先，不引入分布式过度设计。

## 1. 瓶颈分析（按并发压力排序）

| # | 瓶颈 | 现状 | 并发下会发生什么 |
|---|------|------|------------------|
| 1 | Flask 开发服务器 (`app.run`) | 单线程按请求串行 | 开发服务器不支持生产并发，长请求（YOLO/GPT 30s+）阻塞一切 |
| 2 | YOLO 推理 (`model.predict`) | 无并发控制 | ultralytics 推理非线程安全；并发调用可能崩溃或显存溢出 |
| 3 | OpenAI `/makeGPT` | 无配额保护 | 并发重试会瞬间烧穿 API 配额（每张图都计费） |
| 4 | MySQL 连接池 | pool_size=5 硬编码 | WSGI 多线程下连接争抢，>5 并发日志写入排队 |
| 5 | Ollama 代理 | 每次请求新建连接 | 无 keep-alive，握手开销累积 |
| 6 | OpenAI 客户端 | import 时急切初始化 | 无 API key 时整个服务无法启动（可用性问题） |
| 7 | 前端按钮 | 加载中仍可点击 | 双击 = 重复付费请求、重复分割 |

## 2. 升级方案（本次执行）

| # | 措施 | 实现 | 参数（env） |
|---|------|------|-------------|
| 1 | 生产 WSGI 服务器 | waitress 多线程（Windows 友好，gunicorn 不支持 Win）；未安装时自动回退 Flask | `SERVER_THREADS`(默认8), `CONNECTION_LIMIT`(100), `CHANNEL_TIMEOUT`(120s) |
| 2 | YOLO 推理串行化 | 信号量限流 + 排队超时；超时返回 503 而非无限等待 | `MAX_YOLO_CONCURRENCY`(默认1=串行，GPU 场景最稳), `YOLO_QUEUE_TIMEOUT`(120s) |
| 3 | 限流保护配额 | 滑动窗口限流器（按客户端 IP）：全局 + GPT 独立更严限额；超限 429 + `Retry-After` | `RATE_LIMIT_PER_MINUTE`(120), `GPT_RATE_LIMIT_PER_MINUTE`(10) |
| 4 | DB 连接池扩容 | 池大小 env 化 | `DB_POOL_SIZE`(10，≥SERVER_THREADS) |
| 5 | Ollama 连接复用 | 模块级 `requests.Session`（keep-alive） | — |
| 6 | OpenAI 惰性初始化 | 双检锁单例；无 key 也能启动，仅 `/makeGPT` 受影响 | — |
| 7 | 前端防重复提交 | 加载中禁用 Segment / Send to GPT / 聊天发送 | — |
| 8 | 并发原语可测 | 限流器/单例抽到 `concurrency_utils.py`，纯 stdlib，独立单测覆盖多线程行为 | — |

## 3. 明确不过度设计的内容（单机部署）

- **不引入** Celery/Redis 任务队列、消息代理、多进程 GPU worker —— 单机单 GPU
  下 YOLO 串行即最优；进程池反而增加显存占用。
- **不引入** flask-limiter 等外部依赖 —— 30 行滑动窗口足够，且可独立测试。
- **不做** 水平扩缩容 —— waitress 单实例即可支撑本机桌面客户端群；真到多机
  规模时，把 YOLO 拆成独立推理服务（Triton/TorchServe）是正确路径，届时再议。

## 4. 容量预估（默认参数）

- `/yolo_seg`：串行推理，单张 ~1-3s（CPU）→ 稳态 ~20-60 req/min，超出排队
  （120s 超时保护）；GPU 可调 `MAX_YOLO_CONCURRENCY=2-4` 提升。
- `/makeGPT`：受 10 次/分钟硬限流保护，成本可控；单请求 10-60s。
- `/submit_content`：Ollama 本地推理，线程池并发转发，瓶颈在 Ollama 本身。
- `/health`、`/get_image`：纯 IO，waitress 8 线程轻松承载数百 req/min。

## 5. 验证方式

1. `python lib/run/test_concurrency.py` —— 限流器多线程正确性、单例唯一性、
   信号量超时（纯 stdlib，无需模型/DB/网络）。
2. `python lib/run/load_test.py [N] [URL]` —— 对运行中的服务发 N 并发
   `/health`（服务未启动时自动跳过）。压测示例：
   `python lib/run/app_DB.py` 另开终端 `python lib/run/load_test.py 64`。
3. `flutter analyze && flutter test` —— 前端回归（防重复提交不破坏现有 4 项测试）。

## 6. 部署清单

- `pip install -r requirements.txt`（新增 waitress）
- 按 `env.example` 新增并发相关变量（全部有默认值，可不填）
- 数据库账户建议专用账号（非 root），`DB_POOL_SIZE ≥ SERVER_THREADS`
- 服务只绑 `127.0.0.1`；若需局域网访问，改 `HOST=0.0.0.0` 前先加防火墙规则
