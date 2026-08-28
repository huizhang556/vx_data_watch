# VX Data Watch

VX Data Watch 是一个本地优先、适配桌面端和移动端浏览器的微信视频号数据分析应用。它可以持久化导入视频号后台导出的 7 日 CSV、逐视频表格或截图 OCR 结果，并按单日或日期区间展示指标趋势、视频贡献和 AI 优化建议。

项目不需要微信扫码登录，也不会获取微信账号凭据。导入数据默认只保存在部署者自己的 SQLite 数据库中；只有用户主动请求 AI 分析时，所选区间的结构化统计数据才会发送到用户配置的 OpenAI 兼容接口。

## 先看这里：选择部署方式

- **一键运维脚本**：适合首次安装、终端更新、备份迁移和卸载；应用无法打开时，也可以通过 SSH 维护。
- **Docker Compose（手动部署）**：服务器只需安装 Docker，直接使用已发布镜像，不需要安装 Python、Node.js 或 OCR 构建依赖。
- **Ubuntu/Debian 源码部署**：适合需要阅读或修改源码的用户，需要自行安装 Python、Node.js、uv 以及 OCR 依赖。

默认部署地区为海外服务器并使用 Docker Hub。中国大陆服务器在一键安装时会显示公网 IP 检测结果和镜像建议，用户确认后才可选择阿里云 ACR；检测失败时由用户手动选择。无论哪种方式，镜像地址都可以通过 `.env` 的 `VX_IMAGE` 明确指定。

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
| 操作系统 | Ubuntu 24.04 / Debian 12，64 位 | Ubuntu 24.04，64 位 |
| CPU | 2 核 x86_64 | 4 核 x86_64 |
| 内存 | 2 GB | 4 GB 或更多 |
| 可用磁盘 | 5 GB | 10 GB 或更多，并定期备份 |
| 网络 | 可访问 GitHub 和 Docker Hub | 稳定的公网连接 |
| 浏览器 | 当前版本 Chrome、Edge 或 Firefox | 当前版本 Chrome 或 Edge |

服务器还需开放一个宿主机 TCP 访问端口。Docker Compose 和一键脚本默认使用 `10000`，通过 `VX_HOST_PORT` 修改；容器内部端口始终固定为 `8000`。源码部署没有宿主机端口映射，应用直接使用 `VX_PORT`，默认也是 `8000`。公网部署应准备域名、HTTPS 证书和 Nginx/Caddy 等反向代理。

## 部署前配置

Docker Compose、源码部署和一键脚本最终都使用 `.env` 配置文件；手动部署从 `.env.example` 创建，一键脚本会自动生成并填充必要的随机配置：

```bash
cp .env.example .env
nano .env
```

## 必须配置的内容

大多数用户只需要确认下面两项，其他配置可以保持默认值：

| 变量 | 什么时候需要配置 | 示例 |
| --- | --- | --- |
| `VX_IMAGE` | Docker Compose 部署时确认镜像源；海外默认 Docker Hub，中国大陆可按提示选择阿里云 ACR | `docker.io/litehub/vx-data-watch:latest` |
| `VX_MASTER_KEY` | 用于加密密钥和备份；一键脚本会自动生成，手动部署可留空让程序生成 | `openssl rand -base64 32` 的输出 |

只有启用对应功能时才需要配置：

- 邮箱注册或密码重置：将 `VX_REGISTRATION_ENABLED=true`，并填写 SMTP 服务器、用户名、密码和发件人。
- Cloudflare Turnstile：将 `VX_CAPTCHA_ENABLED=true`，并填写站点密钥和服务端密钥。
- HTTPS：将 `VX_COOKIE_SECURE=true`。

通常不需要修改：

- Docker Compose 对外端口默认 `VX_HOST_PORT=10000`，容器内部端口固定 `8000`。
- 源码部署应用端口默认 `VX_PORT=8000`。
- 数据目录、数据库地址、会话时长、上传大小和基础镜像均可先使用默认值。

不要把 SMTP 密码、Turnstile 密钥、主密钥或真实数据提交到 Git。

例如服务器的 `10000` 端口已被占用，可将 Docker Compose 的 `.env` 改为：

```dotenv
VX_HOST_PORT=3000
```

修改后通过 `http://服务器IP:3000` 访问，容器内部仍使用 `8000`。公网 HTTPS 部署还应设置：

```dotenv
VX_COOKIE_SECURE=true
```

如果暂时通过 `http://` 访问，即使服务器位于公网，也必须保持 `VX_COOKIE_SECURE=false`；否则浏览器不会保存登录 Cookie。修改配置后请重启 Compose 服务。

建议生成并妥善保存固定主密钥：

```bash
openssl rand -base64 32
```

将输出填写到 `.env` 的 `VX_MASTER_KEY=` 后面。不要把 `.env`、主密钥、数据库、备份、真实 CSV 或截图提交到 Git。主密钥丢失后，已保存的 AI Key 和加密备份将无法解密。

## 一键运维脚本（Ubuntu 24.04 / Debian 12）

脚本固定将项目安装到 `/opt/vx-data-watch`，Docker Compose 宿主机默认端口为 `10000`，容器内部端口固定为 `8000`，镜像为 `litehub/vx-data-watch:latest`。使用前建议先下载并审阅脚本：

```bash
sudo apt update && sudo apt install -y curl
curl -fL --retry 5 -o vx-data.sh https://raw.githubusercontent.com/huizhang556/vx_data_watch/main/scripts/vx-data.sh
less vx-data.sh
chmod +x vx-data.sh
sudo ./vx-data.sh install
```

安装时会检查 Docker、Compose、`curl`、`openssl` 和 `rsync`。缺少 Docker 或依赖时，脚本会先询问是否自动安装；拒绝后立即退出。脚本会尝试检测服务器公网 IP 所在国家，仅将结果作为建议：海外默认建议 Docker Hub，中国大陆可选择 Docker Hub 或阿里云 ACR，检测失败时由用户手动选择。中国大陆服务器还可在交互步骤选择 Docker 镜像加速地址。加速地址并非永久可靠，连续失败时请更换云服务器或手动配置代理。所有下载和镜像拉取都带有限次重试。

常用命令：

```bash
sudo /opt/vx-data-watch/vx-data.sh update             # 先备份再更新 latest
sudo /opt/vx-data-watch/vx-data.sh update 0.4.2       # 更新到指定版本
sudo /opt/vx-data-watch/vx-data.sh backup              # 备份到 /home/vx_backed
sudo /opt/vx-data-watch/vx-data.sh backup /data/backup # 自定义备份目录
sudo /opt/vx-data-watch/vx-data.sh migrate             # 导出后 rsync 到另一台服务器
sudo /opt/vx-data-watch/vx-data.sh uninstall           # 选择保留数据或完全卸载
```

`migrate` 需要目标服务器已启用 SSH，使用密钥或密码完成认证；默认只迁移数据库、配置和分析数据，并支持断点续传，脚本会询问是否包含下载目录中的大文件。目标端得到的是数据卷归档，需要在目标服务器手动解压/恢复到 `vx-data` 卷。备份前会检查目标目录可写及可用空间，请预留不少于当前数据量再加 10 MB。

卸载分为“删除容器但保留数据”和“删除容器、数据卷及项目目录”，完全卸载前会再次确认，并单独询问保留当前镜像、删除当前镜像或删除全部相关镜像。删除数据卷不可恢复，请先执行备份。首次安装会自动生成随机 `VX_MASTER_KEY`，不要公开 `.env` 或备份文件。

网页中的在线更新和加密备份仍可继续使用；一键脚本适用于服务器初次安装、终端更新、迁移和卸载，不会保存 SSH 凭据。

脚本安装完成后不要求配置 Nginx。没有域名时直接使用提示的服务器 IP 和 `VX_HOST_PORT` 访问；需要域名或 HTTPS 时，再按文末的 Nginx 指引由用户自行配置。

## Docker Compose 部署（手动）

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
| `VX_IMAGE` | 应用镜像及版本 | `docker.io/litehub/vx-data-watch:latest` |
| `VX_UPDATE_REPOSITORY` | 在线更新允许使用的固定仓库 | `litehub/vx-data-watch` |
| `VX_NODE_IMAGE` | 仅自行构建时使用的 Node 基础镜像 | `node:24-alpine` |
| `VX_PYTHON_IMAGE` | 仅自行构建时使用的 Python 基础镜像 | `python:3.12-slim` |

海外服务器默认使用 Docker Hub。中国大陆服务器只有在用户明确选择时才使用阿里云 ACR，例如：

```dotenv
VX_IMAGE=crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com/zhang_spaces/vx-data-watch:latest
```

使用 ACR 镜像时，请先按本地发布手册登录 ACR。终端一键更新会沿用 `.env` 中当前镜像的仓库地址；网页在线更新只允许在 Docker Hub 和已配置的阿里云 ACR 两个受信任仓库之间选择。

普通部署无需修改这些 Docker 变量。

### 3. 启动服务

```bash
docker compose -f docker-compose.yaml pull
docker compose -f docker-compose.yaml up -d --no-build
docker compose -f docker-compose.yaml ps
```

当 `app` 显示为 `healthy` 后，访问 `http://服务器IP:10000`；如果修改了 `VX_HOST_PORT`，请使用修改后的宿主机端口。首次打开时创建管理员账号，项目没有默认用户名或密码。

同时确认云服务器安全组和系统防火墙已经放行所用端口。例如使用 UFW 放行默认端口：

```bash
sudo ufw allow 10000/tcp
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

### Docker Compose 卸载项目

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

Docker Compose 部署完成后不要求配置 Nginx。没有域名时直接使用服务器 IP 和 `VX_HOST_PORT` 访问；需要域名或 HTTPS 时，再按文末的 Nginx 指引配置。

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

也可以下载指定版本的 GitHub 自动源码归档，不需要项目维护者重复上传压缩包：

```bash
VERSION=0.4.2
curl -L -o vx-data-watch-v${VERSION}.tar.gz \
  https://github.com/huizhang556/vx_data_watch/archive/refs/tags/v${VERSION}.tar.gz
tar -xzf vx-data-watch-v${VERSION}.tar.gz
cd vx_data_watch-${VERSION}
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

### 源码部署卸载项目

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

源码部署完成后不要求配置 Nginx。没有域名时直接使用服务器 IP 和 `VX_PORT` 访问；需要域名或 HTTPS 时，再按文末的 Nginx 指引配置。

## Nginx 反向代理（可选）

三种部署方式都不强制要求域名或 Nginx。没有域名时可以直接使用服务器 IP 和端口；如果需要域名、HTTPS 或统一入口，再由用户自行安装并配置 Nginx。先确认应用本机访问正常，再按实际部署方式选择上游端口：源码部署通常为 `127.0.0.1:8000`，Docker Compose/一键脚本默认是 `127.0.0.1:10000`。

安装 Nginx：

```bash
sudo apt update
sudo apt install -y nginx
```

创建站点配置，将 `analytics.example.com` 替换为你的域名：

```bash
sudo nano /etc/nginx/sites-available/vx-data-watch
```

写入：

```nginx
server {
    listen 80;
    server_name analytics.example.com;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
}
```

启用配置并检查：

```bash
sudo ln -s /etc/nginx/sites-available/vx-data-watch /etc/nginx/sites-enabled/vx-data-watch
sudo nginx -t
sudo systemctl reload nginx
```

确认域名可以通过 HTTP 访问后，再申请 HTTPS 证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d analytics.example.com
```

HTTPS 正常后，在 `.env` 中设置 `VX_COOKIE_SECURE=true`，然后重启对应部署方式的服务：

```bash
sudo systemctl restart vx-data-watch       # 源码部署
# Docker Compose/一键脚本：docker compose -f docker-compose.yaml up -d --no-build
```

Docker Compose 的端口映射默认是 `127.0.0.1:10000:8000`；如果修改了 `VX_HOST_PORT`，将 Nginx 的 `proxy_pass` 端口同步改为新的宿主机端口。一键脚本安装的项目同样按此规则配置。

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
