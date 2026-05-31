# SJTU Meeting Skill

Agent skill and Python CLI for managing meetings on Shanghai Jiao Tong University's cloud video meeting platform, `meeting.sjtu.edu.cn`.

The project was built from a working reverse-engineering pass on the SJTU meeting web app. Instead of driving the browser UI, it calls the backend API directly and exposes safe, atomic commands that an agent can compose.

## What It Can Do

- List your future or historical meeting reservations.
- Get a meeting's full detail, including Tencent Meeting join URL, meeting number, password, host, cohosts, and streaming URL if present.
- Create a single meeting with topic, date, time, duration, room group, password, and cohosts.
- Batch-create meetings from JSON with concurrency.
- Expand weekly recurring meeting templates with a dry-run preview.
- Delete one or more meetings by internal ID.
- Query room-group busy slots for a day.
- Query day, week, or month calendar views.
- Validate whether the current token still works.

## Why This Exists

The web UI is usable for one meeting, but brittle for agent automation:

- Browser form automation is slower and more failure-prone.
- Creating a batch of weekly meetings manually is repetitive.
- The join link is available from API responses, so opening every detail page is unnecessary.
- Agents need structured JSON output and clear safety boundaries.

This repository packages the workflow as:

- `scripts/sjtu_meeting.py`: the Python CLI.
- `SKILL.md`: agent-facing routing and usage instructions.
- `references/api.md`: notes on the backend API, payloads, responses, and safety boundaries.
- `docs/credential-setup.md`: detailed credential and logged-in browser setup guide.
- `assets/recurring_meetings.json`: a public example recurring-meeting template.
- `examples/creds.example.json`: a credential-file shape with no real secret.

## Authentication Model

The backend accepts a single `user_token`. In observed behavior, private API calls work when this token is sent without browser cookies.

The CLI sends the token in two places:

- HTTP header: `user-token: <token>`
- Form body field: `user_token=<token>`

The token comes from the logged-in browser's `user_info` cookie on `meeting.sjtu.edu.cn`. This repository does not contain a password, cookie, or real token.

Credential lookup order:

1. `--token`
2. `SJTU_MEETING_TOKEN`
3. credential JSON file

Default credential file:

```text
~/.config/sjtu-meeting/creds.json
```

Override the path:

```bash
export SJTU_MEETING_CREDS=/path/to/creds.json
```

Minimal credential file:

```json
{
  "user_token": "paste-token-here",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

Recommended permissions:

```bash
mkdir -p ~/.config/sjtu-meeting
chmod 700 ~/.config/sjtu-meeting
chmod 600 ~/.config/sjtu-meeting/creds.json
```

## Credential Setup For Agents

The recommended workflow is consent-based and password-free:

1. The user opens `https://meeting.sjtu.edu.cn` in their own browser.
2. The user logs in through the normal SJTU SSO flow.
3. The agent reads only the `user_info` cookie from that same origin.
4. The agent extracts the JSON field `token`.
5. The agent writes the token to the local credential file with file mode `600`.
6. The agent runs `whoami` to verify the token.

The agent does not need the user's jAccount password. If the browser is not logged in, the agent should ask the user to log in manually and then continue.

Agent prompt template:

```text
I am logged in to https://meeting.sjtu.edu.cn in my local browser. Extract only the token field from the user_info cookie for this origin. Do not ask for my password. Do not print the token in chat or logs. Write it to ~/.config/sjtu-meeting/creds.json with chmod 600, then run `python3 scripts/sjtu_meeting.py whoami` to verify it.
```

Manual browser-console extraction:

```js
(() => {
  const m = document.cookie.match(/(?:^|;\s*)user_info=([^;]+)/);
  if (!m) throw new Error("user_info cookie not found; log in to meeting.sjtu.edu.cn first");
  let o = JSON.parse(decodeURIComponent(m[1]));
  if (typeof o === "string") o = JSON.parse(o);
  return o.token;
})()
```

Then create the credential file locally:

```bash
mkdir -p ~/.config/sjtu-meeting
chmod 700 ~/.config/sjtu-meeting
```

```json
{
  "user_token": "paste-token-here",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

Save it as `~/.config/sjtu-meeting/creds.json`, then run:

```bash
chmod 600 ~/.config/sjtu-meeting/creds.json
python3 scripts/sjtu_meeting.py whoami
```

See [docs/credential-setup.md](docs/credential-setup.md) for the detailed guide, including troubleshooting and safety boundaries.

## Token Refresh

When `whoami` fails or an API call returns an authentication error, refresh the token from a browser session that is already logged in to `meeting.sjtu.edu.cn`.

In a browser devtools console on the meeting site:

```js
(() => {
  const m = document.cookie.match(/(?:^|;\s*)user_info=([^;]+)/);
  let o = JSON.parse(decodeURIComponent(m[1]));
  if (typeof o === "string") o = JSON.parse(o);
  return o.token;
})()
```

Write the returned value to the `user_token` field in your local credential file. Treat it as a session secret.

## Installation

With `uv`:

```bash
uv run python3 scripts/sjtu_meeting.py whoami
```

Or install dependencies into your current environment:

```bash
uv pip install httpx
python3 scripts/sjtu_meeting.py whoami
```

The only runtime dependency is `httpx`.

## Command Reference

### Validate Credentials

```bash
python3 scripts/sjtu_meeting.py whoami
python3 scripts/sjtu_meeting.py whoami --json
```

### List Meetings

By default, `list` returns meetings from today through the next year.

```bash
python3 scripts/sjtu_meeting.py list
python3 scripts/sjtu_meeting.py list --from 2026-06-01 --to 2026-06-30
python3 scripts/sjtu_meeting.py list --search "seminar" --json
python3 scripts/sjtu_meeting.py list --all
```

### Get Meeting Details

Use the internal meeting ID from `list`.

```bash
python3 scripts/sjtu_meeting.py get 123456
python3 scripts/sjtu_meeting.py get 123456 --json
```

The response includes `join_url` when available.

### Create One Meeting

```bash
python3 scripts/sjtu_meeting.py create \
  --topic "Weekly Seminar" \
  --date 2026-06-09 \
  --time 19:00 \
  --duration 3 \
  --group 14 \
  --cohost alice,bob
```

Duration accepts hours or minutes:

- `3`
- `0.5`
- `90m`

Start time must end in `:00` or `:30`.

### Batch Create

Create `meetings.json`:

```json
[
  {"topic": "Weekly Seminar", "date": "2026-06-09", "time": "19:00", "duration": 3, "cohost": "alice,bob"},
  {"topic": "Weekly Seminar", "date": "2026-06-16", "time": "19:00", "duration": 3, "cohost": "alice,bob"}
]
```

Run:

```bash
python3 scripts/sjtu_meeting.py create --batch meetings.json --json
```

Batch creation uses a thread pool with default concurrency `4`.

### Recurring Meetings

Edit `assets/recurring_meetings.json` or set:

```bash
export SJTU_MEETING_RECURRING=/path/to/recurring_meetings.json
```

Preview first:

```bash
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --dry-run
```

Create only after checking the preview:

```bash
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07
```

Options:

```bash
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --weeks 16
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --only WEEKLY_SEMINAR
python3 scripts/sjtu_meeting.py recurring --start 2026-09-07 --all-templates
```

Weekday encoding in the template is `0 = Sunday, 1 = Monday, ..., 6 = Saturday`.

### Delete

Deletion is irreversible. Always list candidates first.

```bash
python3 scripts/sjtu_meeting.py delete 123456
python3 scripts/sjtu_meeting.py delete 123456 123457 --json
```

### Busy Slots

```bash
python3 scripts/sjtu_meeting.py busy --date 2026-06-09 --duration 3 --group 14
python3 scripts/sjtu_meeting.py busy --date 2026-06-09 --json
```

### Calendar

```bash
python3 scripts/sjtu_meeting.py calendar --view month --date 2026-06-01
python3 scripts/sjtu_meeting.py calendar --view week --date 2026-06-09
python3 scripts/sjtu_meeting.py calendar --view day --date 2026-06-09
```

Calendar output is JSON because the API shape is nested.

## Implementation Details

### API Shape

Base URL:

```text
https://meeting.sjtu.edu.cn/api/v1
```

Most wrapped endpoints use:

```text
POST application/x-www-form-urlencoded
```

The API returns a common envelope:

```json
{
  "code": 200,
  "text": "OK",
  "success": true,
  "data": {}
}
```

The CLI treats `success: true` as success.

### Wrapped Endpoints

| CLI command | Endpoint | Purpose |
|---|---|---|
| `whoami` | `/user/incomplete` | lightweight token validation |
| `list` | `/meeting/list` | meeting list with optional search/date range |
| `get` | `/meeting/get` | full details, including join URL |
| `create` | `/meeting/edit` | create or edit; this CLI uses `id=0` for create |
| `delete` | `/meeting/delete` | delete by internal ID |
| `busy` | `/query/busy` | half-hour busy/free slots |
| `calendar` | `/query/view/day`, `/query/view/week`, `/query/view/month` | calendar views |

### Create Response Parsing

`meeting/edit` returns a notice URL rather than a direct JSON field for the Tencent join link. The CLI parses:

- query parameter `address` for the Tencent join URL
- query parameter `content` for the meeting number

That is why `create` can immediately print the join URL and meeting number.

### Date Range Defaults

The raw list endpoint can return old historical records. The CLI defaults to a future one-year range unless `--all` is passed.

### Safety Boundary

The repository documents but intentionally does not wrap:

- `meeting/mail/*`, because those endpoints send real emails
- `admin/*`, because they are administrative actions
- `user/clear` and similar clear/rebuild endpoints

Agents should compose the exposed atomic commands instead of calling these risky routes directly.

## Security Notes

- `user_token` is equivalent to a session credential for this platform.
- Do not paste a real token into issues, commits, screenshots, logs, or public chats.
- Do not store credentials in this repository.
- This tool does not need your jAccount password; log in through the browser yourself and extract only the token.
- Review generated batch jobs before running them, because they create real reservations.

## Repository Status

This is a public, sanitized release of an internal agent skill. The private token and personal recurring-meeting configuration are not included.
