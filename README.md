# nwu-mcp

西北大学正方教务系统（`jwgl.nwu.edu.cn/jwglxt/` V-9.0）MCP 服务器，纯 HTTP RSA 自动登录，无需启动浏览器即可让 AI 客户端查询校内教务信息。

## 已实现功能

| 工具名 | 说明 |
| --- | --- |
| `jw_schedule` | 个人课表查询，支持指定学年/学期与按周次筛选 |
| `jw_grades` | 课程成绩查询，支持按学年/学期与课程名关键字过滤 |
| `jw_exams` | 考试安排查询（考试名称、日期、时间、校区、考场、座位号） |
| `jw_classrooms` | 空闲教室查询（支持校区、周次、星期、节次、教学楼、最小座位数，及楼栋/周次元数据） |
| `jw_notices` | 消息通知查询（个人待阅/已阅消息、调停补课通知 + 系统公告列表与正文详情） |
| `jw_plan` | 培养方案、教学执行计划与个人学业修读进度查询 |
| `jw_page` | 通用站内页面抓取工具（返回标题、表格、链接与正文） |
| `jw_refresh_login` | 手动刷新教务登录态（正常情况会话过期会自动静默重登） |

## 安装与配置

### 1. 安装依赖

项目使用 `uv` 管理 Python 环境（Windows / macOS / Linux 通用）：

```bash
uv sync
```

### 2. 配置本地凭据

在用户目录下创建 `~/.config/nwu-mcp/credential.json`（Windows 路径为 `%USERPROFILE%\.config\nwu-mcp\credential.json`）：

```json
{
  "studentNo": "你的学号",
  "password": "教务系统密码"
}
```

也可以通过环境变量传入：`NWU_JW_STUDENT_NO` 与 `NWU_JW_PASSWORD`。

### 3. 在 MCP 客户端中注册

以 Claude Desktop / Cursor / Antigravity 的 `mcpServers` 配置为例：

```json
{
  "mcpServers": {
    "nwu-jw": {
      "command": "uv",
      "args": [
        "--directory",
        "C:/Users/alan5/Desktop/nwu-mcp",
        "run",
        "nwu-mcp"
      ]
    }
  }
}
```

## 本地测试

```bash
uv run pytest
```

## 致谢

本项目灵感与设计思路来自 [DrivingGodJ/njust-jw-mcp](https://github.com/DrivingGodJ/njust-jw-mcp)（Inspired by `DrivingGodJ/njust-jw-mcp`），在此基础上针对西北大学正方教务系统（V-9.0）与全 Python `MCPServer` 架构进行了重新设计与实现。

