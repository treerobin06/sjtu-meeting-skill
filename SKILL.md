---
name: sjtu-meeting
description: >
  Manage meetings on Shanghai Jiao Tong University's meeting.sjtu.edu.cn platform by calling the backend API directly.
  Use this skill when the user wants to list, create, batch-create, inspect, delete, or check availability for their own
  SJTU cloud video meetings. It returns Tencent Meeting join URLs and meeting numbers without opening the web UI.
---

# SJTU Meeting Skill

This skill wraps the `meeting.sjtu.edu.cn` backend API with a small Python CLI. It is designed for agents that need reliable,
scriptable access to SJTU cloud video meeting reservations without browser form automation.

## Entry Point

```bash
python3 scripts/sjtu_meeting.py <command> [options] [--json]
```

Use `--json` when another program or agent needs structured output. Run `whoami` first to verify that the token is still valid.

## Commands

| User intent | Command |
|---|---|
| List meetings, meeting numbers, status | `list` |
| Get full join link and streaming link | `get <id>` |
| Create one meeting or batch-create many | `create` |
| Delete meetings | `delete <id> [id ...]` |
| Check room-group availability | `busy --date YYYY-MM-DD --group 14` |
| Query calendar view | `calendar --view day\|week\|month --date YYYY-MM-DD` |
| Validate credentials | `whoami` |
| Expand a weekly meeting template | `recurring --start YYYY-MM-DD --dry-run` |

## Typical Workflows

- Delete meetings: run `list` first, show the candidate IDs to the user, and only then run `delete`.
- Create a semester schedule: generate a batch JSON or use `recurring --dry-run`, show the full plan, then create after confirmation.
- Share the next join link: run `list` for the near future, pick the relevant ID, then run `get`.

## Credentials

The platform API accepts a single `user_token`. The token is stored outside this repository.

Default credential file:

```text
~/.config/sjtu-meeting/creds.json
```

Override paths with:

```bash
export SJTU_MEETING_CREDS=/path/to/creds.json
export SJTU_MEETING_RECURRING=/path/to/recurring_meetings.json
```

Credential lookup order:

1. `--token`
2. `SJTU_MEETING_TOKEN`
3. `creds.json`

Minimal `creds.json`:

```json
{
  "user_token": "paste-token-here",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}
```

The token comes from the logged-in browser's `user_info` cookie on `meeting.sjtu.edu.cn`. Do not commit it.

For a new user's agent setup:

1. Ask the user to open `https://meeting.sjtu.edu.cn` and complete normal SSO login themselves.
2. Read only the `user_info` cookie from that origin in the logged-in browser context.
3. Extract the `token` field.
4. Write it to `~/.config/sjtu-meeting/creds.json` with permissions `600`.
5. Run `python3 scripts/sjtu_meeting.py whoami` to verify.

Do not ask for the user's jAccount password, do not print the token, and do not extract credentials from third-party or unconsented browser sessions. See `docs/credential-setup.md`.

## Safety Rules

- `delete` is irreversible; always list and confirm IDs before deletion.
- Batch creation creates real external records; dry-run and confirm first.
- The CLI intentionally does not expose mail-sending, admin, or clearing endpoints.
- Never publish `user_token`, cookies, account passwords, or real private meeting templates.

## Platform Constraints

- Start time must be on the hour or half-hour: `HH:00` or `HH:30`.
- Duration is normalized to 30-minute increments and capped at 24 hours.
- Common room groups: `14` = 50 people, `11` = 300 people, `12` = 2000 people with review, `13` = 2026 300-person group.

## Implementation Notes

- All wrapped endpoints are under `https://meeting.sjtu.edu.cn/api/v1`.
- Requests are `POST` with `application/x-www-form-urlencoded` payloads.
- The token is sent in both the `user-token` header and the `user_token` body field.
- `create` parses the notice URL returned by `meeting/edit` to extract the Tencent join URL and meeting number.
- `list` defaults to future meetings for one year to avoid old historical records.
- Batch creation and deletion use a small thread pool with default concurrency 4.
