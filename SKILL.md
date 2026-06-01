---
name: sjtu-meeting
description: >
  Manage meetings on Shanghai Jiao Tong University's meeting.sjtu.edu.cn platform from natural language.
  Use when the user wants to list, create, batch-create, inspect, delete, or check availability for their own
  SJTU cloud video meetings. Returns Tencent Meeting join URLs and meeting numbers without using the web UI.
---

# SJTU Meeting

Use this skill when the user asks to manage their own meetings on `meeting.sjtu.edu.cn`.

Do not use it for Tencent Meeting recordings/transcripts, meeting minutes, Feishu/Lark calendar events, Zoom, Tencent client settings, slide generation, email notifications, or public lecture lookup.

## Natural Language Routing

Map user requests to these operations:

| User intent | Operation |
|---|---|
| “我有哪些会 / 下一场会 / 会议号” | list meetings |
| “把入会链接发我 / 查详情” | get meeting detail |
| “建个会 / 约个会” | create one meeting |
| “排这学期周会 / 批量建固定会议” | preview recurring or batch create |
| “删掉那个会” | list candidates, confirm, then delete |
| “这个时间空不空” | check busy slots |
| “看日历 / 本周本月会议” | calendar view |

Return what the user cares about: meeting time, topic, internal ID when needed, Tencent join URL, meeting number, password, status, and confirmation/result summaries.

## Workflow Rules

- Convert relative dates such as “明天”, “下周三”, and “这学期每周二” to concrete dates before calling the backend.
- Meeting start minutes must be `00` or `30`. If the user gives an invalid time, ask or round only with explicit confirmation.
- For batch creation or recurring meetings, dry-run or show the generated schedule before creating real records.
- Deletion is irreversible. Always list candidate meetings and ask for confirmation before deleting.
- If the user asks for the next meeting link, list near-future meetings first, choose the relevant meeting, then get details.
- If credentials are missing, expired, or unverifiable, stop and complete credential setup first. Do not fall back to controlling the meeting website UI to create/list/delete meetings one by one.

## Credentials

The backend uses a single `user_token` saved outside the repository. The agent should not ask for the user's jAccount password.

For first-time setup:

1. Prefer the local helper: `python3 scripts/setup_chrome_token.py`.
2. The helper first tries already-open local DevTools ports such as `127.0.0.1:9222` to reuse an existing logged-in Chrome/Edge session.
3. If no usable existing browser session is found, the helper opens a dedicated Chrome/Edge profile and asks the user to complete normal SJTU SSO login there.
4. Let the helper read only the `user_info` cookie from `meeting.sjtu.edu.cn`, extract only `token`, write the credential file with permission `600`, and verify the API.
5. If automation still cannot read the cookie or verify the token, stop the setup attempt. Do not continue by driving the website UI for meeting operations.
6. Offer the manual DevTools fallback in `references/credential-setup.md`: the user opens DevTools, finds `user_info` in Application > Cookies or Network > Request Headers, then either pastes that value into the local agent chat or writes it into `user_info_cookie` in `~/.config/sjtu-meeting/creds.json`.
7. Never print the token.

If the user pastes a `user_info` cookie into chat, treat it as a secret. Do not echo it. Import it through stdin, not a command-line argument:

```bash
python3 scripts/sjtu_meeting.py import-cookie
```

Then send the pasted value to stdin, verify the result, and report only success/failure plus non-sensitive account metadata.

Read `references/agent-cookie-capture.zh.md` or `references/credential-setup.md` when setting up or refreshing credentials.

## References

- `references/cli-reference.zh.md`: CLI commands and examples for agent execution/debugging.
- `references/api.md`: backend API payloads, responses, wrapped endpoints, and intentionally unwrapped risky endpoints.
- `references/agent-cookie-capture.zh.md`: detailed Chinese guide for browser-capable agents to capture the logged-in token.
- `references/credential-setup.md`: credential model, refresh, troubleshooting, and security notes.
- `scripts/setup_chrome_token.py`: easiest first-time credential setup; launches local Chrome/Edge and writes creds without printing the token.

## Safety

- Never ask for or store the user's jAccount password.
- Never print `user_token` in chat, logs, commits, issues, screenshots, or final answers.
- Do not call `meeting/mail/*`, `admin/*`, `user/clear`, or other risky routes directly.
- Use the exposed CLI/backend operations rather than inventing raw API calls unless extending the skill deliberately.
