# 台式万用表自动校准软件

当前开发版本为 `V0.2.0`，已完成 M1，并实现 M2 日志系统的候选验收版。

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

## M2 日志

- 业务、审计和通信日志分别写入 UTF-8 JSONL 文件。
- 按日分卷，本机保留 365 天；日志目录来自工位配置。
- 密码、令牌和认证头等敏感字段自动脱敏。
- 日志写入失败不向业务层抛出文件系统异常。
- development/test 环境的“日志查看”支持日期、类型、级别和关键字过滤，不提供编辑或删除。production 环境在 M3 权限模型完成前隐藏该入口。

完整字段和运行规则见 `docs/M2_logging_spec.md`。

## 当前边界

- UI 不发送或拼接 SCPI。
- 当前不实现仪器控制、MPE 计算、自动测量或 Excel 原始记录。
- Windows 客户端不连接服务器数据库。
- 健康检查只约定客户端请求 `GET /health`；M1 不选择或实现正式服务端框架。
- `D:\Auto\PySide6软件数据选取界面` 是项目方已完成的正式数据界面，M2 不修改该目录。
