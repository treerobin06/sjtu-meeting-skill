# Credential Setup

This project uses the logged-in browser session from `meeting.sjtu.edu.cn` to obtain one API credential: `user_token`.

The safe model is:

- The user logs in themselves through the official SJTU SSO page.
- The agent reads only the meeting site's own `user_info` cookie after the user has consented.
- The agent stores only the `token` field in a local credential file.
- The agent never asks for, stores, or prints the user's account password.

Do not use this workflow on someone else's account, browser profile, or machine without explicit consent.

Why this is safer than storing a password:

- The user's account password is never given to the agent.
- Login still happens through the official SJTU SSO page in the user's browser.
- The saved value is a session-like API token, not the account password.
- If the token expires, the user logs in again and the agent refreshes the token. No password reset or account change is involved.
- The local credential file can be deleted at any time to revoke this tool's local access.

The main thing to protect is the token itself. Do not print it in chats, logs, issues, commits, or screenshots.

## What The Token Is

After login, `meeting.sjtu.edu.cn` sets a `user_info` cookie. In the observed web app, this cookie is not `HttpOnly`, so JavaScript running on the meeting site can read it. The cookie contains encoded JSON with fields such as:

```json
{
  "name": "...",
  "token": "...",
  "email": "...",
  "user_id": "...",
  "allow_room_group": [14, 11]
}
```

The CLI needs only `token`. It sends that value as:

- `user-token` HTTP header
- `user_token` form body field

No browser cookies are required after the token has been saved locally.

The token can expire with the browser session or server-side session policy. That is expected. When it expires, simply log in to `meeting.sjtu.edu.cn` again and repeat the extraction step.

## Credential File

Default path:

```text
~/.config/sjtu-meeting/creds.json
```

Override path:

```bash
export SJTU_MEETING_CREDS=/path/to/creds.json
```

Recommended permissions:

```bash
mkdir -p ~/.config/sjtu-meeting
chmod 700 ~/.config/sjtu-meeting
chmod 600 ~/.config/sjtu-meeting/creds.json
```

File shape:

```json
{
  "user_token": "paste-token-here",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

Optional metadata can be included for local convenience:

```json
{
  "user_token": "paste-token-here",
  "name": "Your Name",
  "user_id": "your-jaccount",
  "email": "your-jaccount@sjtu.edu.cn",
  "allow_room_group": [14, 11],
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

Never commit this file.

## Method 1: Manual Browser Console

1. Open `https://meeting.sjtu.edu.cn`.
2. Complete the official SJTU SSO login in your browser.
3. Open browser developer tools on the meeting site.
4. Run this snippet in the console:

```js
(() => {
  const m = document.cookie.match(/(?:^|;\s*)user_info=([^;]+)/);
  if (!m) throw new Error("user_info cookie not found; log in to meeting.sjtu.edu.cn first");
  let o = JSON.parse(decodeURIComponent(m[1]));
  if (typeof o === "string") o = JSON.parse(o);
  return o.token;
})()
```

5. Put the returned token into `~/.config/sjtu-meeting/creds.json`.
6. Verify:

```bash
python3 scripts/sjtu_meeting.py whoami
```

## Method 2: Agent-Assisted Setup

Use this when the user's coding agent can inspect or automate the user's already logged-in browser. The agent should not receive the password.

For a more detailed Chinese guide written directly for browser-capable agents, see [agent-cookie-capture.zh.md](agent-cookie-capture.zh.md).

User steps:

1. Open `https://meeting.sjtu.edu.cn`.
2. Log in manually.
3. Tell the agent it may read the meeting site's `user_info` cookie.

Prompt template:

```text
I am logged in to https://meeting.sjtu.edu.cn in my local browser. Extract only the token field from the user_info cookie for this origin. Do not ask for my password. Do not print the token in chat or logs. Write it to ~/.config/sjtu-meeting/creds.json with chmod 600, then run `python3 scripts/sjtu_meeting.py whoami` to verify it.
```

Agent behavior:

1. Attach to the user's logged-in browser or use the browser automation tool provided by the runtime.
2. Ensure the active page is `https://meeting.sjtu.edu.cn`, not a different origin.
3. Evaluate the cookie-decoding JavaScript in that page context.
4. Extract only `o.token`.
5. Create the credential directory with mode `700`.
6. Write the credential JSON with mode `600`.
7. Run `whoami`.
8. Report only whether verification succeeded. Do not echo the token.

The agent should stop and ask the user to log in manually if:

- `user_info` is missing.
- the page is not on `meeting.sjtu.edu.cn`.
- the browser automation runtime cannot access the logged-in browser profile.
- `whoami` reports an authentication failure.

## Method 3: Environment Variable

For one-off use without writing a file:

```bash
export SJTU_MEETING_TOKEN="paste-token-here"
python3 scripts/sjtu_meeting.py whoami
```

This is convenient for short-lived shells, but a credential file is better for repeated agent use.

## Token Refresh

The token is session-like. It can expire when the browser login expires or the server invalidates the session.

Refresh when:

- `whoami` fails.
- API calls return `401` or `403`.
- API responses have `success: false` with authentication-related text.

Refresh process:

1. Reopen `https://meeting.sjtu.edu.cn`.
2. Log in again if required.
3. Re-extract the token.
4. Replace `user_token` in the local credential file.
5. Run `whoami`.

## Troubleshooting

`user_info cookie not found`

- Confirm the browser is on `https://meeting.sjtu.edu.cn`.
- Refresh after login.
- Avoid private/incognito windows unless the agent can access that same profile.
- Confirm login completed and the meeting app UI loaded.

`whoami` fails after writing the token

- The token may have been copied with extra quotes or whitespace.
- The token may already be expired.
- Confirm the credential file path. The CLI uses `~/.config/sjtu-meeting/creds.json` unless `SJTU_MEETING_CREDS` is set.

Agent cannot access the browser

- Use manual browser-console extraction.
- Or configure the agent's approved browser automation tool to attach to the user's logged-in browser.
- Do not give the agent your account password as a workaround.

## Security Boundary

Allowed:

- The user authorizes their own agent to read their own logged-in browser session.
- The token is stored locally with restrictive permissions.
- The agent verifies the token without printing it.

Not allowed:

- Extracting credentials from another user's browser without consent.
- Asking for or storing the user's jAccount password.
- Publishing tokens in logs, commits, issues, screenshots, or chat transcripts.
- Bundling real credential files or private meeting templates in this repository.
