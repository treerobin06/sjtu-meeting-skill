# Agent 自动抓取已登录浏览器 Token 指南

这份文档写给“用户自己的 agent”。目标是：用户已经在本机浏览器登录了 `meeting.sjtu.edu.cn`，agent 在用户授权下读取这个已登录状态里的 `user_info` cookie，提取 `token`，写入本地凭据文件，从而不需要用户把 jAccount 密码交给 agent。

## 一句话流程

用户自己登录浏览器；agent attach 到这个已有登录态；agent 只在 `meeting.sjtu.edu.cn` 页面上下文读取 `user_info` cookie；agent 提取 `token` 并写入 `~/.config/sjtu-meeting/creds.json`；agent 运行 `whoami` 验证；agent 不回显 token。

## 前提条件

- 用户本机已经安装浏览器。
- 用户的 agent 可以访问浏览器，例如通过 Browser Use、Computer Use、Chrome/Edge DevTools、Playwright MCP、浏览器调试端口或其他等价插件。
- agent 能够 attach 到用户已有登录态的浏览器/profile。注意：如果 agent 打开的是一个全新的无状态浏览器，就没有用户登录态，也就拿不到 cookie。
- 用户已经登录 `https://meeting.sjtu.edu.cn`，或者愿意在 agent 提示时手动登录。

## 给用户的提示

用户可以对 agent 说：

```text
我已经在本机浏览器登录 https://meeting.sjtu.edu.cn，并允许你访问这个已登录浏览器的页面上下文。
请 attach 到这个已有浏览器/profile，不要新开无登录态的浏览器。
如果页面没有登录，请停下来让我手动登录；不要问我要 jAccount 密码。
登录后，只在 https://meeting.sjtu.edu.cn 这个 origin 中读取 user_info cookie，解析其中的 token 字段。
不要在聊天、日志、commit、issue 或最终回复中打印 token。
把 token 写入 ~/.config/sjtu-meeting/creds.json，权限设为 600，然后运行 `python3 scripts/sjtu_meeting.py whoami` 验证。
最终只告诉我验证是否成功，以及识别到的非敏感账号信息；不要回显 token。
```

## Agent 执行清单

1. 连接用户已有登录态的浏览器/profile。
2. 打开或定位到 `https://meeting.sjtu.edu.cn`。
3. 检查当前页面 origin，必须是 `https://meeting.sjtu.edu.cn`。
4. 如果页面跳到 SJTU SSO 或显示未登录，停下来让用户自己完成登录。
5. 用户登录完成后，回到 `meeting.sjtu.edu.cn` 页面。
6. 在该页面上下文执行 cookie 解析 JS。
7. 只保留 `token` 字段；可以本地读取 `name`、`user_id`、`email`、`allow_room_group` 用于核对，但不要公开打印 token。
8. 创建 `~/.config/sjtu-meeting`，权限 `700`。
9. 写入 `~/.config/sjtu-meeting/creds.json`，权限 `600`。
10. 运行 `python3 scripts/sjtu_meeting.py whoami`。
11. 如果验证成功，只汇报“已验证”；如果失败，让用户重新登录并刷新 token。

## 页面上下文 JS

agent 应该在 `meeting.sjtu.edu.cn` 页面上下文执行下面的 JS。不要在其他网站 origin 上执行。

```js
(() => {
  if (location.hostname !== "meeting.sjtu.edu.cn") {
    throw new Error(`wrong origin: ${location.origin}`);
  }

  const m = document.cookie.match(/(?:^|;\s*)user_info=([^;]+)/);
  if (!m) {
    throw new Error("user_info cookie not found; log in to meeting.sjtu.edu.cn first");
  }

  let info = JSON.parse(decodeURIComponent(m[1]));
  if (typeof info === "string") {
    info = JSON.parse(info);
  }

  if (!info.token) {
    throw new Error("token not found in user_info cookie");
  }

  return {
    token: info.token,
    profile: {
      name: info.name || "",
      user_id: info.user_id || "",
      email: info.email || "",
      allow_room_group: info.allow_room_group || []
    }
  };
})()
```

`token` 是真正的会话凭据。`profile` 只用于本地核对，不是必需字段。

## 写入凭据文件

agent 拿到 token 后，写入：

```text
~/.config/sjtu-meeting/creds.json
```

文件内容：

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

注意：不要把 token 放进命令行参数里传给 shell，因为命令行参数可能进入 shell history、process list 或 agent 日志。更稳妥的做法是让 agent 直接写本地 JSON 文件，并避免在最终回复中展示文件完整内容。

## 验证

```bash
python3 scripts/sjtu_meeting.py whoami
```

成功时说明 token 有效。失败时通常有三类原因：

- 浏览器没有登录，`user_info` cookie 不存在。
- agent attach 到了无登录态的新浏览器/profile。
- token 已过期，需要用户重新登录后再抓一次。

## 常见坑

### agent 打开了新浏览器

新浏览器通常没有用户登录态。应改为 attach 到用户正在使用的浏览器/profile，或让用户在 agent 打开的浏览器里手动登录。

### 页面还在 SSO 登录页

不要让 agent 输入账号密码。让用户自己完成登录，然后 agent 再继续读取 `meeting.sjtu.edu.cn` 页面里的 cookie。

### cookie 读不到

确认当前页面确实是 `https://meeting.sjtu.edu.cn`，并且登录后的会议平台页面已经加载完成。必要时刷新页面。

### token 被打印到日志

不同 agent runtime 的浏览器 evaluate 工具可能会把返回值写进工具日志。高敏感场景下，用户应改用手动控制台方式，或者使用自己信任的本地 agent，并确认日志不会公开上传。

## 安全边界

允许：

- 用户授权自己的 agent 读取自己的已登录浏览器。
- agent 只读取 `meeting.sjtu.edu.cn` 的 `user_info` cookie。
- agent 把 token 写入本地受限权限文件。
- agent 用 `whoami` 验证 token。

禁止：

- 读取他人浏览器、他人账号或未授权 profile。
- 向用户索要 jAccount 密码。
- 在聊天、日志、issue、commit、截图中公开 token。
- 把真实 `creds.json` 提交到仓库。
