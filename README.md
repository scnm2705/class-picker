# 班级点名器

用于课堂的本地随机点名工具，提供 3D 棋盘、掷骰、国王棋子、宝箱事件、VIP 设置和名单管理。

## 下载与运行

在本仓库右侧 **Releases** 中下载 V1.0 的 ZIP 压缩包，完整解压后运行 `班级随机点名器_V1.0.exe`。

发布包包含：

- Windows 64 位主程序，内置星空背景和 3D 资源。
- `使用说明.txt`：完整操作说明。
- `样例名单_仅供测试.xlsx`：名单导入格式参考。

首次启动先选择班级，再进入 3D 棋盘。示例班级为演示用途，正式使用前请导入实际名单并核对 VIP 设置。

## 功能

- 可拖动、缩放及全屏的 3D 棋盘，支持按班级人数调整布局。
- 每颗骰子 1～6 点，棋子从当前位置逐格移动；骰子数量由用户设置。
- 可配置宝箱内容、随机学生事件和概率，支持智能比例调整。
- 直接显示、骰子动画、移动动画、名字凸显四项可分别开关并设置时间，无音效。
- 双击棋盘跳过当前批次展示，右侧保留本轮点名名单。
- 支持改名、移出/恢复、VIP、缺席、历史、补抽和本地备份。

## 环境与数据

3D 窗口需要本机具备 Microsoft Edge WebView2 运行时。运行环境准备好后，日常使用无需联网。

班级数据保存在本地，默认位于程序旁的 `data` 文件夹。本仓库包含 V1.0 源码、测试、构建配置和发布包下载入口，不包含使用者的班级数据。

详细规则、保护密码、重置与恢复操作请阅读压缩包内的使用说明。

## 从源码运行

使用 Windows 64 位、Python 3.12（含 Tkinter）及 WebView2 运行时。在仓库根目录打开 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe python_app.py
```

开发环境首次安装依赖需要联网。前端 Three.js 和背景图已随源码提供，无需 npm 安装或在线 CDN。
源码运行时，示例数据默认生成在仓库下 `班级随机点名器_V1.0/data`，该目录已排除出 Git。

## 构建 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist --workpath build "班级随机点名器_V1.0.spec"
```

产物位于 `dist/班级随机点名器_V1.0.exe`。分发时可附上 `docs/使用说明.txt` 和根目录样例名单。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest test_board test_python test_maintenance test_storage -q
node board_web/test-model.cjs
node board_web/test-integrated.cjs
node board_web/test-console.cjs
node board_web/test-probability.cjs
node board_web/test-layout.cjs
```

前端测试需要 Node.js，使用本地 Three.js。窗口自检需要 Windows 图形桌面及 WebView2：

```powershell
.\.venv\Scripts\python.exe python_app.py --health-check
.\.venv\Scripts\python.exe python_app.py --window-health-check --report webview-source-check.json
```

窗口自检使用临时示例数据。模拟渲染检查不等同于人工视觉验收。

## 源码结构

- `python_app.py`：开始界面、管理界面及应用入口。
- `python_core.py`：点名规则、权重、VIP、历史和持久化。
- `python_board.py`：棋盘落点、宝箱与批次规则。
- `python_board_server.py`、`python_board_window.py`：本地接口与 WebView2 窗口。
- `python_storage.py`、`python_maintenance.py`：数据位置、备份、密码和恢复。
- `board_web/`：3D 场景、骰子、控制台、样式、背景图及前端测试。
- `docs/使用说明.txt`：完整使用说明。

Three.js 的 MIT 许可保留在 `board_web/vendor/THREE-LICENSE.txt`。
