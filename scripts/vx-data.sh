#!/usr/bin/env bash
set -Eeuo pipefail

# VX Data Watch one-click operations. Supported: Ubuntu 24.04 and Debian 12.
PROJECT_DIR="/opt/vx-data-watch"
DATA_VOLUME="vx-data"
POSTGRES_VOLUME="vx-postgres"
DEFAULT_BACKUP_DIR="/home/vx_backed"
DEFAULT_IMAGE="docker.io/litehub/vx-data-watch:latest"
GITHUB_DOWNLOAD_BASE="https://raw.githubusercontent.com/huizhang556/vx_data_watch/main"
GITEE_DOWNLOAD_BASE="https://gitee.com/huizhang556/vx_data_watch/raw/main"
DOWNLOAD_BASE="${VX_DOWNLOAD_BASE_URL:-$GITHUB_DOWNLOAD_BASE}"
RETRY_COUNT="${VX_RETRY_COUNT:-5}"
ASSUME_YES="${VX_ASSUME_YES:-0}"
DOCKERHUB_IMAGE="docker.io/litehub/vx-data-watch:latest"
ACR_IMAGE="crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com/zhang_spaces/vx-data-watch:latest"
SELECTED_IMAGE="$DOCKERHUB_IMAGE"
DETECTED_COUNTRY=""

log() { printf '[vx-data] %s\n' "$*"; }
warn() { printf '[vx-data] 警告：%s\n' "$*" >&2; }
die() { printf '[vx-data] 错误：%s\n' "$*" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die '请使用 sudo 或 root 执行。'; }
confirm() { [ "$ASSUME_YES" = 1 ] && return 0; local answer; read -r -p "$1 [y/N] " answer || true; [[ "$answer" =~ ^[Yy]$ ]]; }

retry() {
  local attempt=1 delay=3
  until "$@"; do
    [ "$attempt" -ge "$RETRY_COUNT" ] && return 1
    warn "网络操作失败，第 ${attempt}/${RETRY_COUNT} 次重试，${delay} 秒后继续。"
    sleep "$delay"; attempt=$((attempt + 1)); delay=$((delay * 2)); [ "$delay" -gt 30 ] && delay=30
  done
}
download() { local url="$1" target="$2"; retry curl --fail --location --connect-timeout 15 --max-time 180 --retry 2 --output "${target}.tmp" "$url"; mv -f "${target}.tmp" "$target"; }
select_download_source() {
  [ -n "${VX_DOWNLOAD_BASE_URL:-}" ] && { DOWNLOAD_BASE="$VX_DOWNLOAD_BASE_URL"; return; }
  local preferred="$GITHUB_DOWNLOAD_BASE" fallback="$GITEE_DOWNLOAD_BASE"
  if [ "${DETECTED_COUNTRY:-}" = CN ]; then preferred="$GITEE_DOWNLOAD_BASE"; fallback="$GITHUB_DOWNLOAD_BASE"; fi
  if curl -fsSL --connect-timeout 8 --max-time 15 -o /dev/null "$preferred/.env.example"; then
    DOWNLOAD_BASE="$preferred"
    log "代码源检测成功：$([ "$preferred" = "$GITEE_DOWNLOAD_BASE" ] && printf 'Gitee' || printf 'GitHub')"
  elif curl -fsSL --connect-timeout 8 --max-time 15 -o /dev/null "$fallback/.env.example"; then
    DOWNLOAD_BASE="$fallback"
    warn "首选代码源不可访问，已切换到 $([ "$fallback" = "$GITEE_DOWNLOAD_BASE" ] && printf 'Gitee' || printf 'GitHub')。"
  else
    die 'GitHub 和 Gitee 代码源均不可访问，请检查网络、配置代理，或设置 VX_DOWNLOAD_BASE_URL 后重试。'
  fi
}

check_os() {
  [ -r /etc/os-release ] || die '无法识别操作系统。'; . /etc/os-release
  case "${ID}:${VERSION_ID}" in ubuntu:24.04|debian:12) ;; *) die "仅支持 Ubuntu 24.04 或 Debian 12，当前为 ${PRETTY_NAME:-$ID $VERSION_ID}。" ;; esac
}
ensure_dependencies() {
  local missing=() cmd; for cmd in curl openssl rsync; do command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd"); done
  if [ "${#missing[@]}" -gt 0 ]; then confirm "缺少 ${missing[*]}，是否使用 apt 自动安装？" || die '用户拒绝安装依赖，操作已终止。'; retry apt-get update; retry apt-get install -y ca-certificates curl openssl rsync; fi
}
install_docker() {
  ensure_dependencies
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then return; fi
  warn '未检测到 Docker 或 Docker Compose。'; confirm '是否自动安装 Docker Engine 和 Compose 插件？' || die '用户拒绝安装 Docker，操作已终止。'
  retry sh -c 'curl -fsSL https://get.docker.com | sh'; systemctl enable --now docker
  docker compose version >/dev/null 2>&1 || die 'Docker Compose 插件安装失败。'
}
select_mirror() {
  [ "${VX_SKIP_MIRROR_PROMPT:-0}" = 1 ] && return
  [ "$DETECTED_COUNTRY" = CN ] || [ "${VX_FORCE_MIRROR_PROMPT:-0}" = 1 ] || return
  log '中国大陆服务器可选择 Docker Hub 镜像加速。公共地址可能失效，失败时请改用云服务器或配置代理。'
  log '1) 不配置  2) https://docker.m.daocloud.io  3) https://dockerproxy.net  4) 自定义'
  local choice mirror; read -r -p '请选择 [1-4，默认 1]：' choice || true
  case "${choice:-1}" in 1) return ;; 2) mirror='https://docker.m.daocloud.io' ;; 3) mirror='https://dockerproxy.net' ;; 4) read -r -p '请输入镜像加速地址：' mirror ;; *) warn '无效选择，跳过镜像加速。'; return ;; esac
  [ -n "$mirror" ] || die '镜像加速地址不能为空。'; mkdir -p /etc/docker
  if [ -f /etc/docker/daemon.json ]; then warn 'daemon.json 已存在，未自动覆盖。请手动加入 registry-mirrors 后重试。'; return; fi
  printf '{\n  "registry-mirrors": ["%s"]\n}\n' "$mirror" > /etc/docker/daemon.json; systemctl restart docker
}
detect_country() {
  local country
  country="$(curl -fsS --connect-timeout 5 --max-time 8 https://ipapi.co/country/ 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ "$country" =~ ^[A-Za-z]{2}$ ]]; then printf '%s' "${country^^}"; return 0; fi
  country="$(curl -fsS --connect-timeout 5 --max-time 8 https://ipinfo.io/country 2>/dev/null | tr -d '[:space:]' || true)"
  [[ "$country" =~ ^[A-Za-z]{2}$ ]] && printf '%s' "${country^^}"
}
detect_ip() {
  curl -fsS --connect-timeout 5 --max-time 8 https://api.ipify.org 2>/dev/null | tr -d '[:space:]' || true
}
select_registry() {
  local country choice public_ip recommendation
  public_ip="$(detect_ip)"
  country="$(detect_country || true)"
  DETECTED_COUNTRY="$country"
  local default_choice=1
  if [ "$country" = CN ]; then
    default_choice=2
    recommendation='阿里云 ACR（中国大陆服务器优先建议）'
    log "检测结果：公网 IP ${public_ip:-未知}，国家代码 CN（中国大陆）。"
    log "明确建议：$recommendation；也可以选择 Docker Hub。"
    log '1) Docker Hub（默认）  2) 阿里云 ACR（中国大陆备用）'
  elif [ -n "$country" ]; then
    recommendation='Docker Hub（海外服务器默认建议）'
    log "检测结果：公网 IP ${public_ip:-未知}，国家代码 $country。"
    log "明确建议：$recommendation；如有特殊网络需求也可以选择阿里云 ACR。"
    log '1) Docker Hub（默认）  2) 阿里云 ACR（仅在明确需要时选择）'
  else
    warn "检测结果：公网 IP ${public_ip:-未知}，无法确定所在国家。"
    log '明确建议：默认选择 Docker Hub；如果服务器位于中国大陆或 Docker Hub 不稳定，再选择阿里云 ACR。'
    log '1) Docker Hub（默认）  2) 阿里云 ACR'
  fi
  read -r -p "请选择应用镜像源 [1-2，默认 ${default_choice}]：" choice || true
  choice="${choice:-$default_choice}"
  [ "$choice" = 2 ] && SELECTED_IMAGE="$ACR_IMAGE" || SELECTED_IMAGE="$DOCKERHUB_IMAGE"
}
select_database() {
  local choice
  log '请选择数据库：1) SQLite（默认，适合单机部署）  2) PostgreSQL（内置容器，适合多人/长期运行）'
  read -r -p '请选择 [1-2，默认 1]：' choice || true
  if [ "${choice:-1}" = 2 ]; then
    DB_MODE=postgres
    POSTGRES_USER="vx_user"
    POSTGRES_DB="vx_data"
    POSTGRES_PASSWORD="$(openssl rand -hex 16)"
    log '已选择 PostgreSQL，将自动创建独立数据库容器和数据卷。'
  else
    DB_MODE=sqlite
    log '已选择 SQLite。'
  fi
}
generate_env() {
  mkdir -p "$PROJECT_DIR"; [ -f "$PROJECT_DIR/.env" ] && { log '检测到已有 .env，保留现有配置。'; return; }
  download "$DOWNLOAD_BASE/.env.example" "$PROJECT_DIR/.env.example"; cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  local key; key="$(openssl rand -base64 32 | tr -d '\n' | tr '/+' '_-')"
  sed -i "s|^# VX_MASTER_KEY=.*|VX_MASTER_KEY=$key|" "$PROJECT_DIR/.env"; sed -i 's|^VX_HOST_PORT=.*|VX_HOST_PORT=10000|' "$PROJECT_DIR/.env"; sed -i 's|^VX_PORT=.*|VX_PORT=8000|' "$PROJECT_DIR/.env"; sed -i "s|^VX_IMAGE=.*|VX_IMAGE=$SELECTED_IMAGE|" "$PROJECT_DIR/.env"; if [ "$SELECTED_IMAGE" = "$ACR_IMAGE" ]; then sed -i 's|^VX_UPDATE_REGISTRY=.*|VX_UPDATE_REGISTRY=crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com|' "$PROJECT_DIR/.env"; else sed -i 's|^VX_UPDATE_REGISTRY=.*|VX_UPDATE_REGISTRY=docker.io|' "$PROJECT_DIR/.env"; fi
  # Keep the updater repository explicit so the app and companion use the same source.
  if [ "$SELECTED_IMAGE" = "$ACR_IMAGE" ]; then
    printf '\nVX_UPDATE_REPOSITORY=zhang_spaces/vx-data-watch\n' >> "$PROJECT_DIR/.env"
  else
    printf '\nVX_UPDATE_REPOSITORY=litehub/vx-data-watch\n' >> "$PROJECT_DIR/.env"
  fi
  if [ "${DB_MODE:-sqlite}" = postgres ]; then
    sed -i 's|^# VX_DATABASE_MODE=.*|VX_DATABASE_MODE=postgres|' "$PROJECT_DIR/.env"
    sed -i "s|^# VX_POSTGRES_USER=.*|VX_POSTGRES_USER=$POSTGRES_USER|; s|^# VX_POSTGRES_PASSWORD=.*|VX_POSTGRES_PASSWORD=$POSTGRES_PASSWORD|; s|^# VX_POSTGRES_DB=.*|VX_POSTGRES_DB=$POSTGRES_DB|; s|^# VX_DATABASE_URL=.*|VX_DATABASE_URL=postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB|" "$PROJECT_DIR/.env"
  else
    printf '\nVX_DATABASE_MODE=sqlite\n' >> "$PROJECT_DIR/.env"
  fi
  chmod 600 "$PROJECT_DIR/.env"; log '.env 已生成，宿主机默认端口为 10000，容器内部端口固定为 8000。'
}
load_env() { [ -f "$PROJECT_DIR/.env" ] || die "缺少 $PROJECT_DIR/.env。"; set -a; . "$PROJECT_DIR/.env"; set +a; IMAGE="${VX_IMAGE:-$DEFAULT_IMAGE}"; }
fetch_compose() { [ -n "${DETECTED_COUNTRY:-}" ] || DETECTED_COUNTRY="$(detect_country || true)"; select_download_source; download "$DOWNLOAD_BASE/docker-compose.yaml" "$PROJECT_DIR/docker-compose.yaml"; }
compose() { if [ "${VX_DATABASE_MODE:-sqlite}" = postgres ]; then (cd "$PROJECT_DIR" && docker compose --profile postgres -f docker-compose.yaml "$@"); else (cd "$PROJECT_DIR" && docker compose -f docker-compose.yaml "$@"); fi; }
stop_cmd() {
  need_root
  [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"
  load_env
  log "正在停止 VX Data Watch（包含 PostgreSQL Profile）..."
  compose down --remove-orphans
  log "项目已停止，数据卷和镜像均已保留。"
}
wait_healthy() { local i status; for i in $(seq 1 30); do status="$(compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null || true)"; echo "$status" | grep -q '^app healthy' && return 0; sleep 2; done; compose ps; return 1; }
archive_volume() {
  local target="$1" archive="$2" include_media="${3:-yes}"; mkdir -p "$target"; local available required
  available="$(df -Pk "$target" | awk 'NR==2 {print $4}')"; required="$(docker run --rm -v "$DATA_VOLUME:/data:ro" alpine:3.20 sh -c 'du -sk /data 2>/dev/null | cut -f1' 2>/dev/null || echo 0)"
  [ "$available" -gt $((required + 10240)) ] || die "备份目录空间不足，至少需要约 $((required / 1024 + 10)) MB。"
  retry docker pull alpine:3.20 >/dev/null
  local excludes=""
  [ "$include_media" = yes ] || excludes="--exclude=downloads --exclude='*.mp4' --exclude='*.webm' --exclude='*.mp3' --exclude='*.wav'"
  docker run --rm -v "$DATA_VOLUME:/data:ro" -v "$target:/backup" alpine:3.20 sh -c "tar czf /backup/$(basename "$archive") $excludes -C /data ."; chmod 600 "$archive"
}
postgres_dump() { local target="$1"; compose exec -T postgres pg_dump -U "${VX_POSTGRES_USER:-vx_user}" -d "${VX_POSTGRES_DB:-vx_data}" | gzip > "$target"; chmod 600 "$target"; }
backup_cmd() { need_root; [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"; load_env; local target="${1:-$DEFAULT_BACKUP_DIR}" archive="$target/vx-data-watch-$(date +%Y%m%d-%H%M%S).tar.gz"; [ -w "$(dirname "$target")" ] || die "备份目录父目录不可写：$target"; log "正在备份 Docker 数据卷到 $archive。"; archive_volume "$target" "$archive"; if [[ "${VX_DATABASE_URL:-}" == postgres* ]]; then log '正在导出 PostgreSQL 数据库。'; postgres_dump "${archive%.tar.gz}.postgres.sql.gz" || die 'PostgreSQL 导出失败。'; fi; log '本机备份完成。'; }
migrate_cmd() {
  need_root; ensure_dependencies; [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"; load_env; local user host port path include_media temp
  read -r -p '目标服务器用户名：' user; read -r -p '目标服务器 IP 或域名：' host; read -r -p 'SSH 端口（默认 22）：' port; port="${port:-22}"; read -r -p '目标数据存放路径：' path; [ -n "$user" ] && [ -n "$host" ] && [ -n "$path" ] || die '迁移参数不完整。'
  temp="$(mktemp -d)"; trap 'rm -rf "$temp"' RETURN; read -r -p '是否额外迁移下载目录中的视频/音频等大文件？[y/N]：' include_media || true; local archive_mode=no; [[ "$include_media" =~ ^[Yy]$ ]] && archive_mode=yes; archive_volume "$temp" "$temp/vx-data-watch-migration.tar.gz" "$archive_mode"; if [[ "${VX_DATABASE_URL:-}" == postgres* ]]; then log '正在导出 PostgreSQL 数据库用于异地迁移。'; postgres_dump "$temp/vx-data-watch-migration.postgres.sql.gz" || die 'PostgreSQL 导出失败。'; fi
  run_ssh() { ssh -o ConnectTimeout=15 -p "$port" "$user@$host" "$@"; }; retry run_ssh "mkdir -p '$path'"; local excludes=(); [[ "$include_media" =~ ^[Yy]$ ]] || excludes+=(--exclude='downloads/' --exclude='*.mp4' --exclude='*.webm' --exclude='*.mp3' --exclude='*.wav')
  retry rsync -aH --partial --append-verify --info=progress2 "${excludes[@]}" -e "ssh -p $port -o ConnectTimeout=15" "$temp/" "$user@$host:$path/"; log '异地迁移完成。目标端已获得数据卷归档；使用 PostgreSQL 时还包含数据库转储文件，请按文档恢复。'
}
install_cmd() { need_root; log "正式安装目录：$PROJECT_DIR（当前目录仅用于下载脚本，不会作为项目目录）"; check_os; install_docker; mkdir -p "$PROJECT_DIR"; [ -f "$PROJECT_DIR/.env" ] || { select_registry; select_database; }; select_mirror; fetch_compose; download "$DOWNLOAD_BASE/scripts/vx-data.sh" "$PROJECT_DIR/vx-data.sh"; chmod 700 "$PROJECT_DIR/vx-data.sh"; generate_env; load_env; retry docker pull "$IMAGE" || die '镜像拉取失败，请检查网络、代理或镜像加速配置。'; if [ "${VX_DATABASE_MODE:-sqlite}" = postgres ]; then compose up -d postgres; for i in $(seq 1 30); do compose exec -T postgres pg_isready -U "${VX_POSTGRES_USER:-vx_user}" -d "${VX_POSTGRES_DB:-vx_data}" >/dev/null 2>&1 && break; sleep 2; done; fi; compose up -d --no-build; wait_healthy || die '服务启动后健康检查失败，请执行 docker compose logs app 查看日志。'; log "安装完成：请访问 http://服务器IP:${VX_HOST_PORT:-10000}（宿主机端口；容器内部端口为 8000）。"; }
update_cmd() {
  need_root; [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"; load_env; local version="${1:-latest}" old_image="$IMAGE" image_repo="${IMAGE%:*}" new_image="${image_repo}:${version#v}"; backup_cmd; sed -i "s|^VX_IMAGE=.*|VX_IMAGE=$new_image|" "$PROJECT_DIR/.env"
  if ! retry docker pull "$new_image"; then sed -i "s|^VX_IMAGE=.*|VX_IMAGE=$old_image|" "$PROJECT_DIR/.env"; die '新镜像拉取失败，已恢复原镜像配置。'; fi
  if ! compose up -d --no-build --force-recreate || ! wait_healthy; then warn '新版本启动失败，正在恢复原镜像。'; sed -i "s|^VX_IMAGE=.*|VX_IMAGE=$old_image|" "$PROJECT_DIR/.env"; docker pull "$old_image" || true; compose up -d --no-build --force-recreate || true; die '更新失败，已尝试恢复原版本。'; fi
  log "更新完成：$version，数据卷 $DATA_VOLUME 未删除。"
}
uninstall_cmd() {
  need_root; [ -d "$PROJECT_DIR" ] || die "项目目录不存在：$PROJECT_DIR"; load_env; log '1) 删除容器并保留数据  2) 删除容器、数据卷和项目目录  3) 取消'; local choice; read -r -p '请选择 [1-3]：' choice
  case "$choice" in
    1) compose down --remove-orphans; log "容器已删除，数据卷 $DATA_VOLUME 保留。" ;;
    2) confirm '确认永久删除数据卷、密钥、备份和用户数据？此操作不可恢复。' || return; local image_choice; log '镜像处理：1) 保留当前镜像  2) 删除当前项目镜像  3) 删除所有 vx-data-watch 镜像'; read -r -p '请选择 [1-3，默认 1]：' image_choice || true; compose down --volumes --remove-orphans; case "${image_choice:-1}" in 2) docker image rm -f "$IMAGE" >/dev/null 2>&1 || true ;; 3) docker images --format '{{.Repository}}:{{.Tag}}' | awk '/vx-data-watch/ {print}' | xargs -r docker image rm -f >/dev/null 2>&1 || true ;; esac; rm -rf -- "$PROJECT_DIR"; log '项目和所选数据已删除。' ;;
    *) log '已取消卸载。' ;;
  esac
}
install_cmd_v2() {
  need_root
  log "开始安装 VX Data Watch，项目目录：$PROJECT_DIR"
  check_os
  log "正在检查 Docker 和系统依赖..."
  install_docker
  mkdir -p "$PROJECT_DIR"
  if [ -f "$PROJECT_DIR/.env" ]; then
    log "检测到已有 $PROJECT_DIR/.env，将沿用现有配置。"
  else
    log "首次安装配置：即将选择镜像源和数据库。"
    select_registry
    select_database
  fi
  select_mirror
  fetch_compose
  download "$DOWNLOAD_BASE/scripts/vx-data.sh" "$PROJECT_DIR/vx-data.sh"
  chmod 700 "$PROJECT_DIR/vx-data.sh"
  generate_env
  load_env
  log "最终镜像配置：$IMAGE"
  log "在线更新仓库：${VX_UPDATE_REGISTRY:-docker.io}/${VX_UPDATE_REPOSITORY:-litehub/vx-data-watch}"
  log "正在拉取应用镜像：$IMAGE"
  retry docker pull "$IMAGE" || die '镜像拉取失败，请检查网络、代理或镜像加速配置。'
  if [ "${VX_DATABASE_MODE:-sqlite}" = postgres ]; then
    compose up -d postgres
    for i in $(seq 1 30); do
      compose exec -T postgres pg_isready -U "${VX_POSTGRES_USER:-vx_user}" -d "${VX_POSTGRES_DB:-vx_data}" >/dev/null 2>&1 && break
      sleep 2
    done
  fi
  log "正在启动应用容器..."
  compose up -d --no-build
  wait_healthy || die '服务启动后健康检查失败，请执行 docker compose logs app 查看日志。'
  log "安装完成：请访问 http://服务器IP:${VX_HOST_PORT:-10000}（容器内部端口为 8000）。"
}

usage() { cat <<'EOF'
用法：sudo ./scripts/vx-data.sh <install|stop|update|backup|migrate|uninstall> [参数]

install             安装依赖、下载 Compose、生成随机 .env 并启动
stop                停止 app、updater 和数据库容器，保留数据卷和镜像
update [版本]       先备份，再拉取 latest 或指定版本并健康检查，失败自动回滚
backup [目录]       备份 vx-data 数据卷，默认 /home/vx_backed
migrate             导出数据卷后用 rsync 断点续传到另一台服务器
uninstall           选择保留数据或完全删除，并单独选择是否删除镜像

安装时会先显示公网 IP、国家代码和镜像建议，再由用户确认。仅中国大陆默认询问 Docker 镜像加速；海外如确有需要可设置 VX_FORCE_MIRROR_PROMPT=1。
环境变量：VX_DOWNLOAD_BASE_URL、VX_RETRY_COUNT、VX_SKIP_MIRROR_PROMPT=1、VX_FORCE_MIRROR_PROMPT=1、VX_ASSUME_YES=1
EOF
}
main() { local command="${1:-}"; shift || true; case "$command" in install) install_cmd_v2 "$@" ;; stop) stop_cmd "$@" ;; update) update_cmd "$@" ;; backup) backup_cmd "$@" ;; migrate) migrate_cmd "$@" ;; uninstall) uninstall_cmd "$@" ;; -h|--help|help) usage ;; *) usage; exit 2 ;; esac; }
main "$@"
