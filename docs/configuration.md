# M1 工位配置字段说明

配置文件默认位于 `D:\Auto\data\config\workstation.json`，采用 UTF-8 JSON。写入时先在同一目录生成临时文件，再使用原子替换，避免程序中断留下半写文件。

| 字段 | 类型 | 默认值 | 规则 |
|---|---|---|---|
| `config_version` | 整数 | `1` | 当前只接受版本1 |
| `environment` | 字符串 | `development` | `development`、`test`、`production` |
| `workstation_id` | 字符串 | `CAL-01` | 仅字母、数字、下划线和连字符 |
| `calibrator_model` | 字符串 | `Fluke 9100` | 非空 |
| `calibrator_interface` | 字符串 | `GPIB转USB` | 非空 |
| `calibrator_gpib_controller` | 字符串 | `GPIB0` | 非空 |
| `calibrator_gpib_address` | 整数 | `10` | 0～30 |
| `uut_terminal` | 字符串 | `FRONT` | 首版固定为 `FRONT` |
| `default_temperature` | 十进制字符串 | `23` | 内部配置项，不在M1系统设置界面显示；必须为有限 Decimal，不作为是否允许测量的条件 |
| `default_humidity` | 十进制字符串 | `50` | 内部配置项，不在M1系统设置界面显示；取值0～100，不作为是否允许测量的条件 |
| `excel_template_path` | 绝对路径 | `D:\Auto\templates` | 保存时确保目录可创建/可访问 |
| `cache_directory` | 绝对路径 | `D:\Auto\data\cache` | 保存时确保目录可创建/可访问 |
| `log_directory` | 绝对路径 | `D:\Auto\data\logs` | 保存时确保目录可创建/可访问 |
| `server_host` | 字符串 | 空 | 已确认服务器IP为 `189.189.0.27`；业务API端口确认后与端口同时填写，不允许空白字符 |
| `server_port` | 整数或空 | 空 | 业务API端口待定；填写时为1～65535，不得使用管理面板端口代替 |
| `offline_cache_enabled` | 布尔值 | `true` | 服务器不可用时不阻止客户端启动 |

## 版本和恢复

- 未识别的配置版本、字段缺失、字段类型错误或 JSON 损坏均视为不可加载配置。
- 客户端不会直接覆盖损坏文件；用户确认恢复后，原文件先改名为 `workstation.broken.<时间戳>.json`，再生成默认配置。
- 可通过 `--config-dir` 或环境变量 `DMM_CALIBRATION_CONFIG_DIR` 覆盖配置目录，路径不会写入业务逻辑。

## M1 健康检查约定

客户端在已配置服务器地址和端口时异步请求 `http://<server_host>:<server_port>/health`。HTTP 2xx 视为在线，其余响应、连接失败或超时视为离线。该约定仅用于 M1 客户端探测，不代表正式服务端技术栈选择。

## 已确认的服务器基线

- 服务器IP：`189.189.0.27`。
- 操作系统：AlmaLinux 9.6。
- 管理面板：`http://189.189.0.27:42734/smq27`。该地址仅用于服务器运维管理，端口 `42734` 不是业务API端口，不写入普通客户端配置。
- 服务端业务数据库：MariaDB 11.8.2（`mysql-mariadb_11.8.2`），后续服务端模块必须使用该数据库。
- 业务API端口：待服务器管理员根据反向代理和防火墙策略确认。
- Windows客户端只通过业务API访问服务端，不安装数据库连接驱动，不保存MariaDB账号/密码，也不直接连接数据库。

由于业务API端口尚未确认，当前 `workstation.json` 中 `server_host` 和 `server_port` 继续同时留空，客户端正常启动并显示离线。端口确认后再将 `server_host` 设置为 `189.189.0.27` 并同时填写正式业务API端口。
