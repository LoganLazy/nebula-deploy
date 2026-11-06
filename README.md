# Nebula Deploy

[项目仓库](https://github.com/LoganLazy/nebula-deploy) · [问题反馈](https://github.com/LoganLazy/nebula-deploy/issues)

> 面向轻量 Linux 服务器的 AI SSH 部署助手：计划审阅、限时执行、健康检查与本地审计日志。

Nebula Deploy 是面向 0.5–1GB 小内存 Linux 服务器的 AI SSH 部署助手。AI 在控制端分析源码并生成计划；服务器只接收源码包和一次性 Shell 执行器，结束后自动清理执行器。

## 工作流程

1. SSH 读取系统、内存、磁盘和工具。
2. 本机读取文件树与关键构建配置，由兼容 OpenAI Chat Completions 的 AI 生成 JSON 计划。
3. 人工审阅；只有传入 --yes 才上传源码并部署。
4. 远端限制构建并发为 1，执行命令和健康检查。
5. 清除临时执行器与可选 swap，在本机 runs 目录保留审计记录。

## 使用

    git clone https://github.com/LoganLazy/nebula-deploy.git
    cd nebula-deploy
    python3 nebula_deploy.py init
    # 编辑 deploy.json
    export DEPLOY_AI_KEY='你的密钥'
    python3 nebula_deploy.py inspect
    python3 nebula_deploy.py plan
    python3 nebula_deploy.py apply --dry-run
    python3 nebula_deploy.py apply --yes

    # 失败后允许 AI 根据日志修正计划并重试，最多两次
    python3 nebula_deploy.py apply --yes --auto-repair 2

低于 1GB 且没有 swap 时可加 --allow-swap。仅当部署账号有免密 sudo 且 /tmp 空间不少于 700MB 时，才启用 512MB 临时 swap。

## 安全边界

- .env、私钥、证书、Git 历史、依赖与构建目录不会进入源码包或 AI 上下文。
- API Key 只从本机环境变量读取，不写配置、不发给服务器。
- 拒绝根目录删除、格式化、关机、curl/wget 等高风险计划。
- remote_dir 必须是具体绝对目录，不能是根目录或关键系统目录。
- remote_dir 不可写时会尝试使用免密 sudo 创建目录，并立即把目录所有权交给部署账号；没有相应权限时会安全退出。
- 上传采用合并解压，不主动删除远端旧文件；建议使用专门的非 root 部署账号。
- 默认最多打包 512MB 源码，可通过 max_source_mb 调整；符号链接不会上传，防止意外读取项目目录外的文件。
- 自动修复默认关闭。开启后，每一版修复计划仍会经过相同的命令安全检查，全部尝试及末尾日志写入 runs 目录。

## 0.4.0：部署可靠性升级

旧配置和 Nebula Panel 的调用参数继续有效，新增配置可省略。目标 Linux 需要提供支持
`-k` 参数的 `timeout` 工具（通常由 GNU coreutils 提供）。上传解压前会检查工具是否存在。

在 `deploy.json` 中可添加：

```json
"execution": {
  "command_timeout": 900,
  "healthcheck_timeout": 10,
  "healthcheck_attempts": 5,
  "healthcheck_interval": 3
}
```

- 每条部署命令默认最多运行 900 秒，超时后停止后续步骤；发送终止信号后最多再等待 5 秒，仍未退出则强制结束。
- 健康检查每次最多 10 秒，失败后间隔 3 秒重试，最多 5 次。重试健康检查不会重复运行部署命令；全部失败后才进入已授权的 AI 自动修复流程。
- 计划未设置健康检查时，仍按旧行为跳过检查。健康检查应使用只读、可重复执行的命令。
- 参数必须是整数：命令超时 1–86400 秒，健康检查超时 1–300 秒，检查次数 1–60，间隔 0–300 秒。
- 上传开始前创建 `runs/*.json`，记录上传失败、执行失败、AI 修复失败及成功状态。日志采用原子替换，文件权限为 `0600`，原有 `attempts` 字段保留。

执行时限针对远端部署命令和健康检查，不包含上传、整个 SSH 会话或主动脱离进程组的后台服务。
本版本不会自动回滚源码、数据库或服务；超时前已经发生的变更仍会保留。
进程被强制杀死或断电时，日志可能保留在最后一个进行中状态。

运行本地回归测试（无需 SSH 或 AI 密钥）：

```sh
python3 -m unittest discover -s . -v
```

## 环境与许可

控制端需要 Python 3.10+、OpenSSH 的 `ssh` / `scp`；Python 程序使用标准库，无需安装 pip 依赖。实际部署需要可用的 SSH 账号、目标目录权限和兼容的 AI 接口。目标 Linux 还需 `tar` 与 GNU `timeout`。

本仓库尚未指定项目代码许可证。第三方工具按各自许可证使用。
