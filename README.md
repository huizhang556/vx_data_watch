# VX Data Watch

VX Data Watch 是一个本地优先、适配桌面端和移动端浏览器的微信视频号数据分析应用。它可以持久化导入视频号后台导出的 7 日 CSV、逐视频表格或截图 OCR 结果，并按单日或日期区间展示指标趋势、视频贡献和 AI 优化建议。

项目不需要微信扫码登录，也不会获取微信账号凭据。导入数据默认只保存在部署者自己的 SQLite 数据库中；只有用户主动请求 AI 分析时，所选区间的结构化统计数据才会发送到用户配置的 OpenAI 兼容接口。

## 主要功能

- 导入视频号后台 CSV，按日期持久化、去重并保留修订记录。
- 导入逐视频 CSV/XLSX，或通过截图 OCR 识别后人工确认。
- 查询单日、近 3/7/15/30 日或自定义日期区间。
- 展示播放、点赞、评论、分享、关注、转发、收藏等趋势和同期对比。
- 提供折线图、饼图、柱状图和逐视频播放贡献统计。
- 配置 OpenAI 兼容接口，获取模型列表、测试连接并生成分析报告。
- 支持本地用户和角色、审计日志、加密 API Key 与加密备份。
- Docker Compose 部署支持检测版本、选择版本、在线更新和自动重启。

各版本的详细功能请查看 [版本功能记录](VERSIONS.md)。

## 技术栈

- 后端：Python 3.12、FastAPI、SQLAlchemy 2、Alembic、Pydantic。
- 数据库：SQLite。
- 安全：Argon2id 密码哈希、AES-256-GCM 敏感配置加密。
- OCR：RapidOCR、ONNX Runtime、OpenCV、Pillow。
- 前端：React 19、TypeScript、Vite、Ant Design、Apache ECharts。
- 测试：Pytest、Ruff、Vitest、ESLint、Playwright。
- 部署：Docker Compose，或 Ubuntu/Debian 本地源码部署。

## 服务器最低要求

以下配置适用于个人或小团队使用。导入大量图片并执行 OCR 时会短暂占用较多内存和 CPU。

| 项目 | 最低要求 | 推荐配置 |
| --- | --- | --- |
| 操作系统 | Ubuntu 22.04 / Debian 12，64 位 | Ubuntu 24.04，64 位 |
| CPU | 2 核 x86_64 | 4 核 x86_64 |
| 内存 | 2 GB | 4 GB 或更多 |
| 可用磁盘 | 5 GB | 10 GB 或更多，并定期备份 |
| 网络 | 可访问 GitHub 和 Docker Hub | 稳定的公网连接 |
| 浏览器 | 当前版本 Chrome、Edge 或 Firefox | 当前版本 Chrome 或 Edge |

服务器还需开放一个 TCP 访问端口，默认是 `8000`，可以在 `.env` 中修改。公网部署应准备域名、HTTPS 证书和 Nginx/Caddy 等反向代理。

## 部署前配置

两种部署方式都从 `.env.example` 创建 `.env`：

```bash
cp .env.example .env
nano .env
```

常用配置如下：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `VX_BIND_ADDRESS` | 服务监听地址（反向代理场景建议保持本机监听） | `127.0.0.1` |
| `VX_PORT` | 浏览器访问端口 | `8000` |
| `VX_COOKIE_SECURE` | 仅通过 HTTPS 发送登录 Cookie | `false` |
| `VX_SESSION_DAYS` | 登录会话有效天数 | `14` |
| `VX_MAX_UPLOAD_MB` | 单个上传文件大小限制，单位 MB | `20` |
| `VX_MASTER_KEY` | Base64 编码的 32 字节加密主密钥 | 未设置时自动生成 |

例如服务器的 `8000` 端口已被占用，可将 `.env` 改为：

```dotenv
VX_PORT=3000
```

修改后通过 `http://服务器IP:3000` 访问。公网 HTTPS 部署还应设置：

```dotenv
VX_COOKIE_SECURE=true
```

如果暂时通过 `http://` 访问，即使服务器位于公网，也必须保持 `VX_COOKIE_SECURE=false`；否则浏览器不会保存登录 Cookie。修改配置后请重启 Compose 服务。

建议生成并妥善保存固定主密钥：

```bash
openssl rand -base64 32
```

将输出填写到 `.env` 的 `VX_MASTER_KEY=` 后面。不要把 `.env`、主密钥、数据库、备份、真实 CSV 或截图提交到 Git。主密钥丢失后，已保存的 AI Key 和加密备份将无法解密。

## Docker Compose 部署（推荐）

这种方式直接下载官方镜像，不需要安装 Python、Node.js，也不需要在服务器构建镜像。

### 1. 安装 Docker

先按照 Docker 官方文档为 [Ubuntu](https://docs.docker.com/engine/install/ubuntu/) 或 [Debian](https://docs.docker.com/engine/install/debian/) 安装 Docker Engine 和 Compose 插件。安装完成后检查：

```bash
docker --version
docker compose version
sudo systemctl enable --now docker
```

如普通用户执行 Docker 时提示权限不足，可以暂时在以下 Docker 命令前加 `sudo`。

### 2. 下载项目部署文件

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/huizhang556/vx_data_watch.git
cd vx_data_watch
cp .env.example .env
```

使用 `nano .env` 按“部署前配置”修改端口和安全参数。Docker 部署还支持以下变量：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `VX_IMAGE` | 应用镜像及版本 | `docker.io/litehub/vx-data-watch:0.3.5` |
| `VX_UPDATE_REPOSITORY` | 在线更新允许使用的固定仓库 | `litehub/vx-data-watch` |
| `VX_NODE_IMAGE` | 仅自行构建时使用的 Node 基础镜像 | `node:24-alpine` |
| `VX_PYTHON_IMAGE` | 仅自行构建时使用的 Python 基础镜像 | `python:3.12-slim` |

普通部署无需修改这些 Docker 变量。

### 3. 启动服务

```bash
docker compose -f docker-compose.yaml pull
docker compose -f docker-compose.yaml up -d --no-build
docker compose -f docker-compose.yaml ps
```

当 `app` 显示为 `healthy` 后，访问 `http://服务器IP:8000`；如果修改了 `VX_PORT`，请使用修改后的端口。首次打开时创建管理员账号，项目没有默认用户名或密码。

同时确认云服务器安全组和系统防火墙已经放行所用端口。例如使用 UFW 放行默认端口：

```bash
sudo ufw allow 8000/tcp
```

### 4. 日常管理

查看状态和日志：

```bash
docker compose -f docker-compose.yaml ps
docker compose -f docker-compose.yaml logs -f app
```

停止和重新启动：

```bash
docker compose -f docker-compose.yaml down
docker compose -f docker-compose.yaml up -d --no-build
```

停止服务不会删除数据。不要执行 `docker compose -f docker-compose.yaml down -v`，除非确定要永久删除数据库、主密钥和备份。

数据库和备份保存在 Docker 命名卷 `vx-data` 中。网页“系统设置”可以创建并下载 `.vxbackup` 加密备份，也可以在终端创建备份：

```bash
docker compose -f docker-compose.yaml exec app python -m app.cli backup
```

### Docker Compose 卸载

仅停止服务并保留数据库、主密钥、备份和导入数据：

```bash
cd /path/to/vx_data_watch
docker compose -f docker-compose.yaml down --remove-orphans
```

确认已经备份且不再需要项目数据后，删除 Compose 容器、命名卷和本地构建镜像：

```bash
cd /path/to/vx_data_watch
docker compose -f docker-compose.yaml down --volumes --remove-orphans --rmi local
```

最后再删除源码目录：

```bash
cd ..
rm -rf vx_data_watch
```

`--volumes` 会删除 `vx-data` 数据卷，可能造成数据库、主密钥和备份永久丢失。

### 5. 在线更新

管理员可在左侧“在线更新”中检查 Docker Hub 正式版本，选择高于当前版本且不高于最新版的版本进行更新。系统会先创建加密备份，再拉取镜像、替换应用容器并等待健康检查；失败时自动恢复旧容器，成功后页面自动重新连接。

主 Web 容器不访问 Docker Socket。只有不开放网络端口的 `updater` Companion 可以访问 Docker Engine，并且它只接受固定仓库 `litehub/vx-data-watch` 和三段式正式版本号。

## Ubuntu/Debian 源码部署

源码方式适合无法使用 Docker 或需要阅读、修改代码的用户。生产服务器仍优先推荐 Docker Compose。

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y git curl build-essential
curl -LsSf https://astral.sh/uv/install.sh | sh
```

重新打开终端后检查 `uv`：

```bash
uv --version
```

安装 Node.js 24。以下命令使用 NodeSource 软件源：

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt install -y nodejs
node --version
npm --version
```

### 2. 下载源码

使用 Git 克隆最新版：

```bash
git clone https://github.com/huizhang556/vx_data_watch.git
cd vx_data_watch
cp .env.example .env
```

也可以下载 `v0.3.0` 的 GitHub 自动源码归档，不需要项目维护者重复上传压缩包：

```bash
curl -L -o vx-data-watch-v0.3.0.tar.gz \
  https://github.com/huizhang556/vx_data_watch/archive/refs/tags/v0.3.0.tar.gz
tar -xzf vx-data-watch-v0.3.0.tar.gz
cd vx_data_watch-0.3.0
cp .env.example .env
```

使用 `nano .env` 按“部署前配置”修改参数。

源码部署还可以配置数据位置：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `VX_DATA_DIR` | 数据、自动主密钥和备份目录 | `./data` |
| `VX_DATABASE_URL` | SQLite 数据库连接地址 | `sqlite:///./data/vx_data.db` |

### 3. 首次启动

```bash
sh scripts/start-local.sh
```

脚本会自动完成以下操作：

1. 使用 `uv` 创建 Python 3.12 虚拟环境并安装后端和 OCR 依赖。
2. 安装前端依赖并构建生产网页。
3. 读取 `.env`，按 `VX_BIND_ADDRESS` 和 `VX_PORT` 启动 Web 服务。

首次安装耗时取决于服务器网络。看到 Uvicorn 启动日志后，通过 `http://服务器IP:8000` 或自定义端口访问。前台运行时按 `Ctrl+C` 停止。

### 4. 配置 systemd 常驻运行

直接关闭 SSH 窗口会终止前台服务。确认手动启动正常后按 `Ctrl+C` 停止，然后创建 systemd 服务。下面的 `<Linux用户名>` 和路径必须替换为服务器上的实际值：

```bash
sudo nano /etc/systemd/system/vx-data-watch.service
```

写入：

```ini
[Unit]
Description=VX Data Watch
After=network.target

[Service]
Type=simple
User=<Linux用户名>
WorkingDirectory=/home/<Linux用户名>/vx_data_watch
Environment="PATH=/home/<Linux用户名>/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/bin/sh /home/<Linux用户名>/vx_data_watch/scripts/start-local.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

保存后加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vx-data-watch
sudo systemctl status vx-data-watch
```

查看实时日志：

```bash
sudo journalctl -u vx-data-watch -f
```

### 5. 后续启动和更新源码

再次启动仍执行：

```bash
cd vx_data_watch
sh scripts/start-local.sh
```

使用 Git 部署时可更新源码：

```bash
cd vx_data_watch
git pull --ff-only origin main
sudo systemctl restart vx-data-watch
sudo systemctl status vx-data-watch
```

源码部署可以在网页中检查是否有新版本，但网页不会执行 Git 命令或控制宿主机进程。更新后需要用户在终端重新启动。

公网服务还应通过 Nginx 或 Caddy 提供 HTTPS，并在确认 HTTPS 可用后设置 `VX_COOKIE_SECURE=true`。

### 源码部署卸载

如果使用 systemd，先停止并禁用服务：

```bash
sudo systemctl disable --now vx-data-watch
sudo rm -f /etc/systemd/system/vx-data-watch.service
sudo systemctl daemon-reload
```

只清理源码环境并保留 `data/` 数据：

```bash
cd /path/to/vx_data_watch
rm -rf .venv frontend/node_modules frontend/dist .pytest_cache .ruff_cache
```

确认已经备份且不再需要数据库、主密钥、备份和导入数据后，删除整个源码目录：

```bash
cd ..
rm -rf vx_data_watch
```

源码卸载不会自动删除系统级的 Python、Node.js、uv、Nginx 或其他共享软件。删除前请确认 Nginx 配置不再引用本项目，并执行 `sudo nginx -t` 检查配置。

## 使用流程

1. 首次访问时创建管理员账号。
2. 在“系统设置”中创建要分析的视频号账号。
3. 在“数据导入”中导入后台 7 日 CSV。
4. 按需导入逐视频表格，或上传同一天的截图进行 OCR。
5. OCR 结果必须人工检查，确认日期、标题和数值后再入库。
6. 在“数据概览”和“视频贡献”中选择单日或区间查看统计。
7. 如需 AI 建议，在“AI 建议”中填写自己的兼容接口，先测试再保存。

重叠 CSV 日期不会产生重复记录；平台修订旧日期时，系统保存旧版本并使用新值。当前导出 CSV 没有独立收藏字段，缺失指标显示为“暂无数据”，不会当作 0。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。你可以在保留原始版权和许可声明的前提下使用、复制、修改、合并、发布和分发本项目。软件按“原样”提供，不附带任何明示或暗示担保。

Copyright (c) 2026 huizhang556
