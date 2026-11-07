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

    # 失败后允许 AI 根据日志修正计划并重试，最多两次；每版修复计划会先
    # 保存到 runs/ 并要求人工确认（输入 yes）才会执行
    python3 nebula_deploy.py apply --yes --auto-repair 2

    # 只有明确接受未经审阅的修复计划时，才跳过确认
    python3 nebula_deploy.py apply --yes --auto-repair 2 --auto-repair-yes

低于 1GB 且没有 swap 时可加 --allow-swap。仅当部署账号有免密 sudo 且 /tmp 空间不少于 700MB 时，才启用 512MB 临时 swap。

## 安全边界

- .env、私钥、证书、Git 历史、依赖与构建目录不会进入源码包或 AI 上下文。
- API Key 只从本机环境变量读取，不写配置、不发给服务器。
- 计划里的每条命令都要经过结构化安全检查：除正则外，还会去掉引号后按 shell
  操作符分段，检查每段的首个命令（rm、dd、格式化、shred 等一律拒绝；`find`
  不许用 -delete/-exec；不许写 /dev/* 设备；chmod/chown/mv/tar 的路径参数
  不得出项目目录；不许用 $()、反引号和 sh -c）。黑名单式正则防不住 shell
  语义，人工审阅计划仍是真正的安全网。
- 每条部署命令必须以 `cd <remote_dir>` 开头（`systemctl`/`service` 命令除外），
  命令只能在项目目录里操作。
- remote_dir 只能在 /opt、/srv、/var/www 或 /home/&lt;用户名&gt;/… 下面，其他位置一律拒绝。
- 健康检查必须是只读命令，不允许输出重定向；HTTP 检查只能用 curl/wget 对
  127.0.0.1、localhost 或 ::1 的 plain GET（不允许 -o、管道、POST 等）。
- remote_dir 不可写时会尝试使用免密 sudo 创建目录，并立即把目录所有权交给部署账号；没有相应权限时会安全退出。
- 上传采用合并解压，不主动删除远端旧文件；建议使用专门的非 root 部署账号。
- 默认最多打包 512MB 源码，可通过 max_source_mb 调整；符号链接不会上传，防止意外读取项目目录外的文件。
- 自动修复默认关闭。开启后，每一版修复计划都会先保存到 runs/（文件名形如
  `runs/<时间戳>-repair-1.json`），并要求人工确认（输入 `yes`）才会执行；
  只有传入 --auto-repair-yes 才跳过确认。修复计划仍会经过相同的命令安全检查，
  全部尝试及末尾日志写入 runs 目录。拒绝确认后，状态记为 repair-pending，
  审阅后可用 `apply --plan runs/<时间戳>-repair-1.json --yes` 重新执行。

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
- 计划未设置健康检查时，仍按旧行为跳过检查。健康检查必须是只读命令，不允许
  输出重定向；HTTP 检查只能用 curl/wget 对 127.0.0.1、localhost 或 ::1 的
  plain GET。
- 参数必须是整数：命令超时 1–86400 秒，健康检查超时 1–300 秒，检查次数 1–60，间隔 0–300 秒。
- 上传开始前创建 `runs/*.json`，记录上传失败、执行失败、AI 修复失败及成功状态。日志采用原子替换，文件权限为 `0600`，原有 `attempts` 字段保留。

执行时限针对远端部署命令和健康检查，不包含上传、整个 SSH 会话或主动脱离进程组的后台服务。
本版本不会自动回滚源码、数据库或服务；超时前已经发生的变更仍会保留。
进程被强制杀死或断电时，日志可能保留在最后一个进行中状态。

## 0.4.1：安全加固（2026-11-07）

- 命令校验从纯正则黑名单改为结构化检查：去引号后分段，逐段检查首个命令和
  路径参数。`dd of=/dev/sda if=/dev/zero`、`mke2fs`、`find -delete`、`tee/cp`
  写磁盘、`shred`、`chmod -R 000 /opt`、`mv` 挪走应用、引号拼出的 `rm` 等
  绕过旧黑名单的写法现在都会被拒绝；合法命令（`cd` 进项目目录后跑 npm、
  node、`systemctl` 等）不受影响。
- 自动修复不再默认直接执行：修复计划先保存到 runs/，人工确认后才应用；
  新增 --auto-repair-yes 显式跳过确认。
- remote_dir 从黑名单改为白名单：只允许 /opt、/srv、/var/www 或
  /home/&lt;用户名&gt;/… 下面；/root、/etc/cron.d、/tmp、/boot 等一律拒绝。
- 每条部署命令必须以 `cd <remote_dir>` 开头（`systemctl`/`service` 除外），
  且不得再 `cd` 到别处；输出重定向、`cp` 目标、`tee` 目标也只能写到项目
  目录内（相对路径、`/dev/null` 等安全目标、`2>&1` 除外），`~`/`$` 开头的
  目标一律拒绝；健康检查不允许输出重定向，但 `curl -sf http://127.0.0.1:3000/health`
  这样的回环 GET 检查现在可用。目标目录选项同样受限：`cp -t` /
  `--target-directory`、`rsync` 目标、`unzip -d` / `--directory`、`git clone`
  的目标目录都必须在项目目录内（相对路径、远程 rsync 目标除外）。
- runs/ 目录已存在且权限过松时会被收紧到 0700；启用临时 swap 时 runner 会
  打印 swap 文件路径。进程被 SIGKILL 时 swap 不会自动清理，用
  `sudo swapoff <打印出的路径>` 再删掉该目录即可。
- AI 返回限制为 2 MiB，超出时报错；ssh.port 和 max_source_mb 现在和超时
  参数一样，只接受真整数（布尔值会被拒绝）。

运行本地回归测试（无需 SSH 或 AI 密钥）：

```sh
python3 -m unittest discover -s . -v
```

## 环境与许可

控制端需要 Python 3.10+、OpenSSH 的 `ssh` / `scp`；Python 程序使用标准库，无需安装 pip 依赖。实际部署需要可用的 SSH 账号、目标目录权限和兼容的 AI 接口。目标 Linux 还需 `tar` 与 GNU `timeout`。

本仓库尚未指定项目代码许可证。第三方工具按各自许可证使用。
