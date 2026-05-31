# SJTU Meeting Skill

用自然语言管理上海交通大学云视频会议平台 `meeting.sjtu.edu.cn`。

这个仓库的核心不是让用户手动运行一堆命令，而是提供一个 Agent Skill：用户只需要和自己的 agent 对话，例如“下周三晚上 7 点帮我建个组会”“把明天那个会的腾讯入会链接发我”，agent 会把自然语言请求翻译成后端 API 操作，并返回会议号、入会链接或确认清单。

## 能用自然语言做什么

你可以直接对 agent 说：

- “帮我看看接下来一周有哪些会议。”
- “下周三晚上 7 点建一个论文讨论会，开 2 小时，密码默认。”
- “明天下午 3 点约个项目同步会，拉 alice,bob 做联席主持。”
- “把 9 月开始连续 16 周的每周组会排上，先给我预览。”
- “我下一场会的腾讯会议链接和会议号发我。”
- “删掉 6 月 9 日晚上那个测试会，先列出来让我确认。”
- “查一下 6 月 12 日 300 人会议室组哪些时段空。”
- “把这个月所有 seminar 会议列出来。”

agent 会负责：

- 理解相对日期和时间，例如“下周三”“明天下午”“这学期每周二”。
- 检查平台约束，例如开始时间必须是整点或半点。
- 创建会议后直接返回腾讯会议入会链接和会议号。
- 批量创建前先 dry-run 给用户确认。
- 删除前先列出候选会议 ID 和时间，避免误删。
- 查询会议列表、详情、占用时段和日历视图。

## 为什么需要这个 Skill

网页 UI 适合人工创建单个会议，但对 agent 自动化不够稳定：

- 浏览器表单自动化慢，容易受 UI 改版影响。
- 一学期固定会议通常需要批量创建，手工重复成本高。
- 创建接口本身会返回腾讯会议入会链接，不必逐个打开详情页复制。
- agent 更适合把自然语言请求拆成可确认的原子操作。

这个 skill 的内部实现是直接调用 `meeting.sjtu.edu.cn` 后端 API，不依赖腾讯会议 MCP，也不模拟浏览器表单。用户日常使用时不需要关心 Python 命令；这些命令只是 agent 的执行后端。

## 仓库结构

- `SKILL.md`：给 agent 读取的 skill 说明，定义何时触发、如何把自然语言请求映射到操作。
- `scripts/sjtu_meeting.py`：agent 内部使用的 Python CLI 后端。
- `docs/agent-cookie-capture.zh.md`：用户自己的 agent 如何从已登录浏览器安全抓取 token。
- `docs/credential-setup.md`：凭证、登录态、刷新和排障说明。
- `docs/cli-reference.zh.md`：CLI 命令参考，主要给 agent/维护者调试用。
- `references/api.md`：后端 API 逆向说明。
- `assets/recurring_meetings.json`：公开示例 recurring 会议模板。
- `examples/creds.example.json`：凭据文件示例，不包含真实 token。

## 登录态和安全模型

这个工具不需要用户把 jAccount 账号密码交给 agent。

推荐流程是：

1. 用户自己在浏览器打开 `https://meeting.sjtu.edu.cn`。
2. 用户自己完成学校官方 SSO 登录。
3. 用户授权自己的 agent 访问这个已登录浏览器的页面上下文。
4. agent 只读取 `meeting.sjtu.edu.cn` 这个 origin 的 `user_info` cookie。
5. agent 只保存其中的 `token` 字段到本机凭据文件。
6. agent 用该 token 调用会议平台 API。

这种方式的安全边界比较清楚：

- 不保存、不传输、不代填 jAccount 账号密码。
- 用户始终在学校官方 SSO 页面自己登录。
- agent 只是复用用户已经登录好的浏览器会话。
- token 保存在用户本机，建议文件权限为 `600`。
- token 是会话型凭据，不是账号密码。
- token 过期后没有额外问题，用户重新登录 `meeting.sjtu.edu.cn`，agent 再抓一次 token 即可。
- 本地凭据文件可以随时删除，相当于撤销这个工具在本机的访问能力。

真正需要保护的是 token 本身：不要把它打印到聊天、日志、issue、commit、截图或公开文档里。

## 给用户复制给 Agent 的提示词

如果你的 agent 已经能访问浏览器，例如 Browser Use、Computer Use、Chrome/Edge DevTools、Playwright MCP、浏览器调试端口或类似插件，可以直接对 agent 说：

```text
我已经在本机浏览器登录 https://meeting.sjtu.edu.cn，并允许你访问这个已登录浏览器的页面上下文。
请 attach 到这个已有浏览器/profile，不要新开无登录态的浏览器。
如果页面没有登录，请停下来让我手动登录；不要问我要 jAccount 密码。
登录后，只在 https://meeting.sjtu.edu.cn 这个 origin 中读取 user_info cookie，解析其中的 token 字段。
不要在聊天、日志、commit、issue 或最终回复中打印 token。
把 token 写入 ~/.config/sjtu-meeting/creds.json，权限设为 600，然后验证会议 API 是否可用。
最终只告诉我验证是否成功，以及识别到的非敏感账号信息；不要回显 token。
```

agent 的执行原则：

- 必须 attach 到用户已有登录态的浏览器/profile；新开的无状态浏览器通常没有 cookie。
- 只在 `meeting.sjtu.edu.cn` 页面上下文读取 `user_info` cookie。
- 如果还在 SSO 登录页，停下来让用户自己登录，不要索要密码。
- 写入本地凭据文件后，只汇报验证结果，不回显 token。

详细的浏览器 token 抓取流程见 [docs/agent-cookie-capture.zh.md](docs/agent-cookie-capture.zh.md)。

## Agent 如何使用这个 Skill

面向 agent 的入口是 [SKILL.md](SKILL.md)。

agent 看到用户要求在 SJTU 云视频会议平台上创建、查询、删除或批量安排会议时，应触发这个 skill。典型流程是：

1. 解析用户自然语言，确定操作类型、日期、时间、时长、主题、会议室组、联席主持人等。
2. 如果是批量创建或删除，先生成清单让用户确认。
3. 调用内部 CLI/API 完成操作。
4. 返回用户真正关心的结果，例如会议号、腾讯入会链接、创建成功数、删除结果或占用时段。

用户不需要阅读 CLI 参数。CLI 命令参考保留在 [docs/cli-reference.zh.md](docs/cli-reference.zh.md)，用于维护、调试或扩展 skill。

## 安全边界

这个工具故意不封装以下危险接口：

- `meeting/mail/*`：会真实发送邮件。
- `admin/*`：管理员接口。
- `user/clear` 以及其他带清理、重建语义的接口。

删除会议不可逆，所以 agent 必须先列出候选会议并让用户确认。批量创建会产生真实会议记录，所以也应先预览清单。

## 当前状态

这是一个经过去敏处理的公开版本。仓库中不包含私人 token、账号密码或真实私人会议模板。
