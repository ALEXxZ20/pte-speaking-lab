# M5 Docker 部署过程与资产记录

记录日期：2026-09-28。本文记录**已实际完成**的操作与核对结果；可复用命令见 [运维手册](OPERATIONS.md)，从零安装和迁移步骤见 [M5 部署手册](M5_DOCKER_DEPLOYMENT.md)。后续代码归档于私有仓库提交 `8d0b63c`；运行镜像在该最终文档提交之前由同一工作树的应用代码构建，不能声称镜像字节与该提交完全一致。

## 两台机器与部署资产

| 项目 | M2 原生服务 | M5 Docker 服务 |
|---|---|---|
| 主机与系统 | MacBook Air M2 / 24 GB / macOS ARM64 | MacBook Pro M5 Pro / 48 GB / macOS ARM64，Docker Linux ARM64 VM |
| 地址 | `192.168.5.14:8765` | `192.168.5.19:8765` |
| 代码 | `/Users/alex/codex_project/PTE口语诊断分析` | `/Users/zihanzong/pte-speaking-lab` |
| 配置 | 仅 M2 的 `.env` | 仅 M5 的 `.env.docker`，权限 600 |
| 数据 | M2 项目 `data/` | M5 `/Users/zihanzong/pte-speaking-lab-data/`，权限 700 |
| 启动机制 | `launchd` 与 `scripts/start.sh` | Docker Desktop 与单服务 Compose |

两台主机目前是两个独立实例。M5 取得了 M2 在迁移时点的一次数据快照；之后的写入不自动同步。M5 的运行密码随机生成，实际值只在 M5 的 Git 忽略配置文件中，未进入镜像、仓库或本文。

## 实际部署顺序

1. 在 M5 的 `zihanzong` 账号完成 Docker Desktop 首次图形界面授权，确认 Docker 引擎架构 `aarch64`。SSH 非交互 shell 的 PATH 起初缺少 Docker Desktop 凭据工具，加入 `/Applications/Docker.app/Contents/Resources/bin` 后可执行构建。
2. 从 M2 用 SSH/rsync 传送项目工作树，排除 `.git`、`.env*`、`data/`、真实测试包、虚拟环境、`node_modules` 和构建产物。公开 `.env.docker.example` 单独传送。实际配置只在 M5 创建。
3. 暂停 M2 内网服务，通过 SQLite backup API 导出一致快照并逐项计算 SHA-256；随后立即恢复 M2 服务。快照共 56 个文件（数据库及 55 个原始资产）。传至 M5 的镜像外持久目录后通过哈希与数据库完整性核对。
4. 在 M5 构建原生 ARM64 单镜像。首轮非交互构建遇到 Docker 凭据工具 PATH 问题；下一轮模型预取遇到 NLTK 默认下载被网络代理拦截。改从官方 NLTK 数据仓库下载固定 `punkt_tab` 归档并校验 SHA-256 后构建成功。在无网络构建层和另一个断网容器里验证预装模型可加载。
5. 启动单个 Compose 应用容器，绑定 M5 内网 IP 的 8765 端口；SQLite 和原始资产通过 bind mount 留在镜像外。未启用 M2 上的 CLIProxyAPI，M5 使用本地规则总结。
6. 在容器中执行后端测试，**48 passed**；前端生产构建在镜像构建阶段通过。真实 *Choices of Lunch* 双边录音完成两次分析，分别约 14.35 秒和 15.12 秒；采样内存峰值约 2.291 GiB。两次报告是 `partial`，原因是少量词时间戳质量不足，发音/流利度/比较/诊断/总结仍生成。
7. 核对授权首页、健康检查、历史 API 均为 200，未授权 API 为 401；从另一台 Mac 请求 M5 内网地址也得到 401，证明跨设备网络可达。双方录音尾部的 HTTP Range 请求返回 206 和预期字节数。在线 Edge TTS 成功，断网时返回可理解的 503。执行 Compose 停止和重新启动后，历史记录、数据库及文件仍在；55 个原始资产哈希不变，SQLite `integrity_check=ok`。

## 镜像边界和剩余事项

- 镜像名称 `pte-speaking-lab:arm64-local`，实测大小 **6,072,283,625 字节**（约 6.07 GB）。镜像内有编译前端、FastAPI、Linux ARM64 Python 依赖、FFmpeg、Tesseract 英文 OCR、eSpeak NG、WhisperX/OpenPronounce 权重。模型在 Docker Linux VM 的 CPU 上运行，无法调用 Mac Metal GPU。Node 用于构建阶段，非运行必需；真实数据、运行凭据、CLIProxyAPI 和本机 macOS 虚拟环境均不在镜像中。
- 当前 M5 Docker VM 约 **8 GB**，足够已验证的这组任务；未来更大模型可能需在 Docker Desktop 图形界面提高至约 28 GB，并重新测量。采样峰值不保证覆盖瞬时峰值。首次完整成功构建时长未被可靠计时。
- `192.168.5.19` 的路由器 DHCP 地址保留仍需在路由器界面核对。当前仅可信内网 HTTP Basic，不用于公网暴露。Edge TTS 依赖网络。
- 迁移前已有一个运行 `run_0817844b3ebe43d1908625a3506f7bd8d` 缺少报告结果；M2 与 M5 均为 404，属源数据既有的不完整记录。核对的其他新旧报告可打开。
- 2026-09-28 复查时 M5 容器仍 `healthy`；M2 原生服务也在监听。M2 虽已安装 Docker Desktop 应用与 CLI，但当时引擎未运行、Compose 插件未被 CLI 识别；**M2 Docker 并行实例尚未部署或验收**。同一台 Mac 并行运行的端口和数据隔离方案已写入 [运维手册](OPERATIONS.md)，实际构建成功和性能仍待在 M2 验证。
