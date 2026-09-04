# VX Data Watch

HG工具站（VX Data Watch）是一个多功能、综合性的工具类网站。其主要提供的功能有：
1.单用户系统登录、注册。本地多视频号管理和数据支持、支持会员功能用户隔离。支持管理员登录管理设置后台系统。
2.本地优先的微信视频号数据分析平台，适配桌面端和移动端浏览器。系统支持视频号运营数据导入、OCR 识别、数据分析，趋势分析，AI建议等功能。
3.油管视频下载，提供油管视频下载和本地保存功能(需要用户提供自己的cookies)。支持视频列表分析和视频下载。支持视频转码（通用转为mp4格式）。
4.提供一站式AI对话服务。支持聊天模式，生图模式，生视频模式。
5.（管理员权限）一站式在线更新服务，AI接入配置，用户数据加密备份，系统设置等。
6.支持国内/国外服务器一键脚本部署，一键更新，一键数据迁移和备份，省心快捷。同时也支持docker compose和本地源码部署。
项目数据默认保存在部署者选择的 SQLite 或 PostgreSQL 数据库中；用户主动请求 AI 分析或 AI 速问时，相关数据才会发送到管理员配置并授权使用的模型接口，确保用户隐私保护。

## 主要功能

- **数据分析**：导入视频号后台 CSV、逐视频表格或截图 OCR；支持去重、修订记录、日期区间查询、趋势图表、视频贡献和 AI 分析建议。
- **视频号账号**：每个用户可维护多个视频号账号，分析数据按账号隔离；管理员可统一管理所有账号。
- **AI 速问**：提供独立的 AI 对话窗口，支持分类和会话树、置顶/排序、历史恢复、搜索、批量删除、Markdown/JSON 导出，以及文本和图片附件预览。搜索时自动切换为扁平结果列表，显示所属分类并支持直接恢复历史会话。
- **AI 配置**：管理员维护全局的官方 API 或 OPENAI 兼容接口，查询模型、测试连通性并发布可用配置；普通用户只能选择管理员已发布的配置，不能查看或修改 API Key。
- **AI 快速配置**：每个用户最多保存 5 个常用模型组合，支持创建日期、关联分析数量、编辑、应用和删除，并在 AI 建议页面持久化保存。
- **模型协议**：支持 OpenAI Chat Completions/Responses，以及 Anthropic Messages、Gemini、Grok 等协议适配。
- **视频下载**：支持下载配置、Cookies/代理检测、格式和质量选择；下载内容分为下载队列和完成队列，支持批量及单任务暂停/继续/取消/删除，并可将服务器完成文件保存到本地。
- **用户与权限**：支持管理员、超级会员、会员和普通用户等级；用户资料、视频号账号、AI 会话和使用次数按用户持久化并隔离。
- **系统安全**：支持邮箱注册与密码重置、Cloudflare Turnstile、人机验证开关、审计日志、加密 API Key 和加密备份。
- **主题界面**：提供晨曦、玫瑰柔和、薰衣草、雾蓝、薄荷和奶油六套主题，支持手动选择、保存到浏览器本地；跟随系统时统一使用晨曦模式。新增功能区域统一使用 CSS Variables，覆盖背景、卡片、文字、边框、按钮、链接及成功/警告/错误状态。
- **部署与运维**：支持一键安装/更新/备份迁移/卸载、Docker Compose 和 Ubuntu/Debian 源码部署；数据库可选择 SQLite 或 PostgreSQL，代码源支持 GitHub/Gitee，镜像源支持 Docker Hub/阿里云 ACR。
- **在线更新**：管理员可检测版本、选择受信任镜像源并执行更新；更新前自动备份，失败时回滚，普通用户无更新权限。

各版本的详细功能请查看 [版本功能记录](VERSIONS.md)。

## 技术栈

- 后端：Python 3.12、FastAPI、SQLAlchemy 2、Alembic、Pydantic。
- 数据库：SQLite（默认）或 PostgreSQL（可选）。
- 安全：Argon2id 密码哈希、AES-256-GCM 敏感配置加密。
- OCR：RapidOCR、ONNX Runtime、OpenCV、Pillow。
- 前端：React 19、TypeScript、Vite、Ant Design、Apache ECharts。
- 测试：Pytest、Ruff、Vitest、ESLint、Playwright。
- 部署：Docker Compose，或 Ubuntu/Debian 本地源码部署。

## 服务器最低要求

以下配置适用于个人或小团队使用。导入大量图片并执行 OCR 时会短暂占用较多内存和 CPU。

| 项目 | 最低要求 | 推荐配置 |
| --- | --- | --- |
| 操作系统 | Ubuntu 22.04/24.04/26.04、Debian 11/12/13，64 位 | Ubuntu 24.04 或 Debian 12，64 位 |
| CPU | 2 核 x86_64 | 4 核 x86_64 |
| 内存 | 2 GB | 4 GB 或更多 |
| 可用磁盘 | 5 GB | 10 GB 或更多，并定期备份 |
| 网络 | 可访问 GitHub/Gitee 代码源和 Docker Hub/阿里云 ACR 至少各一个 | 稳定的公网连接 |
| 浏览器 | 当前版本 Chrome、Edge 或 Firefox | 当前版本 Chrome 或 Edge |

服务器还需开放一个宿主机 TCP 访问端口。Docker Compose 和一键脚本默认使用 `10000`，通过 `VX_HOST_PORT` 修改；容器内部端口始终固定为 `8000`。源码部署没有宿主机端口映射，应用直接使用 `VX_PORT`，默认也是 `8000`。公网部署应准备域名、HTTPS 证书和 Nginx/Caddy 等反向代理。

## 部署前配置（手动部署适用）

本节仅适用于手动 Docker Compose 和源码部署。一键运维脚本不需要提前创建或编辑 `.env`，脚本会自动生成配置并填充随机密钥；请直接阅读下一节并执行安装命令：

```bash
cp .env.example .env
nano .env
```

代码仓库以 GitHub 为主：`https://github.com/huizhang556/vx_data_watch`；无法访问时可使用 Gitee：`https://gitee.com/huizhang556/vx_data_watch`。镜像默认使用 Docker Hub：`docker.io/litehub/vx-data-watch`；中国大陆服务器可在明确选择后使用阿里云 ACR：`crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com/zhang_spaces/vx-data-watch`。

## 必须配置的内容

大多数用户只需要确认下面两项，其他配置可以保持默认值：

| 变量 | 什么时候需要配置 | 示例 |
| --- | --- | --- |
| `VX_IMAGE` | Docker Compose 部署时确认镜像源；一键脚本会按地区默认选择，海外为 Docker Hub，中国大陆为阿里云 ACR | `docker.io/litehub/vx-data-watch:latest` |
| `VX_MASTER_KEY` | 用于加密密钥和备份；一键脚本会自动生成，手动部署可留空让程序生成 | `openssl rand -base64 32` 的输出 |

登录凭证默认有效 12 小时（`VX_SESSION_HOURS=12`）。超过有效期未重新登录时，凭证会失效；重新登录后会重新签发 12 小时凭证。可在 `.env` 中按小时调整该值，修改后需重启服务。

选择 PostgreSQL 时，必须同时设置 `VX_DATABASE_MODE=postgres`、`VX_DATABASE_URL` 以及 PostgreSQL 用户、密码和数据库名；不设置时使用 SQLite。

应用启动时会自动执行 Alembic 数据库迁移。迁移会沿单一版本链升级，不会覆盖业务数据；在线更新和一键更新会先备份，再启动新容器并等待健康检查，迁移或启动失败时自动恢复旧版本。升级前仍建议确认备份可用，不要手动删除 `alembic_version` 表或迁移文件。

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

## 一键运维脚本（小白推荐安装方式）

脚本和项目文件统一放在 `/opt/vx-data-watch`，其中包含 `vx-data.sh`、`.env` 和 `docker-compose.yaml`。宿主机默认端口为 `10000`，容器内部端口为 `8000`。无需提前准备 `.env` 或手动安装 Docker；脚本会检测服务器地区并给出默认源：中国大陆默认使用 Gitee 和阿里云 ACR，其他地区默认使用 GitHub 和 Docker Hub，用户仍可在提示处手动改选。

```bash
sudo apt update && sudo apt install -y curl
sudo mkdir -p /opt/vx-data-watch && cd /opt/vx-data-watch
# 海外：
sudo curl -fL --retry 5 -o vx-data.sh https://raw.githubusercontent.com/huizhang556/vx_data_watch/main/scripts/vx-data.sh
# 中国大陆改用：
# sudo curl -fL --retry 5 -o vx-data.sh https://gitee.com/huizhang556/vx_data_watch/raw/main/scripts/vx-data.sh
sudo chmod 700 vx-data.sh && sudo ./vx-data.sh install
```

安装时脚本会检测网络和公网地区，提示选择镜像源、镜像加速和数据库。数据库默认 SQLite，也可以选择自动部署 PostgreSQL；缺少 Docker 或依赖时会先征得同意再安装。首次安装会自动生成随机密钥和 PostgreSQL 密码。安装完成后直接访问提示的 `http://服务器IP:10000`，不需要 Nginx；需要域名或 HTTPS 时再按文末指引自行配置。

常用维护命令：

```bash
sudo /opt/vx-data-watch/vx-data.sh update             # 备份后更新 latest
sudo /opt/vx-data-watch/vx-data.sh update 0.5.1       # 更新到指定版本
sudo /opt/vx-data-watch/vx-data.sh rollback           # 按更新记录恢复上一版本
sudo /opt/vx-data-watch/vx-data.sh backup              # 备份到 /home/vx_backed
sudo /opt/vx-data-watch/vx-data.sh backup /data/backup # 自定义备份目录
sudo /opt/vx-data-watch/vx-data.sh migrate             # rsync 迁移到另一台服务器
sudo /opt/vx-data-watch/vx-data.sh uninstall           # 选择保留数据或完全卸载
```

更新会自动备份并在失败时回滚；备份和迁移会包含数据库，视频等大文件由用户选择是否携带。迁移需要目标服务器 SSH，所有网络操作带有限次重试。完全卸载会再次确认，并分别询问是否删除数据卷和镜像；删除数据不可恢复，请先备份。

## Docker Compose 部署（主力推荐安装方式）

这种方式直接下载官方镜像，不需要安装 Python、Node.js，也不需要在服务器构建镜像。

### 1. 安装 Docker

先按照 Docker 官方文档为 [Ubuntu](https://docs.docker.com/engine/install/ubuntu/) 或 [Debian](https://docs.docker.com/engine/install/debian/) 安装 Docker Engine 和 Compose 插件。本项目一键脚本支持 Ubuntu 22.04、24.04、26.04 以及 Debian 11、12、13（均为 64 位）；安装完成后检查：

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
```

如果服务器无法访问 GitHub，请改用 Gitee 同步仓库：

```bash
git clone https://gitee.com/huizhang556/vx_data_watch.git
```

然后进入目录并创建配置文件：

```bash
cd vx_data_watch
cp .env.example .env
```

进入项目目录后，复制 `.env.example` 为 `.env`，通常只需按“部署前配置”修改对外端口和安全参数。以下 Docker 变量仅在需要更换镜像或自行构建时修改：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `VX_IMAGE` | 应用镜像地址和版本 | `docker.io/litehub/vx-data-watch:latest` |
| `VX_UPDATE_REPOSITORY` | 在线更新使用的镜像仓库 | `litehub/vx-data-watch` |
| `VX_NODE_IMAGE` | 自行构建时的 Node 基础镜像 | `node:24-alpine` |
| `VX_PYTHON_IMAGE` | 自行构建时的 Python 基础镜像 | `python:3.12-slim` |

海外服务器默认使用 Docker Hub。中国大陆服务器只有在用户明确选择时才使用阿里云 ACR，例如：

```dotenv
VX_IMAGE=crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com/zhang_spaces/vx-data-watch:latest
```

当前配置的阿里云 ACR 命名空间和镜像仓库为公开仓库，正常安装、拉取和在线更新无需预先登录。终端一键更新会沿用 `.env` 中当前镜像的完整仓库地址；网页在线更新只允许在 Docker Hub 和已配置的阿里云 ACR 之间选择。只有服务器实际返回 `unauthorized` 或 `authentication required` 时，才需要检查 ACR 公开权限或执行 `docker login`。

普通部署无需修改这些 Docker 变量。

如果选择内置 PostgreSQL，请在 `.env` 中设置 `VX_DATABASE_MODE=postgres` 及对应数据库参数，并用 `docker compose --profile postgres ...` 执行后续命令；默认 SQLite 继续使用普通的 `docker compose ...` 命令。

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

SQLite 数据库和备份保存在 Docker 命名卷 `vx-data` 中；使用内置 PostgreSQL 时另有 `vx-postgres` 数据卷。网页“系统设置”可以创建并下载 `.vxbackup` 加密备份，也可以在终端创建备份：

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

管理员可在左侧“在线更新”中检查当前配置的 Docker Hub 或阿里云 ACR 正式版本，选择高于当前版本且不高于最新版的版本进行更新。系统会先创建备份，再拉取镜像、替换应用容器并等待健康检查；失败时自动恢复旧容器，成功后页面自动重新连接。

主 Web 容器不访问 Docker Socket。只有不开放网络端口的 `updater` Companion 可以访问 Docker Engine，并且它只接受固定仓库 `litehub/vx-data-watch` 和三段式正式版本号。

Docker Compose 部署完成后不要求配置 Nginx。没有域名时直接使用服务器 IP 和 `VX_HOST_PORT` 访问；需要域名或 HTTPS 时，再按文末的 Nginx 指引配置。

## Ubuntu/Debian 源码部署（开发者推荐）

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

无法访问 GitHub 时，将仓库地址替换为 `https://gitee.com/huizhang556/vx_data_watch.git`。

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
| `VX_DATABASE_URL` | 数据库连接地址；默认 SQLite，PostgreSQL 使用 `postgresql+psycopg://...` | `sqlite:///./data/vx_data.db` |

源码部署默认使用 SQLite；若使用 PostgreSQL，请准备可访问的 PostgreSQL 服务并填写连接地址，依赖会随项目安装。内置 PostgreSQL 容器仅适用于一键脚本和 Docker Compose 部署。已有 `.env` 的升级不会自动切换数据库。

手动使用内置 PostgreSQL 时，在 `.env` 中填写 `VX_DATABASE_MODE=postgres`、`VX_POSTGRES_USER`、`VX_POSTGRES_PASSWORD`、`VX_POSTGRES_DB` 和 `VX_DATABASE_URL`，并使用 `docker compose --profile postgres up -d` 启动。SQLite 数据卷为 `vx-data`，PostgreSQL 数据卷为 `vx-postgres`；不要在未确认备份的情况下执行 `down --volumes`。PostgreSQL 备份文件为 `.postgres.sql.gz`，恢复前先停止应用，再执行 `gunzip -c 文件.sql.gz | docker compose --profile postgres exec -T postgres psql -U "$VX_POSTGRES_USER" -d "$VX_POSTGRES_DB"`。

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

## 许可证

本项目基于 [MIT License](LICENSE) 开源。你可以在保留原始版权和许可声明的前提下使用、复制、修改、合并、发布和分发本项目。软件按“原样”提供，不附带任何明示或暗示担保。

Copyright (c) 2026 huizhang556
