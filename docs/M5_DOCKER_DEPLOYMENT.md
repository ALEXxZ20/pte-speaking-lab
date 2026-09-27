# M5 Pro 单镜像部署与远程操作

本手册针对 MacBook M5 Pro / 48 GB。镜像内含网页、FastAPI、Linux ARM64 Python 依赖、FFmpeg、英文 Tesseract、eSpeak NG 和预装的 WhisperX/OpenPronounce 模型。`data/` 与密码位于镜像外。音频模型在 Docker 的 Linux VM 内走 CPU；Edge TTS 仍需要联网。2026-09-28 已在目标 M5 完成原生 ARM64 构建与真实录音验收，实测见文末部署记录。

模型及第三方许可来源见 [M5 模型清单](M5_MODEL_NOTICES.md)。

## 1. M5 上准备 macOS 账号与固定地址

若 M5 尚未完成首次开机设置，请先在机器屏幕上走完 macOS 设置助理并创建第一个登录账号；这一步不能从尚未开通的 SSH 远程完成。此后使用这个已有账号即可，不要求再创建第二个系统用户。首次在 M5 本机登录，打开“系统设置 → 通用 → 共享 → 远程登录”，仅允许该账号访问。命令行方式（会要求管理员密码）：

```bash
sudo systemsetup -setremotelogin on
whoami
ipconfig getifaddr en0
```

若 `en0` 无地址，用 `networksetup -listallhardwareports` 查当前 Wi-Fi/以太网设备名，再运行 `ipconfig getifaddr 设备名`。在路由器为 M5 的 MAC 地址保留 DHCP IP；**固定 IP 由路由器保证**，Compose 不能替路由器设置。记下 `<M5_USER>`、`<M5_IP>`。从旧 Mac 测试：

```bash
ssh <M5_USER>@<M5_IP> 'uname -m; whoami'
```

期望 `arm64` 和预期用户名。首次连接需核对主机指纹；密码只在 SSH 提示中输入，不发聊天。

## 2. M5 上安装 Docker Desktop

在 M5 本机终端执行；遵循项目偏好使用 Homebrew：

```bash
brew install --cask docker
open -a Docker
docker version
docker compose version
docker info --format '{{.Architecture}}'
```

首次打开 Docker Desktop 需在图形界面完成许可和授权。`docker info` 应显示 `aarch64`/`arm64`。若以后部署更大的模型，可在 Docker Desktop 设置中将 VM 内存提高至约 **28 GB**；Compose 为应用设了 **24 GB** 上限，但实际可用内存仍受 Docker VM 配置约束。当前 M5 Docker VM 约 8 GB，现有真录音分析已成功，采样峰值约 2.3 GiB；这不代表更大模型仍有足够余量。

## 3. 传送代码和配置

在旧 Mac 上先确保本项目 Docker 文件已保存到 Git，然后在 M5 上用私有仓库克隆；也可通过 SSH 复制工作树（排除本地隐私数据）：

```bash
M5_USER='<M5_USER>'
M5_IP='<M5_IP>'
ssh "$M5_USER@$M5_IP" 'mkdir -p ~/pte-speaking-lab'
rsync -a --exclude='.git/' --exclude='.env' --exclude='.env.*' \
  --exclude='data/' --exclude='测试数据包/' --exclude='backend/.venv/' \
  --exclude='frontend/node_modules/' --exclude='frontend/dist/' \
  /Users/alex/codex_project/PTE口语诊断分析/ \
  "$M5_USER@$M5_IP:~/pte-speaking-lab/"
```

`.env.docker.example` 被 `--exclude='.env.*'` 排除；在 M5 上从项目仓库版本复制，或用 `rsync` 单独传此公开模板：

```bash
rsync -a /Users/alex/codex_project/PTE口语诊断分析/.env.docker.example \
  "$M5_USER@$M5_IP:~/pte-speaking-lab/.env.docker.example"
ssh "$M5_USER@$M5_IP"
cd ~/pte-speaking-lab
cp .env.docker.example .env.docker
```

编辑 `.env.docker` 中的 `PTE_DOCKER_BIND_IP` 为 M5 的固定内网 IPv4，`PTE_DOCKER_HOST_PORT` 保持 `8765`，`PTE_DOCKER_DATA_DIR` 为 M5 上**绝对路径**，例如 `/Users/<M5_USER>/pte-speaking-lab-data`。用 `openssl rand -hex 24` 生成至少 16 字符密码，填入 `PTE_LAN_PASSWORD`；不要把密码写进命令历史、Git 或聊天。`LLM_PROVIDER=none` 且 `OPENAI_API_KEY=`；暂不接 CLIProxyAPI。`PTE_LAN_BIND_IP` 不需设置为 M5 地址：容器内部监听 `0.0.0.0:8765`，宿主机端口只绑定 `PTE_DOCKER_BIND_IP` 和 `PTE_DOCKER_HOST_PORT`。

```bash
mkdir -p "$HOME/pte-speaking-lab-data"
chmod 700 "$HOME/pte-speaking-lab-data"
chmod 600 .env.docker
docker compose --env-file .env.docker config --quiet
```

端口 8765 上的 Basic Auth 经普通 HTTP 传输，适用于可信内网；若需要不可信网络访问，先加 TLS/隧道。

## 4. 在旧 Mac 制作一致数据快照并传入 M5

为避免导出期间新录音写入，短暂停止旧服务；导出后立即重启。这里的快照排除 `data/models/`、日志和 PID，但包括 SQLite 及所有业务资产。不要将快照加入 Git。

```bash
cd /Users/alex/codex_project/PTE口语诊断分析
./scripts/stop.sh
python3 scripts/export_m5_data.py export /private/tmp/pte-m5-snapshot --source data
./scripts/start.sh
python3 scripts/export_m5_data.py verify /private/tmp/pte-m5-snapshot
rsync -a /private/tmp/pte-m5-snapshot/ \
  "<M5_USER>@<M5_IP>:/Users/<M5_USER>/pte-speaking-lab-data/"
```

在 M5 的 `~/pte-speaking-lab` 目录验证：

```bash
python3 scripts/export_m5_data.py verify /Users/<M5_USER>/pte-speaking-lab-data
```

脚本通过 SQLite backup API 取得一致数据库副本，检查 `PRAGMA integrity_check`，并核对资产 SHA-256。`snapshot-manifest.json` 是数据目录内的核对清单。若重试，请先另选一个新的快照目录；不要覆盖旧快照或当前运行的数据目录。

## 5. M5 原生构建与启动

以下在 M5 的 `~/pte-speaking-lab` 执行：

```bash
docker compose --progress=plain --env-file .env.docker build
docker image inspect pte-speaking-lab:arm64-local --format '{{.Architecture}} {{.Size}}'
docker compose --env-file .env.docker run --rm --no-deps --entrypoint python \
  pte-speaking-lab scripts/prefetch_container_models.py verify
docker compose --env-file .env.docker up -d --no-build
docker compose --env-file .env.docker ps
```

镜像构建在无网络的单独层加载模型以验证预装；若依赖安装或模型验证失败，**停止部署并修正构建**。不要以 AMD64 模拟构建通过代替 ARM64 验收。检查容器系统工具和前端：

```bash
docker compose --env-file .env.docker exec pte-speaking-lab sh -c \
  'ffmpeg -version | head -1; ffprobe -version | head -1; tesseract --list-langs; espeak-ng --version; test -f /app/frontend/dist/index.html; cat /opt/pte-models/manifest.json'
docker compose --env-file .env.docker logs --tail=100
curl -i "http://<M5_IP>:8765/api/v1/health"
curl -u '<PTE_LAN_USERNAME>' "http://<M5_IP>:8765/api/v1/health"
```

第一条 `curl` 应为 401；第二条会交互询问密码，应为 200。不要用 `curl -u user:password` 让密码进入 shell 历史。从第二台内网设备浏览器访问 `http://<M5_IP>:8765/`，核对首页及历史报告。Docker Desktop 首次监听可能触发 macOS 防火墙提示，需允许 Docker 接收入站连接。

## 6. 真录音和持久性验收

在页面打开迁入的 *Choices of Lunch*，核对用户/参考录音、历史报告、截图词色、词时间轴和尾词回听。重新运行分析，记录完成状态、词级可信数、耗时、`docker stats` 峰值。再在线生成一段 Edge TTS 参考；断网时应出现可理解的失败且已迁移报告仍可打开。运行测试：

```bash
docker compose --env-file .env.docker run --rm --no-deps \
  -e PTE_LAN_MODE=false -e LLM_PROVIDER=openai \
  --entrypoint python pte-speaking-lab -m pytest backend/tests -q
docker stats --no-stream
docker compose --env-file .env.docker down
docker compose --env-file .env.docker up -d --no-build
python3 -c 'import sqlite3; db=sqlite3.connect("/Users/<M5_USER>/pte-speaking-lab-data/db/pte.sqlite3"); print(db.execute("PRAGMA integrity_check").fetchone()[0])'
```

`down` 不应删除挂载的数据目录；**不要运行 `down -v` 或删除目录**。分析会改变 SQLite，因此迁入时的快照哈希清单仅用于迁入前后首次核对，运行分析后改用数据库完整性检查。若需验证离线模型，将 M5 暂时断网并重新运行 `prefetch_container_models.py verify`，其模型加载必须成功；Edge TTS 则预期失败。记录 `docker images` 镜像大小、首次构建时间、分析时间与内存峰值，和旧 Mac 原生运行比较。通过全部验收后，才考虑停掉旧 Mac 服务。升级镜像前再做一次快照。

## 7. 排障与边界

- `docker` 命令缺失：确认 Docker Desktop 已打开并完成首次设置。
- 镜像不是 ARM64：确认 M5 上的 `uname -m` 为 `arm64`，没有设置 `DOCKER_DEFAULT_PLATFORM=linux/amd64`。
- 构建时 Python 包或模型失败：保留完整 `docker compose --progress=plain ... build` 日志，核对 Linux ARM64 wheel、源站可达性和模型许可证；不要直接跳过依赖。
- 页面无法打开：先查 `docker compose ... ps` 和日志，核对 `PTE_DOCKER_BIND_IP` 属于 M5 当前网卡且路由器已保留地址。
- 数据库不可写：检查 M5 数据目录的所有权与 Docker Desktop 文件共享授权。
- 普通 HTTP Basic 不能保护不可信网络；当前部署只面向可信家庭内网。Edge TTS 朗读稿会发送到在线服务。

安装与远程登录参考：[Docker Desktop Mac 官方文档](https://docs.docker.com/desktop/setup/install/mac-install/)、[Apple 远程登录说明](https://support.apple.com/guide/mac-help/mchlp1066/mac)。

## 2026-09-28 实际部署记录

- 目标：`zihanzong@192.168.5.19`；代码 `/Users/zihanzong/pte-speaking-lab`，持久数据 `/Users/zihanzong/pte-speaking-lab-data`。访问 `http://192.168.5.19:8765/` 需项目 Basic Auth 账号密码，密码仅在目标机器 Git 忽略的 `.env.docker`，不要写进文档或镜像。地址当前可从旧 Mac 访问；路由器 DHCP 保留仍需在路由器界面核对。
- 原生 ARM64 镜像构建成功，镜像大小约 6.07 GB（`docker image inspect .Size`）；预装模型在无网络构建层与独立断网容器中加载成功。FFmpeg、ffprobe、Tesseract `eng`、eSpeak NG 均可用。首次成功构建总时长未单独计时，不能给出可靠数字。
- 后端容器测试 **48 passed**；前端在镜像构建阶段完成生产构建。测试时覆盖生产环境的 Basic Auth 和 LLM provider 设置，以运行测试预期，不改变生产 Compose 配置。
- 已迁移一致 SQLite 备份和 55 个原始资产，迁移后 56 个文件通过快照校验；重启及新增分析后原始资产哈希不变，数据库 `integrity_check=ok`。旧报告及新报告均可访问，用户与参考录音的尾部 Range 请求返回 206。
- 真实 *Choices of Lunch* 双边录音在 M5 的两次分析约 14.35 秒与 15.12 秒，状态 `partial`，原因是部分词时间戳质量较低；并非部署错误。第二次采样容器内存峰值约 **2.291 GiB**，采样不能保证捕获瞬时峰值。在线 Edge TTS 成功；断网时返回可理解的 503 提示。M5 重启容器后历史、SQLite 和业务文件仍在。
- 一个迁移前的旧运行 `run_0817844b3ebe43d1908625a3506f7bd8d` 缺少报告结果，在旧 Mac 与 M5 均为 404；这是源数据已有的不完整记录。其他核对的历史报告可打开。当前保留旧 Mac 内网服务作为回退。
