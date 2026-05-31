# CLI 参考

这份文档是给 agent、维护者和调试者看的。普通用户通常只需要通过自然语言和 agent 对话，不需要手动运行这些命令。

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

## 验证凭据

```bash
python3 scripts/sjtu_meeting.py whoami
python3 scripts/sjtu_meeting.py whoami --json
```

## 列出会议

默认查询从今天起未来一年的会议：

```bash
python3 scripts/sjtu_meeting.py list
python3 scripts/sjtu_meeting.py list --from 2026-06-01 --to 2026-06-30
python3 scripts/sjtu_meeting.py list --search "seminar" --json
python3 scripts/sjtu_meeting.py list --all
```

## 获取会议详情

`id` 来自 `list` 命令返回的内部会议 ID：

```bash
python3 scripts/sjtu_meeting.py get 123456
python3 scripts/sjtu_meeting.py get 123456 --json
```

详情中会包含 `join_url`，即腾讯会议入会链接。

## 创建单个会议

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

## 批量创建会议

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

## 固定周会模板

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

## 删除会议

删除不可逆。建议先 `list` 查出候选会议，确认 ID 后再删。

```bash
python3 scripts/sjtu_meeting.py delete 123456
python3 scripts/sjtu_meeting.py delete 123456 123457 --json
```

## 查询时段占用

```bash
python3 scripts/sjtu_meeting.py busy --date 2026-06-09 --duration 3 --group 14
python3 scripts/sjtu_meeting.py busy --date 2026-06-09 --json
```

## 查询日历视图

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
