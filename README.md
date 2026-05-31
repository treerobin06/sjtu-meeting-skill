# SJTU Meeting Skill

用于上海交通大学云视频会议平台 `meeting.sjtu.edu.cn` 的 Agent Skill 和 Python CLI。

它不模拟浏览器表单，而是直接调用平台后端 API，帮助 agent 或用户脚本完成会议查询、创建、批量创建、删除、获取腾讯会议入会链接、查询占用时段和日历视图等操作。

## 功能概览

- 查询未来或历史会议列表。
- 获取单个会议详情，包括腾讯会议入会链接、会议号、密码、主持人、联席主持人、直播链接等。
- 创建单个会议，支持主题、日期、时间、时长、会议室组、密码、联席主持人。
- 从 JSON 批量创建会议，默认并发 4。
- 按每周固定模板展开 recurring meetings，并支持 dry-run 预览。
- 按内部会议 ID 删除会议。
- 查询某天某会议室组的半小时占用状态。
- 查询 day / week / month 日历视图。
- 验证当前 `user_token` 是否有效。

## 为什么做这个工具

网页 UI 适合人工创建单个会议，但对 agent 自动化不够稳定：

- 浏览器表单自动化速度慢、容易受 UI 改版影响。
- 一学期固定会议通常需要批量创建，手工重复成本高。
- 创建接口本身会返回腾讯会议入会链接，不必逐个打开详情页复制。
- agent 更适合消费结构化 JSON 输出，并按安全边界组合原子命令。

本仓库包含：

- `scripts/sjtu_meeting.py`：Python CLI 主程序。
- `SKILL.md`：给 agent 使用的 skill 说明。
- `references/api.md`：后端接口、payload、response 和安全边界说明。
- `docs/credential-setup.md`：登录态和凭证获取的详细说明。
- `docs/agent-cookie-capture.zh.md`：给用户自己的 agent 自动抓取已登录浏览器 token 的中文操作手册。
- `assets/recurring_meetings.json`：公开示例 recurring 会议模板。
- `examples/creds.example.json`：凭据文件示例，不包含真实 token。

## 认证模型

平台后端接受一个 `user_token`。实测在不带浏览器 cookie 的情况下，只要把这个 token 带到 API 请求里，也可以访问当前用户自己的会议数据。

CLI 会把 token 同时放在两个位置：

- HTTP header：`user-token: <token>`
- 表单 body：`user_token=<token>`

token 来源于用户已经登录 `meeting.sjtu.edu.cn` 后，浏览器里的 `user_info` cookie。这个仓库不包含账号密码、cookie 或真实 token。

凭据读取顺序：

1. 命令行参数 `--token`
2. 环境变量 `SJTU_MEETING_TOKEN`
3. 本地凭据 JSON 文件

默认凭据文件：

```text
~/.config/sjtu-meeting/creds.json
```

也可以用环境变量改路径：

```bash
export SJTU_MEETING_CREDS=/path/to/creds.json
```

最小凭据文件：

```json
{
  "user_token": "paste-token-here",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

建议权限：

```bash
mkdir -p ~/.config/sjtu-meeting
chmod 700 ~/.config/sjtu-meeting
chmod 600 ~/.config/sjtu-meeting/creds.json
```

## 给陌生用户和 Agent 的凭证设置流程

推荐流程是“用户自己登录，agent 只读取授权后的浏览器登录态”，不需要把 jAccount 密码交给 agent。详细版见 [docs/agent-cookie-capture.zh.md](docs/agent-cookie-capture.zh.md)。

前提：

- 用户本机已经有浏览器，并且 agent 有权限访问这个浏览器或它的调试接口。
- 用户已经在该浏览器里登录 `https://meeting.sjtu.edu.cn`，或者愿意在 agent 提示后手动登录。
- agent 必须 attach 到用户已有登录态的浏览器/profile；如果开的是全新无状态浏览器，就拿不到 cookie。

1. 用户在自己的浏览器打开 `https://meeting.sjtu.edu.cn`。
2. 用户自己完成 SJTU SSO 登录。
3. 用户授权 agent 读取当前页面同源的 `user_info` cookie。
4. agent 只提取其中的 JSON 字段 `token`。
5. agent 把 token 写入本地凭据文件，并设置文件权限为 `600`。
6. agent 运行 `whoami` 验证 token 是否有效。

可以给 agent 的提示词：

```text
我已经在本机浏览器登录 https://meeting.sjtu.edu.cn，并允许你访问这个已登录浏览器的页面上下文。
请 attach 到这个已有浏览器/profile，不要新开无登录态的浏览器。
如果页面没有登录，请停下来让我手动登录；不要问我要 jAccount 密码。
登录后，只在 https://meeting.sjtu.edu.cn 这个 origin 中读取 user_info cookie，解析其中的 token 字段。
不要在聊天、日志、commit、issue 或最终回复中打印 token。
把 token 写入 ~/.config/sjtu-meeting/creds.json，权限设为 600，然后运行 `python3 scripts/sjtu_meeting.py whoami` 验证。
最终只告诉我验证是否成功，以及识别到的非敏感账号信息；不要回显 token。
```

agent 在浏览器页面上下文中执行的核心 JS：

```js
(() => {
  if (location.hostname !== "meeting.sjtu.edu.cn") {
    throw new Error(`wrong origin: ${location.origin}`);
  }
  const m = document.cookie.match(/(?:^|;\s*)user_info=([^;]+)/);
  if (!m) throw new Error("user_info cookie not found; log in to meeting.sjtu.edu.cn first");
  let o = JSON.parse(decodeURIComponent(m[1]));
  if (typeof o === "string") o = JSON.parse(o);
  if (!o.token) throw new Error("token not found in user_info cookie");
  return {
    token: o.token,
    profile: {
      name: o.name || "",
      user_id: o.user_id || "",
      email: o.email || "",
      allow_room_group: o.allow_room_group || []
    }
  };
})()
```

agent 只需要把返回对象里的 `token` 写入 `~/.config/sjtu-meeting/creds.json`；`profile` 只是用于本地核对，不应包含在公开日志里。

Agent 推荐执行清单：

1. 连接用户已有登录态的浏览器/profile。
2. 打开或定位到 `https://meeting.sjtu.edu.cn`。
3. 检查当前页面 origin，必须是 `https://meeting.sjtu.edu.cn`。
4. 如果页面跳到 SJTU SSO 或显示未登录，停下来让用户自己完成登录。
5. 用户登录完成后，回到 `meeting.sjtu.edu.cn` 页面。
6. 在该页面上下文执行上面的 cookie 解析 JS。
7. 只保留 `token` 字段；`name`、`user_id`、`email`、`allow_room_group` 只用于本地核对。
8. 创建 `~/.config/sjtu-meeting`，权限 `700`。
9. 写入 `~/.config/sjtu-meeting/creds.json`，权限 `600`。
10. 运行 `python3 scripts/sjtu_meeting.py whoami`。
11. 验证成功后只汇报成功和非敏感账号信息，不回显 token。

```json
{
  "user_token": "paste-token-here",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

验证：

```bash
chmod 600 ~/.config/sjtu-meeting/creds.json
python3 scripts/sjtu_meeting.py whoami
```

常见坑：

- agent 打开了全新无状态浏览器：这种浏览器没有用户登录态，通常拿不到 cookie。应 attach 到用户正在使用的浏览器/profile，或让用户在 agent 打开的浏览器里手动登录。
- 页面还停在 SJTU SSO：不要让 agent 输入账号密码，让用户自己完成登录。
- cookie 读不到：确认当前页面是 `https://meeting.sjtu.edu.cn`，并且登录后的会议平台页面已经加载完成。
- token 被打印到日志：有些浏览器 evaluate 工具会把返回值写进工具日志。高敏感场景下，改用手动控制台方式，或使用可信本地 agent。

安全边界：

- 只允许读取用户自己授权的、自己账号的已登录浏览器。
- 只读取 `meeting.sjtu.edu.cn` 这个 origin 的 `user_info` cookie。
- 不要读取他人浏览器、他人账号或未授权 profile。
- 不要向用户索要 jAccount 密码。
- 不要在聊天、日志、issue、commit、截图中公开 token。
- 不要把真实 `creds.json` 提交到仓库。

更详细的凭证设置、刷新和排障说明见 [docs/credential-setup.md](docs/credential-setup.md) 和 [docs/agent-cookie-capture.zh.md](docs/agent-cookie-capture.zh.md)。

## 安装和运行

推荐使用 `uv`：

```bash
uv run python3 scripts/sjtu_meeting.py whoami
```

或者在当前 Python 环境安装依赖：

```bash
uv pip install httpx
python3 scripts/sjtu_meeting.py whoami
```

运行依赖只有 `httpx`。

## 命令说明

### 验证凭据

```bash
python3 scripts/sjtu_meeting.py whoami
python3 scripts/sjtu_meeting.py whoami --json
```

### 列出会议

默认查询从今天起未来一年的会议：

```bash
python3 scripts/sjtu_meeting.py list
python3 scripts/sjtu_meeting.py list --from 2026-06-01 --to 2026-06-30
python3 scripts/sjtu_meeting.py list --search "seminar" --json
python3 scripts/sjtu_meeting.py list --all
```

### 获取会议详情

`id` 来自 `list` 命令返回的内部会议 ID：

```bash
python3 scripts/sjtu_meeting.py get 123456
python3 scripts/sjtu_meeting.py get 123456 --json
```

详情中会包含 `join_url`，即腾讯会议入会链接。

### 创建单个会议

```bash
python3 scripts/sjtu_meeting.py create \
  --topic "Weekly Seminar" \
  --date 2026-06-09 \
  --time 19:00 \
  --duration 3 \
  --group 14 \
  --cohost alice,bob
```

`duration` 支持小时或分钟：

- `3`
- `0.5`
- `90m`

开始时间必须是整点或半点，即 `HH:00` 或 `HH:30`。

### 批量创建会议

准备 `meetings.json`：

```json
[
  {"topic": "Weekly Seminar", "date": "2026-06-09", "time": "19:00", "duration": 3, "cohost": "alice,bob"},
  {"topic": "Weekly Seminar", "date": "2026-06-16", "time": "19:00", "duration": 3, "cohost": "alice,bob"}
]
```

运行：

```bash
python3 scripts/sjtu_meeting.py create --batch meetings.json --json
```

批量创建默认使用 4 个线程并发。

### 固定周会模板

编辑 `assets/recurring_meetings.json`，或用环境变量指定自己的模板：

```bash
export SJTU_MEETING_RECURRING=/path/to/recurring_meetings.json
```

先预览：

```bash
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --dry-run
```

确认清单后再真正创建：

```bash
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07
```

常用参数：

```bash
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --weeks 16
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --only WEEKLY_SEMINAR
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --all-templates
```

模板里的 weekday 编码是 `0 = 周日, 1 = 周一, ..., 6 = 周六`。

### 删除会议

删除不可逆。建议先 `list` 查出候选会议，确认 ID 后再删。

```bash
python3 scripts/sjtu_meeting.py delete 123456
python3 scripts/sjtu_meeting.py delete 123456 123457 --json
```

### 查询时段占用

```bash
python3 scripts/sjtu_meeting.py busy --date 2026-06-09 --duration 3 --group 14
python3 scripts/sjtu_meeting.py busy --date 2026-06-09 --json
```

### 查询日历视图

```bash
python3 scripts/sjtu_meeting.py calendar --view month --date 2026-06-01
python3 scripts/sjtu_meeting.py calendar --view week --date 2026-06-09
python3 scripts/sjtu_meeting.py calendar --view day --date 2026-06-09
```

日历接口结构较复杂，因此 CLI 始终输出 JSON。

## 实现方法

### API 形态

Base URL：

```text
https://meeting.sjtu.edu.cn/api/v1
```

主要接口使用：

```text
POST application/x-www-form-urlencoded
```

统一响应结构大致为：

```json
{
  "code": 200,
  "text": "OK",
  "success": true,
  "data": {}
}
```

CLI 以 `success: true` 作为成功判断。

### 已封装接口

| CLI 命令 | 后端接口 | 作用 |
|---|---|---|
| `whoami` | `/user/incomplete` | 轻量验证 token |
| `list` | `/meeting/list` | 查询会议列表 |
| `get` | `/meeting/get` | 获取会议详情和入会链接 |
| `create` | `/meeting/edit` | 创建会议，CLI 使用 `id=0` |
| `delete` | `/meeting/delete` | 删除会议 |
| `busy` | `/query/busy` | 查询半小时粒度的忙闲状态 |
| `calendar` | `/query/view/day`, `/query/view/week`, `/query/view/month` | 查询日历视图 |

### 创建结果解析

`meeting/edit` 创建会议后，返回值里不是直接给一个结构化 `join_url` 字段，而是返回一个 notice URL。CLI 会解析这个 URL：

- query 参数 `address`：腾讯会议入会链接。
- query 参数 `content`：包含会议号。

因此 `create` 命令创建完成后可以立刻打印会议号和入会链接。

### 列表默认时间范围

原始 `meeting/list` 接口可能返回很久以前的历史会议。CLI 默认限制为从今天起未来一年；需要历史会议时再显式传 `--all`。

## 安全边界

这个工具故意不封装下列接口：

- `meeting/mail/*`：会真实发送邮件。
- `admin/*`：管理员接口。
- `user/clear` 以及其他带清理、重建语义的接口。

agent 应该组合 CLI 暴露的原子命令，而不是绕过 CLI 直接调用危险接口。

安全注意：

- `user_token` 等同于该平台的会话凭据。
- 不要把真实 token 放进 issue、commit、截图、日志或聊天记录。
- 不要把真实凭据文件提交到仓库。
- 这个工具不需要 jAccount 密码；用户自己在浏览器登录即可。
- 批量创建会产生真实会议记录，运行前应先 dry-run 或人工确认。

## 仓库状态

这是一个经过去敏处理的公开版本。仓库中不包含私人 token、账号密码或真实私人会议模板。
