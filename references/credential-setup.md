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

## Method 1: One-Command Local Setup

This is the easiest route for most collaborators. It does not require a browser plugin, Playwright, MCP, or copying cookies by hand.

From the repository root:

```bash
python3 scripts/setup_chrome_token.py
```

What happens:

1. The script first tries existing local DevTools ports such as `127.0.0.1:9222`, `9223`, and `9224`.
2. If an existing Chrome/Edge session is reachable and already logged in to `meeting.sjtu.edu.cn`, the script reuses that session.
3. If no usable existing session is found, the script opens a dedicated local Chrome/Edge profile with DevTools enabled on `127.0.0.1`.
4. You complete the official SJTU SSO login in that browser window.
5. The script waits until `meeting.sjtu.edu.cn` is loaded.
6. The script reads only the `user_info` cookie from that origin, extracts only `token`, and does not print it.
7. The script writes `~/.config/sjtu-meeting/creds.json` with mode `600`.
8. The script verifies the token against the meeting API.

Useful options:

```bash
python3 scripts/setup_chrome_token.py --browser chrome
python3 scripts/setup_chrome_token.py --browser edge
python3 scripts/setup_chrome_token.py --timeout 300
python3 scripts/setup_chrome_token.py --creds /path/to/creds.json
python3 scripts/setup_chrome_token.py --skip-existing
```

If you already started Chrome/Edge with a local DevTools port, you can attach instead of launching a new browser:

```bash
python3 scripts/setup_chrome_token.py --attach-port 9222
```

The default launched browser uses a dedicated profile at `~/.config/sjtu-meeting/browser-profile`, so it does not need to control or modify your everyday Chrome profile.

## Fallback Policy

Credential setup has a strict fallback order:

1. Run `python3 scripts/setup_chrome_token.py`.
2. Let it try an already-open logged-in Chrome/Edge session through local DevTools ports.
3. If that fails, finish login in the dedicated browser window opened by the script, return to `meeting.sjtu.edu.cn`, and refresh once.
4. If the script still cannot read `user_info` or API verification fails, stop the automatic setup path.
5. Use the manual DevTools method below.

Do not fall back to controlling the meeting website UI to create, list, or delete meetings one by one. This skill's runtime path is the API CLI after credentials are valid. If credentials are not valid, the correct next step is credential setup, not UI automation.

## Method 2: Manual DevTools Cookie Copy

1. Open `https://meeting.sjtu.edu.cn`.
2. Complete the official SJTU SSO login in your browser.
3. After the meeting page loads, open browser developer tools:
   - macOS: `Cmd+Option+I`
   - Windows/Linux: `F12` or `Ctrl+Shift+I`
4. Preferred path:
   - Open the `Application` tab.
   - In the left sidebar, open `Storage` > `Cookies` > `https://meeting.sjtu.edu.cn`.
   - Find the cookie named `user_info`.
   - Copy its `Value`.
5. If the `Application` tab is hard to find, use `Network` instead:
   - Open the `Network` tab.
   - Refresh the meeting page.
   - Click a request under `meeting.sjtu.edu.cn/api/v1`, for example `user/incomplete`.
   - Open `Headers` > `Request Headers`.
   - Copy the `user_info=...` part from the `Cookie` header. Copying the full `Cookie` header is also acceptable.
6. Create or edit `~/.config/sjtu-meeting/creds.json` and paste the copied value into `user_info_cookie`:

```json
{
  "user_info_cookie": "PASTE_USER_INFO_COOKIE_VALUE_HERE",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

The CLI will parse `user_info_cookie` locally and extract the token at runtime. Do not paste the cookie into chat, issues, commits, screenshots, or public logs.

7. Save the file, then tell your agent:

```text
I pasted user_info_cookie into ~/.config/sjtu-meeting/creds.json.
Please verify the SJTU meeting credential.
```

## Method 3: Agent-Assisted Setup

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
- the runtime tries to switch to website UI operations instead of obtaining a valid token.

## Method 4: Environment Variable

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

1. Run `python3 scripts/setup_chrome_token.py` again.
2. Complete login in the opened browser window if required.
3. Let the script overwrite `user_token` in the local credential file.
4. Run `python3 scripts/sjtu_meeting.py whoami` if you want a separate check.

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

- Use `python3 scripts/setup_chrome_token.py`.
- Or use manual browser-console extraction.
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
