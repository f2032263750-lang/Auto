# M2 日志字段与运行规则

## 边界

M2 只实现 Windows 客户端本地日志、查询和查看能力，不实现 API、数据库、仪器通信或日志上传。
`D:\Auto\PySide6软件数据选取界面` 作为项目方已完成的正式数据界面保留，M2 不修改该目录；M7 整合时通过本模块接口记录导入、导出、保存和测量快照事件。

## 日志文件

| 通道 | 文件名 | 用途 |
|---|---|---|
| `business` | `business-YYYY-MM-DD.jsonl` | 启动、退出、任务状态、计算结果和业务异常 |
| `audit` | `audit-YYYY-MM-DD.jsonl` | 登录、配置修改、安全确认和编号变更等可追溯操作 |
| `communication` | `communication-YYYY-MM-DD.jsonl` | 设备、接口、SCPI、响应、耗时和通信错误 |

文件采用 UTF-8 JSON Lines，每行是一个完整 JSON 对象。按本地日期每日自然分卷，客户端保留最近 365 个日历日。

## 通用字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | 是 | 日志结构版本，M2 为 `1` |
| `timestamp` | 是 | 带时区的 ISO 8601 时间，精确到毫秒 |
| `channel` | 是 | `business` / `audit` / `communication` |
| `level` | 是 | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `event_code` | 是 | 稳定的大写事件编码 |
| `module` | 是 | 产生事件的模块 |
| `message` | 是 | 面向运维和开发人员的中文摘要 |
| `workstation_id` | 否 | 工位编号 |
| `user_id` / `task_id` | 否 | 用户和任务上下文 |
| `device` / `interface` / `operation` | 否 | 设备、接口和操作上下文 |
| `duration_ms` | 否 | 毫秒耗时 |
| `success` | 否 | 操作成功/失败 |
| `error_type` / `error_message` / `traceback` | 否 | 异常诊断信息 |
| `details` | 否 | 事件特有的结构化字段 |

## 等级、脱敏和失败行为

- `development` 和 `test` 记录 `DEBUG` 及以上；`production` 记录 `INFO` 及以上。
- 字段名包含 password、passwd、pwd、token、secret、authorization、credential 或 API key 时，值统一写为 `[REDACTED]`。
- 日志调用不向业务层抛出文件系统异常；写入失败只记录在 `last_error`，不能阻止后续安全命令。
- 查看功能只读，不提供编辑、删除或导出日志的功能。
- 已确认正式软件中的日志查看入口只对管理员/维护人员开放，普通校准员工不显示。M3 权限模型完成前，`development`/`test` 环境显示入口用于开发验收，`production` 环境隐藏入口；M3 完成后改由用户权限决定。
