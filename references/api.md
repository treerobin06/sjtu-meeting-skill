# SJTU 云视频会议系统 · 接口逆向文档

> 逆向于 2026-05-30，针对 `meeting.sjtu.edu.cn`（Vue 前端 + PHP8/Laravel 后端）。
> 前端构建时间 `20240414`。所有结论均经真实请求验证。

## 认证机制（关键）

- **Base URL**：`https://meeting.sjtu.edu.cn/api/v1`
- **唯一凭据**：`user_token` 一个字符串。**实测：只带 `user-token` header（无 cookie）即可调用返回私有数据的接口**，所以 Python 直连只需这一个 token，不需要 session cookie。
- token 同时放在 **请求头 `user-token`** 和 **body 字段 `user_token`**（两者都带最稳）。
- **token 来源**：浏览器 `user_info` cookie（非 HttpOnly）解析出的 JSON 的 `token` 字段。
  `user_info` 是双重编码的 JSON，含 `{name, token, email, user_id, role_level, allow_room_group, ...}`。
- **格式**：`POST`，`Content-Type: application/x-www-form-urlencoded`。
- **统一响应**：`{"code":200, "text":"OK", "success":true, "data":...}`。判成功看 `success`。
- 后端 `Access-Control-Allow-Origin: *`，不校验 Origin/Referer，所以裸 httpx 可直连。
- 有 `X-RateLimit-*`，但**实测并发 4 创建零限流**，4 个会议总耗时≈1 个（后端真并行）。

### token 刷新（过期时）

token 会随登录态过期。重抓：用 edge-devtools 在登录态 Edge（:9222）打开的 meeting 站执行：
```js
() => { const m = document.cookie.match(/(?:^|;\s*)user_info=([^;]+)/); let o = JSON.parse(decodeURIComponent(m[1])); if (typeof o === 'string') o = JSON.parse(o); return o.token; }
```
写回本地凭据文件（默认 `~/.config/sjtu-meeting/creds.json`）的 `user_token`。

面向公开使用时，推荐把这一步表述为“用户自己在本机浏览器完成登录，agent 只在该用户授权的浏览器上下文里读取 `meeting.sjtu.edu.cn` 这个 origin 的 `user_info` cookie”。不要让 agent 索要 jAccount 密码，也不要在聊天、日志、issue 或 commit 中打印 token。

---

## 核心接口（CLI 已封装，均实测验证）

### `meeting/edit` — 创建 / 编辑会议
`id=0` 新建，`id≠0` 编辑已有。`Content-Type` urlencoded。

完整 payload（变量 + 固定字段）：
```
topic=Weekly Seminar         # 主题
meeting_date=2026-06-09      # YYYY-MM-DD
meeting_time=19:00           # HH:MM —— 分钟必须 00 或 30！
duration=180                 # 分钟（3小时=180）
group_id=14                  # 会议室组
password=000000              # 6 位
assistants=alice,bob         # 联席主持 jAccount，逗号分隔；无则空
usage=办公  size=100  id=0  ask=1  quite=true  attendees=[]
option_mute=1 option_jbh=1 option_h323=0 auto_record=0 assistant=
option_enroll=0 enroll_attendees= option_water_mark=0 option_sso_only=0
meeting_guests= waiting_room=0 option_interpreter=0 option_live=0
```

响应（`data.data` 是个 notice URL，从 query 提取链接和会议号）：
```json
{"success":true,"data":{"message":"CREATED",
  "data":"https://notice.sjtu.edu.cn/ui/notice/create?...&address=https://meeting.tencent.com/dm/XXXX&...&content=会议号码：988757389%0D%0A参会密码为：000000..."}}
```
- `address` = 腾讯入会链接；`content` 里 `会议号码：` 后是会议号。
- ⚠️ 响应**不含系统内部 id**，要拿 id 得随后 `meeting/list` 按主题/会议号匹配。

### `meeting/list` — 我的会议列表（分页）
payload：`search`(主题模糊)、`page`、`page_size`、`use_date_range`(0/1)、`date_range[0]`/`date_range[1]`(`YYYY-MM-DD HH:MM`)。
- `use_date_range=0` 时返回全部（按时间正序，最早在前，会出现多年前的）。
- CLI 默认 `use_date_range=1` 限未来一年，避免翻出 2023 的老会议。

响应 `data.data[]` 每条：`id, start_time, duration_hour, topic, host_name, usage, room_group, approve_status(含HTML), zoom_info("会议号:xxx<br>密码:xxx"), should_not_edit`。

### `meeting/get` — 单会议详情
payload：`id`。响应 `data.data` 含编辑回填全字段，**且有 `join_url`(腾讯 dm 链接) 和 `streaming`(直播链接)**。
→ 任何会议（含别处创建的）都能 API 拿到完整入会链接，无需打开 UI。

### `meeting/delete` — 删除
payload：`id`。响应 `{success:true, data:null}`。不可逆。

### `query/busy` — 时段占用
payload：`start_date`(YYYY-MM-DD)、`id=0`、`duration`(分钟)、`h323=false`、`group_id`。
响应 `data.states` = `{"09:00":"空", "09:30":"忙", ...}` 每半小时一格。

### `query/view/day|week|month` — 会议日历
payload：`date`。month 返回 `{ "YYYY-MM-DD": {date, inactive, books}, ... }`。day 返回 `{books, tencent[], welink}`。

### `user/incomplete` — 待办数
返回一个数字（如 `15`）。CLI `whoami` 用它顺带验证 token。

### `user/preset` — 账户配置（GET）
返回 `room_groups`(id+名称)、`usages`、`max_hours`(24)、`create_meeting_forbidden`、`org_code` 等。
会议室组映射来自这里。

---

## 会议室组 group_id

| id | 名称 | 说明 |
|----|------|------|
| 14 | 腾讯会议（50人） | 默认 |
| 11 | 腾讯会议（300人） | |
| 12 | 腾讯会议（2000人） | 需审核 |
| 13 | 腾讯会议2026（300人） | |

`usages` 当前只有「办公」；单会议最长 24 小时。

---

## 硬约束汇总

1. **开始时间分钟只能 `00` 或 `30`**（否则后端报"时间只能是 00 和 30分钟"）。
2. **duration 单位是分钟**（前端下拉 0.5~4 小时 = 30~240 分钟，30 的倍数）。
3. 认证只认 `user_token`（header 或 body 均可）。
4. 并发安全（实测并发 4 零限流，可更高）。

---

## ⚠️ 危险 / 未封装接口（逆向到路径但 CLI 故意不暴露）

- `meeting/mail/attendee`、`meeting/mail/host` — **会真发邮件**给参会者/主持人。
- `query/rebuild/attendee`、`user/clear` — 含写/清除语义。
- `admin/*`（`admin/meeting/create|import`、`admin/approve/*`、`admin/user-approve/*`、
  `admin/lock`、`admin/delay`、`admin/batch`、`admin/visitor/all/uid` …）— 管理员功能，
  普通账号（role_level=0）大概率 403。
- 报表类（只读，未封装）：`report/statistic/get|download`、`report/meeting/detail/list`、
  `report/meeting/lock/list`、`report/survey/get|download`。
- 其他：`query/meeting/search`(主题联想 `[{id,label}]`)、`query/host`、`query/emails`、
  `announcement/newest`、`user/get|profile|remind|token`、`sso/login`。

需要时可按上面的认证方式自行扩展 CLI。

---

## 完整路由表（从前端 bundle 提取）

```
Meeting:   list, delete, edit, get, host, mail/{attendee,host}
Query:     busy, emails, host, meeting/search, rebuild/attendee, view/{day,week,month}
User:      preset, incomplete, get, profile, login, sso, remind, token, clear, sufe/wechat, wx/corp
Report:    statistic/{get,download}, survey/{get,download}, meeting/detail/list, meeting/lock/list
Announcement: newest
Admin:     meeting/{create,import}, approve/{list,approve,get}, user-approve/{list,get,approve},
           visitor/all/uid, announcement, disclaimer, survey, university, delay, lock, batch
SSO:       login
```
