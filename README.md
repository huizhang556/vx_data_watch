# VX Data Watch

VX Data Watch 是一个本地优先、适配桌面端和移动端浏览器的微信视频号数据分析应用。它可以持久化导入视频号后台导出的 7 日 CSV、逐视频表格或截图 OCR 结果，并按单日或日期区间展示指标趋势、视频贡献和 AI 优化建议。

项目不需要微信扫码登录，也不会获取微信账号凭据。导入数据默认只保存在部署者自己的 SQLite 数据库中；只有用户主动请求 AI 分析时，所选区间的结构化统计数据才会发送到用户配置的 OpenAI 兼容接口。

## 功能

- 导入视频号后台 CSV，按日期持久化、去重并保留修订记录。
- 导入逐视频 CSV/XLSX，或通过截图 OCR 识别后人工确认。
- 查询单日、近 3/7/15/30 日或自定义日期区间。
- 展示播放、点赞、评论、分享、关注、转发、收藏等趋势和同期对比。
- 提供折线图、饼图、柱状图和逐视频播放贡献统计。
- 配置 OpenAI 兼容接口，获取模型列表、测试连接并生成分析报告。
- 支持本地用户和角色、审计日志、加密 API Key 与加密备份。

## 技术栈

- 后端：Python 3.12、FastAPI、SQLAlchemy 2、Alembic、Pydantic。
- 数据库：SQLite。
- 安全：Argon2id 密码哈希、AES-256-GCM 敏感配置加密。
- OCR：RapidOCR、ONNX Runtime、OpenCV、Pillow。
- 前端：React 19、TypeScript、Vite、Ant Design、Apache ECharts。
- 测试：Pytest、Ruff、Vitest、ESLint、Playwright。
- 部署：Docker Compose，或 Windows/Linux 本地源码部署。

## Docker Compose 部署（推荐）

要求安装 Docker Engine 或 Docker Desktop，并支持 Compose v2。

```bash
git clone https://github.com/huizhang556/vx_data_watch.git
cd vx_data_watch
cp .env.example .env
docker compose -f docker-compose.yaml pull
docker compose -f docker-compose.yaml up -d --no-build
docker compose -f docker-compose.yaml ps
```

Windows PowerShell 复制配置文件时使用：

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.yaml pull
docker compose -f docker-compose.yaml up -d --no-build
```

浏览器访问 `http://127.0.0.1:8000`。首次打开时自行创建管理员账号，项目没有默认用户名或密码。

数据库、加密主密钥和备份默认保存在 Docker 命名卷 `vx-data` 中。停止应用不会删除数据：

```bash
docker compose -f docker-compose.yaml down
```

不要执行 `docker compose -f docker-compose.yaml down -v`，除非确定要永久删除全部应用数据。

查看日志：

```bash
docker compose -f docker-compose.yaml logs -f app
```

### 从源码构建镜像

默认配置使用公开镜像 `docker.io/litehub/vx-data-watch:0.3.0`，用户无需安装 Node.js、Python 或在服务器重复构建。需要验证源码或自行修改镜像时执行：

```bash
git pull --ff-only origin main
VX_IMAGE=vx-data:local docker compose -f docker-compose.yaml up -d --build
```

## 本地源码部署

要求安装 Git、[uv](https://docs.astral.sh/uv/) 和 Node.js 24。Python 3.12 由 `uv` 管理。

```bash
git clone https://github.com/huizhang556/vx_data_watch.git
cd vx_data_watch
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Linux：

```bash
cp .env.example .env
sh scripts/start-local.sh
```

脚本会安装后端和 OCR 依赖、安装前端依赖、构建网页并在 `0.0.0.0:8000` 启动服务。使用 `Ctrl+C` 停止。生产服务器优先使用 Docker Compose；如使用源码部署，应通过 systemd 管理进程并配置 HTTPS 反向代理。

### 开发检查

```bash
uv sync --extra dev --extra ocr
uv run ruff check backend
uv run pytest -q
cd frontend
npm ci
npm run lint
npm test
npm run build
npm run test:e2e
```

## 配置

复制 `.env.example` 为 `.env` 后按需修改：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `VX_DATA_DIR` | 源码部署的数据目录 | `./data` |
| `VX_DATABASE_URL` | SQLite 连接地址 | `sqlite:///./data/vx_data.db` |
| `VX_BIND_ADDRESS` | Docker 端口绑定地址 | `0.0.0.0` |
| `VX_PORT` | Web 服务端口 | `8000` |
| `VX_COOKIE_SECURE` | 仅通过 HTTPS 发送登录 Cookie | `false` |
| `VX_SESSION_DAYS` | 登录会话有效天数 | `14` |
| `VX_MAX_UPLOAD_MB` | 单个上传文件大小限制 | `20` |
| `VX_MASTER_KEY` | Base64 编码的 32 字节主密钥 | 自动生成本地密钥 |
| `VX_IMAGE` | Docker 镜像名称和标签 | `vx-data:local` |
| `VX_UPDATE_REPOSITORY` | 在线更新允许访问的固定镜像仓库 | `litehub/vx-data-watch` |

公网部署必须配置 HTTPS，并设置 `VX_COOKIE_SECURE=true`。未配置 `VX_MASTER_KEY` 时，应用会在数据目录生成 `.master-key`；丢失该文件后，AI Key 和加密备份无法解密。

## 使用流程

1. 首次访问时创建管理员账号。
2. 在“系统设置”中创建要分析的视频号账号。
3. 在“数据导入”中导入后台 7 日 CSV。
4. 按需导入逐视频表格，或上传同一天的截图进行 OCR。
5. OCR 结果必须人工检查，确认日期、标题和数值后再入库。
6. 在“数据概览”和“视频贡献”中选择单日或区间查看统计。
7. 如需 AI 建议，在“AI 建议”中填写自己的兼容接口，先测试再保存。

重叠 CSV 日期不会产生重复记录；平台修订旧日期时，系统保存旧版本并使用新值。当前导出 CSV 没有独立收藏字段，缺失指标显示为“暂无数据”，不会当作 0。

## 在线更新

Docker Compose 部署的管理员可以在“系统设置 > 在线更新”中：

1. 从 Docker Hub 检测当前版本、最新版本和可选历史版本。
2. 选择高于当前版本且不高于最新版本的正式版本。
3. 自动创建加密数据库备份。
4. 拉取目标镜像、替换主应用容器并等待健康检查。
5. 更新失败时自动恢复原容器；成功后页面自动重新连接。

为了降低风险，主 Web 容器不挂载 Docker Socket。只有不开放网络端口的 `updater` Companion 可以访问 Docker Engine，并且它只接受固定仓库 `litehub/vx-data-watch` 和严格的三段式版本号。在线更新会把选中的镜像写回部署目录的 `.env`，后续重启不会退回旧版本。

源码部署可以在线查询版本，但不会由网页执行 `git` 或任意主机命令。源码用户应在终端拉取代码、运行测试并重新启动服务。

## 备份与恢复

网页“系统设置”支持创建并下载 `.vxbackup` 加密备份。源码部署也可以执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -BackupPath .\data\backups\vx-data-时间.vxbackup
```

Docker 中创建备份：

```bash
docker compose -f docker-compose.yaml exec app python -m app.cli backup
```

恢复前必须停止应用，并使用创建备份时的同一主密钥。备份和主密钥应分开保存。

## Docker Hub 发布（维护者）

Docker Desktop 登录 `litehub` 后，构建并推送版本号和 `latest`：

```bash
docker build -t litehub/vx-data-watch:0.3.0 -t litehub/vx-data-watch:latest .
```

```bash
docker push litehub/vx-data-watch:0.3.0
docker push litehub/vx-data-watch:latest
```

不要把 Docker Hub 密码或 Personal Access Token 写入命令、README、Issue 或聊天。

Docker Hub 当前镜像约 297 MB；Docker Desktop 解压层、快照和构建缓存的本地占用可能明显更大。主要体积来自 OCR 所需的 ONNX Runtime、OpenCV、NumPy、模型依赖、Python 运行环境和系统动态库，业务源码本身很小。

## 参与开发

建议先 Fork 仓库；有写入权限的协作者也可以直接克隆。不要在 `main` 上直接开发：

```bash
git clone https://github.com/你的用户名/vx_data_watch.git
cd vx_data_watch
git remote add upstream https://github.com/huizhang556/vx_data_watch.git
git fetch upstream
git switch main
git pull --ff-only upstream main
git switch -c feat/简短功能名
```

完成修改并运行相关测试后提交自己的分支：

```bash
git status
git add <本次修改的文件>
git diff --cached
git commit -m "feat: 简要说明功能变化"
git push -u origin feat/简短功能名
```

随后向本仓库 `main` 创建 Pull Request。修复使用 `fix:`，文档使用 `docs:`，测试使用 `test:`。PR 应说明问题、实现范围、测试结果以及数据库或部署影响；数据库结构变化必须新增 Alembic migration，不要修改已经发布的迁移。

严禁提交真实用户 CSV、截图、数据库、`.env`、API Key、主密钥、备份、日志或个人信息。安全漏洞请使用 GitHub Private vulnerability reporting，不要创建包含凭据、用户数据或漏洞利用细节的公开 Issue。

## 版本功能

### 0.3.0 - 2026-08-18

- 增加 Docker Hub 正式版本检测、历史版本选择、升级前备份、在线更新和自动重启。
- 使用隔离的 Companion 更新服务，主 Web 容器不直接访问 Docker Socket。
- 更新失败时恢复原容器，成功后持久化镜像版本并自动刷新页面。
- Compose 文件统一为 `docker-compose.yaml`，公开文档精简到单一 README。
- 官方镜像发布到 `litehub/vx-data-watch`，Linux 不再提供单文件二进制。

### 0.2.1 - 2026-08-18

- AI 查询记录支持重新生成并查看分析、编辑日期范围和确认删除。
- 查询记录操作写入审计日志，查看历史不会创建重复记录。
- 侧边栏展开/收缩按钮调整到右侧边缘垂直中点。
- 增加持续集成、公开部署说明和隐私文件排除规则。

### 0.2.0 - 2026-08-17

- 概览支持单日、近 3/7/15/30 日和自定义区间。
- 趋势覆盖播放、点赞、评论、分享、关注、转发和收藏，并显示同期涨跌。
- 增加趋势、互动构成和视频贡献图表。
- AI 建议支持区间分析、Markdown 富文本、图表和查询记录。
- AI 配置支持获取模型、独立测试和保存。
- 修复 OCR 错位和误识别、退出页面不跳转、AI 报告不显示及按钮联动问题。
- 支持 Docker Compose、本地源码部署、加密配置、审计和备份。

### 0.1.0 - 2026-08-17

- 完成账号管理、7 日 CSV、逐视频表格、截图 OCR、数据概览和 AI 接口配置的首个可运行版本。

## Linux 发布说明

项目不发布单文件 Linux 二进制。OCR 依赖 ONNX Runtime、OpenCV、系统动态库和模型资源，封装产物体积接近容器且受 glibc 与 CPU 架构限制。Linux 用户应使用 Docker Hub 镜像；无 Docker 环境时使用源码部署脚本。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。你可以在保留原始版权和许可声明的前提下使用、复制、修改、合并、发布和分发本项目。软件按“原样”提供，不附带任何明示或暗示担保。

Copyright (c) 2026 huizhang556
