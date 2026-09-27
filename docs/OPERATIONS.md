# PTE Speaking Lab 运维手册：本机服务与 Docker

更新时间：2026-09-28。给日常使用者和维护人员看的命令清单。首次在 M5 安装 Docker、传送项目和迁移数据的完整步骤见 [M5 Docker 部署手册](M5_DOCKER_DEPLOYMENT.md)；本次部署的实测与边界见 [部署记录](DEPLOYMENT_RECORD_2026-09-28.md)。下面的密码、密钥和录音路径都不应发到聊天或提交 Git。

## 先分清两个运行实例

| 项目 | 本机原生服务（M2） | Docker 服务（M5） |
|---|---|---|
| 已验证入口 | `http://192.168.5.14:8765/` | `http://192.168.5.19:8765/` |
| 项目目录 | `/Users/alex/codex_project/PTE口语诊断分析` | `/Users/zihanzong/pte-speaking-lab` |
| 运行配置 | 项目根目录 `.env` | M5 项目根目录 `.env.docker` |
| 业务数据 | 项目根目录 `data/` | M5 的 `/Users/zihanzong/pte-speaking-lab-data/`，挂载为容器的 `/app/data` |
| 网页/后端 | 构建后的 React，由本机 FastAPI 提供；macOS `launchd` 托管 | 构建后的 React 与 FastAPI 在一个 Linux ARM64 容器中 |
| 模型 | 本机依赖与 `data/models/` 缓存 | 镜像内 `/opt/pte-models/`，容器走 CPU |

两边当前同时运行且**数据相互独立**。M5 的历史数据来自一次迁移快照；迁移之后新增的录音、报告、密码和配置不会自动在两边同步。两边都连接同一可信内网，但没有跨设备同步服务。若在同一台 Mac 上同时运行原生服务和 Docker，必须使用**不同宿主机端口、不同数据目录、各自的配置文件**；可共用项目源码，不可让两个服务并发写同一个 SQLite 数据库或业务目录。

镜像含已构建前端、FastAPI 后端、锁定的 Python 依赖、FFmpeg、Tesseract 英文 OCR、eSpeak NG，以及预装 WhisperX/OpenPronounce 模型。Node 只在镜像构建阶段使用。镜像**不含** `.env`、`.env.docker`、个人录音、截图、SQLite 或报告数据。当前 M5 是先通过 SSH 传送经过排除规则的代码，**在 M5 上构建镜像**，不是从 M2 传送一个已经构建好的镜像。镜像里的 Edge TTS 客户端仍需联网；本机 CLIProxyAPI 没有装进镜像，M5 的 Compose 明确关闭云端 AI。

## 1. M2 原生内网服务

在 M2 终端先进入目录：

```bash
cd /Users/alex/codex_project/PTE口语诊断分析
```

### 查看状态、启动、停止

```bash
./scripts/start.sh                         # 已运行时会提示，不重复启动
./scripts/stop.sh                          # 停止后台服务
./scripts/restart.sh                       # 修改 .env 后重启
tail -n 100 data/logs/lan.log              # 最近日志
tail -f data/logs/lan.log                  # 实时日志；Control+C 仅退出查看
lsof -nP -iTCP:8765 -sTCP:LISTEN           # 看端口监听
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.5.14:8765/api/v1/health
```

未带密码访问健康检查返回 `401` 代表认证在工作，不代表服务失败。需验证账号时运行 `curl -u pte http://192.168.5.14:8765/api/v1/health`，让 curl 交互询问密码；不要将 `用户名:密码` 写进命令行。若修改了前端代码，先运行 `npm run build --prefix frontend`，再重启。开发模式另用 `./scripts/dev.sh`，在 `127.0.0.1:5173` 与 `127.0.0.1:8000` 运行，按 Control+C 结束；它不代替内网后台服务。

### 配置与数据

```bash
nano .env                 # 修改本机配置；保存后 ./scripts/restart.sh
cp .env.example .env      # 仅首次新安装使用；不要覆盖现有 .env
```

`.env` 中 `PTE_LAN_USERNAME`、`PTE_LAN_PASSWORD` 控制浏览器登录；密码至少 16 字符。`PTE_LAN_BIND_IP`、`PTE_LAN_PORT` 控制本机服务地址。`OPENAI_API_KEY`、`OPENAI_ANALYSIS_MODEL`、`LLM_PROVIDER` 和兼容服务用的 `OPENAI_BASE_URL` 只由本机后端读取。CLIProxyAPI 当前连接的是本机 `127.0.0.1:8317`；这是 M2 自己的回环地址。全部选项见 [配置说明](CONFIGURATION.md)。

`data/db/pte.sqlite3` 是 SQLite 数据库；`data/audio/original/`、`data/audio/derived/` 和 `data/screenshots/original/` 分别保存原始音频、处理音频和截图。`data/models/` 是本机模型缓存，`data/logs/` 和 `data/run/` 是日志与运行状态。不要直接编辑数据库，也不要把 `data/`、`.env` 或真实测试数据上传 Git。

## 2. M5 Docker 服务

在 M5 本机终端执行，或先从已配置 SSH 的电脑登录 M5。**Docker Desktop 必须先启动。**

```bash
cd /Users/zihanzong/pte-speaking-lab
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker up -d --no-build
docker compose --env-file .env.docker stop
docker compose --env-file .env.docker restart
```

四条 Compose 命令依次是查看状态、启动、停止、在**配置与镜像都未改动时**重启。配置文件的 `PTE_DOCKER_BIND_IP=192.168.5.19`、`PTE_DOCKER_HOST_PORT=8765` 对应当前网页地址；未填写宿主机端口时默认 8765。容器内部始终使用 8765。M5 现有 `.env.docker` 即使没有新增的端口字段，也会继续使用默认 8765。

### 日志、健康、资源

```bash
docker compose --env-file .env.docker logs --tail=100
docker compose --env-file .env.docker logs -f            # Control+C 不停止容器
docker stats --no-stream
docker compose --env-file .env.docker config --quiet     # 仅校验，不打印密码
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.5.19:8765/api/v1/health
```

未认证的健康检查应为 `401`；交互式验证可用 `curl -u pte http://192.168.5.19:8765/api/v1/health`，成功为 `200`。看到容器 `healthy` 仍应以网页、API 与实际录音分析确认功能。日志可能含请求或错误上下文，分享前检查是否有私人数据。

### 查看或修改密码、地址和功能开关

```bash
nano .env.docker
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --no-build --force-recreate
```

在 `.env.docker` 中修改 `PTE_LAN_USERNAME`、至少 16 字符的 `PTE_LAN_PASSWORD`，或修改 Docker 宿主机 IP、端口、数据目录及 TTS 等开关。**改环境变量后必须重新创建容器；`docker compose restart` 不会加载新的环境变量。** 浏览器若缓存了旧 Basic Auth 凭据，可用无痕窗口重新登录。`.env.docker` 权限应为 `600`，不得复制到仓库。

当前 [`compose.yaml`](../compose.yaml) 明确覆盖 `LLM_PROVIDER=none`、`OPENAI_API_KEY=""` 和 `OPENAI_BASE_URL=""`。因此只在 `.env.docker` 填 API key 不会启用 AI；如要改成云端分析，须同时审查 Compose 覆盖项、网络地址和密钥注入，再重新创建容器。容器内的 `127.0.0.1` 指向容器自身，**不指向 M2 上的 CLIProxyAPI**。

### 构建、升级和停止整个 Compose 项目

```bash
docker compose --env-file .env.docker build
docker compose --env-file .env.docker up -d --no-build
docker compose --env-file .env.docker down
docker compose --env-file .env.docker up -d --no-build
```

代码或依赖变化时先 `build` 再 `up`。`down` 会移除应用容器和 Compose 网络，但不会删除镜像外的业务数据目录；下一条 `up` 会重新创建容器。不要删除 `/Users/zihanzong/pte-speaking-lab-data/`，也不需要用 `down -v` 完成日常操作。Docker Desktop 关闭或 Mac 休眠时，其他设备无法访问；容器 `restart: unless-stopped` 只在 Docker 引擎运行且容器未被手动停止时发挥作用。

## 3. 备份和恢复边界

先停止正在写入数据的服务，再用项目快照脚本生成**新的**备份目录。脚本用 SQLite backup API 和 SHA-256 核对，不直接复制正在运行的 SQLite/WAL 文件。

M2 原生服务：

```bash
cd /Users/alex/codex_project/PTE口语诊断分析
./scripts/stop.sh
mkdir -p "$HOME/pte-backups"
BACKUP_DIR="$HOME/pte-backups/$(date +%Y%m%d-%H%M%S)"
python3 scripts/export_m5_data.py export "$BACKUP_DIR" --source data
python3 scripts/export_m5_data.py verify "$BACKUP_DIR"
./scripts/start.sh
```

M5 Docker 服务：

```bash
cd /Users/zihanzong/pte-speaking-lab
docker compose --env-file .env.docker stop
mkdir -p "$HOME/pte-backups"
BACKUP_DIR="$HOME/pte-backups/$(date +%Y%m%d-%H%M%S)"
python3 scripts/export_m5_data.py export "$BACKUP_DIR" --source "$HOME/pte-speaking-lab-data"
python3 scripts/export_m5_data.py verify "$BACKUP_DIR"
docker compose --env-file .env.docker up -d --no-build
```

快照目录与当前数据目录必须不同，且是此前不存在的新目录。快照包含数据库和业务资产，不含可重建模型缓存、日志和 PID。验证命令只对**未被继续写入的快照**使用；运行中的业务目录里的数据库会变动，不能拿旧快照清单去校验当前数据库。恢复前先保留当前目录的另一份备份，再停止服务并核对快照；不要在服务运行时覆盖数据库。

## 4. 在 M2 也运行 Docker：准备条件与并行方案

Dockerfile 的目标是原生 `linux/arm64`，M2 与 M5 都属于 ARM64，因此本机**可以另行构建并运行同一项目**。M5 实机已验收；M2 的 Docker 版本尚未构建或跑过真实录音，性能不能照搬 M5 数字。2026-09-28 检查时，M2 已有 Docker Desktop 应用和 CLI，但 Desktop 引擎未运行，`docker compose` 插件尚未被 CLI 识别；此刻不能直接执行 Compose。先在 M2 图形界面打开 Docker Desktop，完成首次授权与 CLI 集成，再检查 `docker info` 和 `docker compose version`。若仍缺 Compose，检查 Docker Desktop 安装/CLI 集成后再继续，不要把 M5 的运行状态误当成本机验证。

若保留 M2 原生服务在 `192.168.5.14:8765`，Docker 另用宿主机端口 **8766**，且使用独立空数据目录：

```bash
cd /Users/alex/codex_project/PTE口语诊断分析
cp .env.docker.example .env.docker              # 仅首次；不要覆盖已有配置
mkdir -p "$HOME/pte-speaking-lab-docker-data"
chmod 700 "$HOME/pte-speaking-lab-docker-data"
chmod 600 .env.docker
nano .env.docker
```

在新 `.env.docker` 中填 `PTE_DOCKER_BIND_IP=192.168.5.14`、`PTE_DOCKER_HOST_PORT=8766`、`PTE_DOCKER_DATA_DIR=/Users/alex/pte-speaking-lab-docker-data`，并设置独立的 `PTE_LAN_USERNAME` 和不少于 16 字符的 `PTE_LAN_PASSWORD`。不要直接挂载原生服务的 `data/`。然后在 Docker Desktop 正常运行后执行：

```bash
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker build
docker compose --env-file .env.docker up -d --no-build
docker compose --env-file .env.docker ps
```

新地址为 `http://192.168.5.14:8766/`。这是一个**全新、空白的独立实例**；若要复制已有练习，需要先做一致快照，再在 Docker 未启动时迁入独立数据目录。不要把现有 `data/` 作为两套服务的共享卷。M2 的 24 GB 统一内存还需给 macOS 和浏览器留余量；Linux 容器走 CPU，无法使用 Mac Metal GPU。不要为了这个实例停掉已在 M5 验收的服务。

## 5. 常见情况

- `docker compose` 不存在、无法连接 Docker daemon：先启动 Docker Desktop，检查 CLI 集成；在 M5 的非交互 SSH 中可能需将 Docker Desktop 的 `Resources/bin` 加入 PATH。
- `port is already allocated`：该 Mac 的宿主机端口已被占用；若与原生服务并行，将 Docker 的 `PTE_DOCKER_HOST_PORT` 改为 8766 并重新创建容器。
- 地址无法访问：查看 `ps`、日志和宿主机当前内网 IP。IP 长期稳定需在路由器配置 DHCP 保留；不做公网端口转发。
- 改了密码仍无效：用 `up -d --no-build --force-recreate`，再用无痕窗口登录。
- 看见 `401`：无凭据访问时属预期；带正确凭据仍为 401 才检查配置和浏览器缓存。
- 报告为 `partial`：可能是词级时间戳质量不足；先看报告中的缺失原因，不等同于容器启动失败。
- 数据不见了：先确认打开的是 M2 原生、M5 Docker，还是 M2 Docker 新实例；三者的数据目录不同。

HTTP Basic 经过普通 HTTP 时不加密，仅供可信家庭内网使用。Edge TTS 会把核对后的朗读稿发送给在线服务；当前 Docker 未启用云端 LLM。
