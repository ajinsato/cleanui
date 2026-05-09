# CleanUI

Linux 桌面图形清理工具（Python + Tkinter）。**本文档说明如何把本工具部署到你的环境中并运行。**

---

## 一、部署要求

| 项目 | 说明 |
|------|------|
| 操作系统 | 常见 Linux 发行版，带桌面会话 |
| Python | **3.9 及以上** |
| 图形环境 | 需可用的 Tk（多为 `python3-tk` 包）；在 X11 或 Wayland 下均可（取决于发行版对 Tk 的支持） |
| 可选 | `fontconfig` 的 `fc-list` / `fc-match`，用于界面中文字体选择 |

**依赖安装示例（Debian/Ubuntu）：**

```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
```

---

## 二、获取代码并安装（核心部署步骤）

在存放源码的目录执行以下任一方式。

### 一键脚本（推荐）

克隆仓库后，在**仓库根目录**（含 `pyproject.toml`）执行：

```bash
chmod +x install.sh    # 仅需首次
./install.sh
```

脚本会：

1. **依赖检查（默认开启）**：确认 Python **3.9+**、**pip**、**tkinter** 可用；若缺失且检测到 **`apt-get` / `dnf` / `yum` / `pacman`**，会提示并用 **sudo** 安装对应包（如 Debian/Ubuntu：`python3`、`python3-pip`、`python3-tk`、`fontconfig`）。
2. **`pip install --user -e .`**（默认用户级可编辑安装）。
3. 在 **`~/.profile`** 中按需追加 **`python -m site --user-base`/bin** 到 `PATH`。
4. 在 **`~/.local/share/applications/`** 写入 **CleanUI** 桌面菜单项（可用参数跳过）。

常用参数：

| 参数 | 含义 |
|------|------|
| （默认） | 自动检测并尝试安装系统依赖（需 sudo，首次会询问） |
| `-y` / `--yes` | 非交互，自动同意 sudo 安装依赖等 |
| `--no-install-deps` | **不**安装系统包；环境缺 Tk/pip 时会失败并提示 |
| `--install-deps` | 显式开启依赖安装（与默认相同） |
| `--system` | **sudo** 系统级 pip 安装（多用户；部分发行版需 PEP 668，脚本会再试 `--break-system-packages`） |
| `--no-desktop` | 不安装 `.desktop` |
| `--no-path` | 不修改 `~/.profile` |
| `--git-hooks` | 设置 `core.hooksPath=.githooks`，提交前自动递增 **VERSION** |

示例：`./install.sh -y`（无人值守）、`./install.sh --no-install-deps`（依赖已自备）

### 方式 A：当前用户安装（推荐日常桌面使用）

```bash
cd /path/to/cleanui   # 克隆后的仓库根目录，内含 pyproject.toml
python3 -m pip install --user -e .
```

- `-e` 表示可编辑安装：后续修改源码无需重复安装（仅需重启程序）。
- `--user` 将脚本安装到用户目录，无需 root。

### 方式 B：虚拟环境部署（推荐开发与隔离依赖）

```bash
cd /path/to/cleanui
python3 -m venv .venv
source .venv/bin/activate          # Windows 使用 .venv\Scripts\activate
pip install -e .
```

使用虚拟环境时，仅在激活该环境后 `cleanui` 命令可用。

### 方式 C：系统范围安装（多用户共享）

```bash
cd /path/to/cleanui
sudo python3 -m pip install .
```

需管理员权限；升级时用相同命令指定新版本源码路径。

---

## 三、部署后检查

确认命令可用且不会误启图形界面：

```bash
cleanui --version
cleanui --help
```

若提示找不到 `cleanui`，说明脚本目录不在 `PATH` 中。用户级 pip 默认脚本路径一般为 **`~/.local/bin`**，请在本机 shell 配置中加入：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

（写入 `~/.bashrc` 或 `~/.profile` 后重新打开终端。）

---

## 四、运行与管理员权限（sudo）

### 启动图形界面

直接运行 **`cleanui`** 时，程序会**先执行一次 `sudo -v`**（终端里提示输入密码），再打开窗口。这样在默认的 sudo 缓存时间内，点击「立即清理」里的 **`sudo apt-get` / `sudo journalctl`** 等往往不用再输密码。

```bash
cleanui
# 或
python3 -m cleanui
```

不需要系统级清理、或自动化脚本勿交互时：

```bash
cleanui --no-sudo-warmup
```

### 为何不建议「整个程序用 sudo 运行」

若以 **`sudo cleanui`** 启动，进程的 **`$HOME`、回收站、用户缓存路径等会变成 root 视角**，容易扫错、删错。**推荐仍以普通用户启动界面**，仅让个别清理命令通过 **`sudo`** 提升权限。

### 其他说明

| 方式 | 说明 |
|------|------|
| **`cleanui-sudo`** | 与 **`cleanui`** 行为相同（保留便于旧桌面快捷方式）；仍会先 `sudo -v`。 |
| **终端里先 `sudo -v` 再 `cleanui`** | 若刚验证过 sudo，第一次启动时的密码提示可能很快结束或不再出现（取决于系统缓存）。 |
| **`sudoers` 细粒度免密** | 可由管理员配置 **仅对固定路径命令** `NOPASSWD`（风险高）。 |

从**桌面图标**启动且未配置图形化 sudo 时，可能没有 TTY 输入密码，`sudo -v` 会失败；界面仍会打开，但系统级清理可能失败。请**从终端**运行一次 **`cleanui`** 完成密码验证，或使用 **`cleanui --no-sudo-warmup`** 作为图标启动命令（仅扫用户目录项）。

### 帮助与版本

```bash
cleanui --help
cleanui --version
```
（`--help` / `--version` **不会**触发 `sudo -v`。）

## 五、从旧版「单文件 + 包装脚本」迁移

若你曾使用 `~/.local/share/cleanui/cleanui.py` 与手动写的 `~/.local/bin/cleanui`：

1. 按上文在本仓库根目录执行 **`pip install --user -e .`**。
2. 删除或改名为备份旧的包装脚本，避免 PATH 仍指向旧路径。
3. 确认 `which cleanui` 指向 **`~/.local/bin/cleanui`**（由 pip 生成）。

---

## 六、版本号管理

- **唯一来源**：仓库根目录的 **`VERSION`** 文件（形如 `主版本.次版本.补丁`，一行）。
- **打包**：`pyproject.toml` 通过 **`[tool.setuptools.dynamic]`** 从该文件读取版本，勿手工改 `toml` 里的版本字段。
- **界面与 CLI**：程序标题栏、关于区与 **`cleanui --version`** 均读取 **`cleanui.__version__`**（开发时优先读源码树中的 `VERSION`，安装包则回退到发行版元数据）。
- **每次提交自动 +1**：克隆本仓库后执行一次：
  ```bash
  ./scripts/install-git-hooks.sh
  ```
  或 **`./install.sh --git-hooks`**（需在 git 仓库内）。启用后 **`git commit`** 会运行 **`scripts/bump_version.py`**，将 **`VERSION`** 的**补丁号加一并纳入本次提交**。
- **跳过某次递增**（例如仅改文档、或 `git commit --amend` 不想再加版本）：
  ```bash
  SKIP_VERSION_BUMP=1 git commit ...
  ```

## 七、许可

- 许可证：MIT（见 `pyproject.toml`）。
