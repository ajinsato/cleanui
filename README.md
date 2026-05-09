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

## 四、运行

- 图形界面：

  ```bash
  cleanui
  ```

  或：

  ```bash
  python3 -m cleanui
  ```

- 部分清理项会执行 `sudo` 类命令。若需系统级清理，请用有权限的终端会话启动，或在系统策略允许的前提下以 root 运行；否则相关步骤会在应用内日志中失败。

---

## 五、从旧版「单文件 + 包装脚本」迁移

若你曾使用 `~/.local/share/cleanui/cleanui.py` 与手动写的 `~/.local/bin/cleanui`：

1. 按上文在本仓库根目录执行 **`pip install --user -e .`**。
2. 删除或改名为备份旧的包装脚本，避免 PATH 仍指向旧路径。
3. 确认 `which cleanui` 指向 **`~/.local/bin/cleanui`**（由 pip 生成）。

---

## 六、版本与许可

- 版本号见 **`pyproject.toml`** 或运行 **`cleanui --version`**。
- 许可证：MIT（见 `pyproject.toml`）。
