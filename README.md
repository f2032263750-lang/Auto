# 台式万用表自动校准软件

当前版本为 `V0.1.0`，仅实现开发模块 M1：项目骨架、工位配置、系统设置界面和客户端服务器健康检查。

## 环境

- Windows 11 x64
- Python 3.13.14
- PySide6 6.8.3
- Qt Widgets

## 初始化

在 PowerShell 中进入本目录后执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## 启动

```powershell
.\.venv\Scripts\python.exe -m dmm_calibration
```

首次启动会在 `D:\Auto\data\config\workstation.json` 创建默认工位配置。也可以通过命令行指定其他配置目录：

```powershell
.\.venv\Scripts\python.exe -m dmm_calibration --config-dir D:\Temp\dmm-config
```

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## M1 边界

- UI 不发送或拼接 SCPI。
- 本模块不实现仪器控制、MPE 计算、自动测量、业务日志或 Excel 原始记录。
- Windows 客户端不连接服务器数据库。
- 健康检查只约定客户端请求 `GET /health`；M1 不选择或实现正式服务端框架。
