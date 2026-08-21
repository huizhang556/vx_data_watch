本地优先的视频号流量分析工具。支持视频号后台 7 日 CSV 持久化导入、重叠数据修订、逐视频表格和截图 OCR 导入、单日及区间分析、AI 优化建议、移动端网页和加密备份。

## 快速启动

Windows 本地部署需要 `uv` 和 Node.js 24：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Docker Compose 部署：

```bash
docker compose up -d --build
```

启动后访问 `http://127.0.0.1:8000`。首次打开时创建本地管理员账号，然后在“系统设置”中新建视频号账号并导入数据。

## 文档

- [部署说明](docs/DEPLOYMENT.md)
- [使用说明](docs/USER_GUIDE.md)
- [最终实施方案](docs/07-final-plan.md)
- [官方接口核查记录](docs/04-official-api-research.md)

## 数据与安全

- SQLite 数据库、主密钥和备份默认位于 `data/`，该目录不会提交到 Git。
- 本地密码使用 Argon2id 哈希，AI API Key 使用 AES-256-GCM 加密。
- 截图 OCR 在本机执行；只有用户主动生成 AI 报告时，结构化分析数据才会发往配置的兼容接口。
- 请定期下载 `.vxbackup` 加密备份，并妥善保存 `data/.master-key`。

## 卸载项目

卸载前请先确认是否需要保留数据。数据库、AI 配置加密密钥和备份一旦删除，未导出的数据将无法恢复。建议先在网页“系统设置”中下载 `.vxbackup`，并将备份文件和 `data/.master-key` 保存到项目目录之外。

### Docker Compose 部署卸载

仅停止服务并保留数据：

```bash
cd /path/to/vx_data_watch
docker compose down --remove-orphans
```

彻底删除 Compose 服务、项目数据卷和本地项目镜像：

```bash
cd /path/to/vx_data_watch
docker compose down --volumes --remove-orphans --rmi local
```

如果 `.env` 中使用了远程镜像标签，`--rmi local` 不会删除远程镜像。确认不再需要本地项目目录后，再删除源码目录：

```bash
cd ..
rm -rf vx_data_watch
```

如果还要删除已拉取到本机的远程标签镜像，请先查看并按实际标签删除：

```bash
docker image ls litehub/vx-data-watch
docker image rm litehub/vx-data-watch:0.3.7
```

不要使用 `docker system prune -a` 代替上述命令，它可能删除其他项目正在使用的镜像和缓存。Docker Hub 上的远程镜像不会因本地卸载而删除，需要在 Docker Hub 中单独管理。

### 源码部署卸载

如果服务是在当前终端前台启动的，回到该终端按 `Ctrl+C` 停止。确认没有残留进程：

```bash
ps aux | grep '[u]vicorn.*app.main'
```

如果你自行创建了 systemd 服务，先停止并禁用它（服务名以你实际创建的为准）：

```bash
sudo systemctl stop vx-data-watch
sudo systemctl disable vx-data-watch
sudo rm -f /etc/systemd/system/vx-data-watch.service
sudo systemctl daemon-reload
```

仅删除源码环境并保留 `data/` 数据：

```bash
cd /path/to/vx_data_watch
rm -rf .venv frontend/node_modules frontend/dist .pytest_cache .ruff_cache
```

彻底删除源码、数据库、主密钥、备份和导入数据：

```bash
cd ..
rm -rf vx_data_watch
```

源码卸载不会自动删除系统级的 Python、Node.js、uv、Nginx 或其他共享软件。若 Nginx 配置专门用于本项目，请先删除对应站点配置并检查：

```bash
sudo nginx -t
sudo systemctl reload nginx
```
# 账号注册、邮箱验证与人机验证

默认关闭公开注册：`VX_REGISTRATION_ENABLED=false`。需要开放注册时，在部署目录的 `.env` 中设置为 `true`，并配置 SMTP；修改后执行 `docker compose up -d` 使配置生效。

邮箱配置项：`VX_SMTP_HOST`、`VX_SMTP_PORT`、`VX_SMTP_USERNAME`、`VX_SMTP_PASSWORD`、`VX_SMTP_FROM`、`VX_SMTP_STARTTLS`、`VX_SMTP_SSL`。465 端口通常设置 `VX_SMTP_SSL=true`，587 端口通常使用 `VX_SMTP_STARTTLS=true`。系统只在数据库中保存验证码哈希，验证码默认 10 分钟有效，可用 `VX_VERIFICATION_CODE_MINUTES` 调整。

可选的人机验证目前支持 Cloudflare Turnstile：配置 `VX_CAPTCHA_ENABLED=true`、`VX_CAPTCHA_PROVIDER=turnstile`、`VX_CAPTCHA_SITE_KEY` 和 `VX_CAPTCHA_SECRET_KEY`。站点域名必须在 Turnstile 控制台中登记。开启后登录、注册和重置密码都要求完成验证。

已有本地管理员账号不受影响。注册用户默认是只读角色；管理员仍可在系统设置中创建和管理本地用户。用户可在登录后通过账户设置修改用户名，密码重置只能使用已验证邮箱。
