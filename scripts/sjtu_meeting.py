#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SJTU 云视频会议 (meeting.sjtu.edu.cn) API CLI —— atomic operations.

认证：只需一个 user_token（来自浏览器 user_info cookie 的 token 字段）。
读取顺序：--token 参数 > 环境变量 SJTU_MEETING_TOKEN > 凭据文件
凭据文件：默认 ~/.config/sjtu-meeting/creds.json，可用 SJTU_MEETING_CREDS 覆盖
token 过期时（接口返回 success=false / 401 / 数据异常），需从登录态浏览器重抓刷新。

每个子命令都是一个原子操作，互不依赖；编排（比如"建一学期的组会再核对"）由调用方组合。
默认输出人类可读文本；加 --json 输出结构化 JSON（供程序 / agent 解析）。
"""
import argparse
import json
import os
import re
import sys
import time
import datetime
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, unquote

try:
    import httpx
except ImportError:
    sys.exit("缺少 httpx。安装：uv pip install httpx  （或 pip3 install httpx）")

CREDS_PATH = os.path.expanduser(
    os.environ.get("SJTU_MEETING_CREDS", "~/.config/sjtu-meeting/creds.json")
)
BASE = "https://meeting.sjtu.edu.cn/api/v1"
RECURRING_PATH = os.path.expanduser(
    os.environ.get(
        "SJTU_MEETING_RECURRING",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "recurring_meetings.json"),
    )
)

# 会议室组：id -> 名称（来自 user/preset，创建会议 group_id 用）
ROOM_GROUPS = {
    14: "腾讯会议（50人）",
    11: "腾讯会议（300人）",
    12: "腾讯会议（2000人）需审核",
    13: "腾讯会议2026（300人）",
}

# ---------------------------------------------------------------- 凭据
def load_creds(token_override=None):
    creds = {}
    if os.path.exists(CREDS_PATH):
        try:
            with open(CREDS_PATH, encoding="utf-8") as f:
                creds = json.load(f)
        except Exception as e:
            sys.exit(f"读取凭据文件失败 {CREDS_PATH}: {e}")
    token = token_override or os.environ.get("SJTU_MEETING_TOKEN") or creds.get("user_token")
    if not token:
        sys.exit(
            "没有 user_token。请用 --token 指定，或写入 "
            + CREDS_PATH
            + "（字段 user_token）。token = 浏览器 user_info cookie 的 token 字段。"
        )
    creds["user_token"] = token
    return creds


# ---------------------------------------------------------------- HTTP
class AuthError(RuntimeError):
    pass


def api(token, path, data=None, retries=4):
    """POST 一个接口，返回解析后的 JSON dict。429 自动退避重试。"""
    headers = {
        "user-token": token,
        "Content-Type": "application/x-www-form-urlencoded",
        "accept": "application/json",
    }
    body = dict(data or {})
    body.setdefault("user_token", token)
    last = None
    for attempt in range(retries + 1):
        try:
            r = httpx.post(BASE + path, headers=headers, data=body, timeout=40)
            if r.status_code == 429:
                time.sleep(0.3 * (2 ** attempt))
                continue
            if r.status_code in (401, 403):
                raise AuthError(f"{path} 返回 {r.status_code}，token 可能已失效，请重抓凭据。")
            try:
                return r.json()
            except Exception:
                raise RuntimeError(f"{path} 返回非 JSON（HTTP {r.status_code}）: {r.text[:200]}")
        except AuthError:
            raise
        except Exception as e:
            last = e
            time.sleep(0.3 * (2 ** attempt))
    raise RuntimeError(f"请求失败 {path}: {last}")


def ok(j):
    return bool(j and j.get("success"))


# ---------------------------------------------------------------- 工具
def parse_duration_to_min(s):
    """'3' / '3h' / '3小时' -> 180；'0.5' -> 30；'90m' / '90分钟' -> 90。默认按小时。"""
    if s is None:
        return 180
    s = str(s).strip()
    m = re.match(r"^([\d.]+)\s*(.*)$", s)
    if not m:
        raise ValueError(f"无法解析时长: {s}")
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit in ("m", "min", "mins", "minute", "minutes", "分", "分钟"):
        minutes = val
    else:  # 小时
        minutes = val * 60
    minutes = int(round(minutes / 30.0)) * 30  # 吸附到 30 分钟整
    return max(30, min(minutes, 24 * 60))


def parse_zoom_info(s):
    """'会议号:679829601<br>密码:000000' -> (code, pwd)"""
    s = s or ""
    code = re.search(r"会议号[:：]?\s*(\d+)", s)
    pwd = re.search(r"密码[:：]?\s*(\S+)", s)
    return (code.group(1) if code else "", pwd.group(1) if pwd else "")


def parse_create_result(j):
    """从 meeting/edit 返回中提取 腾讯链接 + 会议号。"""
    link, code = "", ""
    try:
        notice = (j.get("data") or {}).get("data") or ""
        q = parse_qs(urlparse(notice).query)
        link = q.get("address", [""])[0]
        content = unquote(q.get("content", [""])[0])
        cm = re.search(r"会议号码[:：]?\s*(\d+)", content)
        code = cm.group(1) if cm else ""
    except Exception:
        pass
    return link, code


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def out(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    return obj


# ---------------------------------------------------------------- 命令
def cmd_whoami(args):
    creds = load_creds(args.token)
    tok = creds["user_token"]
    j = api(tok, "/user/incomplete", {})
    info = {
        "name": creds.get("name"),
        "user_id": creds.get("user_id"),
        "email": creds.get("email"),
        "allow_room_group": creds.get("allow_room_group"),
        "token_valid": ok(j),
        "incomplete_count": (j or {}).get("data"),
    }
    if args.json:
        return out(info, True)
    status = "✓ 有效" if info["token_valid"] else "✗ 可能失效（请重抓凭据）"
    print(f"{info['name']} ({info['user_id']}) <{info['email']}>")
    print(f"token: {status}   待办: {info['incomplete_count']}")
    groups = ", ".join(f"{g}={ROOM_GROUPS.get(g, '?')}" for g in (info["allow_room_group"] or []))
    print(f"可用会议室组: {groups}")
    return info


def cmd_list(args):
    creds = load_creds(args.token)
    tok = creds["user_token"]
    data = {"search": args.search or "", "page": 1, "page_size": args.limit, "use_date_range": 0}
    if not args.all:
        # 默认只看未来一年（避免返回多年前的历史会议）
        from datetime import date, timedelta
        today = date.today()
        frm = args.date_from or today.isoformat()
        to = args.date_to or (today + timedelta(days=365)).isoformat()
        data["use_date_range"] = 1
        data["date_range[0]"] = f"{frm} 00:00"
        data["date_range[1]"] = f"{to} 23:59"
    elif args.date_from and args.date_to:
        data["use_date_range"] = 1
        data["date_range[0]"] = f"{args.date_from} 00:00"
        data["date_range[1]"] = f"{args.date_to} 23:59"
    j = api(tok, "/meeting/list", data)
    if not ok(j):
        sys.exit(f"列表失败: {j.get('text') or j}")
    rows = (j.get("data") or {}).get("data") or []
    items = []
    for m in rows:
        code, pwd = parse_zoom_info(m.get("zoom_info"))
        items.append({
            "id": m.get("id"),
            "start_time": m.get("start_time"),
            "duration": m.get("duration_hour"),
            "topic": m.get("topic"),
            "room_group": m.get("room_group"),
            "status": strip_html(m.get("approve_status")),
            "meeting_code": code,
            "password": pwd,
        })
    if args.json:
        return out({"count": len(items), "meetings": items}, True)
    if not items:
        print("（没有匹配的会议）")
        return items
    print(f"共 {len(items)} 个会议：")
    for m in items:
        print(f"  [{m['id']}] {m['start_time']}  {m['duration']:<5} {m['topic']}")
        print(f"        会议号 {m['meeting_code']}  密码 {m['password']}  {m['status']}")
    return items


def cmd_get(args):
    creds = load_creds(args.token)
    tok = creds["user_token"]
    j = api(tok, "/meeting/get", {"id": args.id})
    if not ok(j):
        sys.exit(f"获取失败: {j.get('text') or j}")
    d = (j.get("data") or {}).get("data") or j.get("data") or {}
    if args.json:
        return out(d, True)
    print(f"主题: {d.get('topic')}")
    print(f"时间: {d.get('meeting_date')} {d.get('meeting_time')}  时长 {d.get('duration')} 分钟")
    print(f"会议室组: {ROOM_GROUPS.get(int(d.get('group_id', 0)), d.get('group_id'))}")
    print(f"密码: {d.get('password')}   状态: {d.get('approve_status')}")
    print(f"主持人: {d.get('host_name')} ({d.get('host_id')})   联席: {d.get('assistants')}")
    print(f"入会链接: {d.get('join_url')}")
    if d.get("streaming"):
        print(f"直播链接: {d.get('streaming')}")
    return d


def _build_create_payload(creds, job):
    tok = creds["user_token"]
    # 平台约束：会议开始时间只能是整点或半点（分钟 00 / 30）
    tm = str(job.get("time", "")).strip()
    mm = re.match(r"^(\d{1,2}):(\d{2})$", tm)
    if not mm or mm.group(2) not in ("00", "30"):
        raise ValueError(f"开始时间必须是整点或半点（分钟 00/30），收到 '{tm}'")
    group_id = job.get("group") or creds.get("default_group_id") or 14
    password = str(job.get("password") or creds.get("default_password") or "000000")
    cohost = job.get("cohost")
    if cohost is None:
        cohost = creds.get("default_cohost") or ""
    dur_min = parse_duration_to_min(job.get("duration", 3))
    return {
        "user_token": tok,
        "topic": job["topic"],
        "meeting_date": job["date"],
        "meeting_time": job["time"],
        "duration": dur_min,
        "group_id": group_id,
        "usage": job.get("usage") or "办公",
        "size": job.get("size") or 100,
        "password": password,
        "assistants": cohost,
        "option_mute": 1, "option_jbh": 1, "option_h323": 0, "auto_record": 0,
        "assistant": "", "option_enroll": 0, "enroll_attendees": "",
        "option_water_mark": 0, "option_sso_only": 0, "meeting_guests": "",
        "waiting_room": 0, "option_interpreter": 0, "id": 0, "quite": "true",
        "option_live": 0, "attendees": "[]", "ask": 1,
    }


def _create_one(creds, job):
    tok = creds["user_token"]
    try:
        payload = _build_create_payload(creds, job)
        j = api(tok, "/meeting/edit", payload)
        link, code = parse_create_result(j)
        return {
            "topic": job["topic"], "date": job["date"], "time": job["time"],
            "ok": ok(j), "join_url": link, "meeting_code": code,
            "msg": (j.get("data") or {}).get("message") or j.get("text"),
        }
    except Exception as e:
        return {"topic": job.get("topic"), "date": job.get("date"), "time": job.get("time"), "ok": False, "error": str(e)}


def cmd_create(args):
    creds = load_creds(args.token)
    # 组装任务列表
    if args.batch:
        raw = sys.stdin.read() if args.batch == "-" else open(args.batch, encoding="utf-8").read()
        jobs = json.loads(raw)
        if isinstance(jobs, dict):
            jobs = [jobs]
    else:
        if not (args.topic and args.date and args.time):
            sys.exit("单条创建需要 --topic --date --time（或用 --batch 传 JSON）")
        jobs = [{
            "topic": args.topic, "date": args.date, "time": args.time,
            "duration": args.duration, "group": args.group,
            "password": args.password, "cohost": args.cohost,
        }]
    # 并发创建
    results = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(_create_one, creds, jb): i for i, jb in enumerate(jobs)}
        for fut in futs:
            i = futs[fut]
            results[i] = fut.result()
    okc = sum(1 for r in results if r and r["ok"])
    if args.json:
        return out({"total": len(jobs), "ok": okc, "results": results}, True)
    print(f"创建完成：成功 {okc}/{len(jobs)}")
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        print(f"  {mark} {r['date']} {r['time']} {r['topic']}")
        if r["ok"]:
            print(f"       会议号 {r['meeting_code']}  入会 {r['join_url']}")
        else:
            print(f"       {r.get('error') or r.get('msg')}")
    return results


def _delete_one(tok, mid):
    try:
        j = api(tok, "/meeting/delete", {"id": mid})
        return {"id": mid, "ok": ok(j)}
    except Exception as e:
        return {"id": mid, "ok": False, "error": str(e)}


def cmd_delete(args):
    creds = load_creds(args.token)
    tok = creds["user_token"]
    ids = args.ids
    results = [None] * len(ids)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(_delete_one, tok, mid): i for i, mid in enumerate(ids)}
        for fut in futs:
            results[futs[fut]] = fut.result()
    okc = sum(1 for r in results if r and r["ok"])
    if args.json:
        return out({"total": len(ids), "ok": okc, "results": results}, True)
    print(f"删除完成：成功 {okc}/{len(ids)}")
    for r in results:
        print(f"  {'✅' if r['ok'] else '❌'} {r['id']} {r.get('error', '')}")
    return results


def cmd_calendar(args):
    creds = load_creds(args.token)
    tok = creds["user_token"]
    path = {"day": "/query/view/day", "week": "/query/view/week", "month": "/query/view/month"}[args.view]
    j = api(tok, path, {"date": args.date})
    if not ok(j):
        sys.exit(f"日历查询失败: {j.get('text') or j}")
    return out(j.get("data"), True if args.json else True)  # 日历结构复杂，始终 JSON


def cmd_busy(args):
    creds = load_creds(args.token)
    tok = creds["user_token"]
    dur = parse_duration_to_min(args.duration)
    j = api(tok, "/query/busy", {
        "start_date": args.date, "id": 0, "duration": dur,
        "h323": "false", "group_id": args.group or creds.get("default_group_id") or 14,
    })
    if not ok(j):
        sys.exit(f"时段查询失败: {j.get('text') or j}")
    states = (j.get("data") or {}).get("states") or {}
    if args.json:
        return out(states, True)
    busy = [t for t, s in states.items() if s != "空"]
    print(f"{args.date} 该会议室组占用时段：{('、'.join(busy) if busy else '全天空闲')}")
    return states


# ---------------------------------------------------------------- 固定会议模板
WEEKDAY_CN = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]


def load_recurring():
    with open(os.path.normpath(RECURRING_PATH), encoding="utf-8") as f:
        return json.load(f)


def cmd_recurring(args):
    """按固定会议模板批量建会。给起始日期，按周数展开每个会议的所有日期，并发创建。"""
    creds = load_creds(args.token)
    tpl = load_recurring()
    meetings = tpl["meetings"]
    shared = tpl.get("shared", {})
    weeks = args.weeks or tpl.get("default_weeks", 8)
    if args.only:
        names = [s.strip() for s in args.only.split(",") if s.strip()]
    elif args.all_templates:
        names = list(meetings.keys())
    else:
        names = tpl.get("default_batch", list(meetings.keys()))
    try:
        start = datetime.date.fromisoformat(args.start)
    except Exception:
        sys.exit(f"--start 日期格式应为 YYYY-MM-DD，收到 {args.start}")
    end = start + datetime.timedelta(days=weeks * 7 - 1)
    # 展开每个固定会议在日期范围内的所有出现
    jobs = []
    for name in names:
        m = meetings.get(name)
        if not m:
            print(f"⚠ 模板里没有会议「{name}」，跳过")
            continue
        cur = start
        while cur <= end:
            our_wd = (cur.weekday() + 1) % 7  # python Mon=0 → 本表 周一=1 / 周日=0
            if our_wd == m["weekday"]:
                jobs.append({
                    "topic": name, "date": cur.isoformat(), "time": m["time"],
                    "duration": m.get("duration_hours", shared.get("duration_hours", 3)),
                    "cohost": m.get("cohost", shared.get("cohost", "")),
                    "password": shared.get("password", "000000"),
                    "group": shared.get("group_id", 14),
                })
            cur += datetime.timedelta(days=1)
    jobs.sort(key=lambda j: (j["date"], j["time"]))
    cnt = Counter(j["topic"] for j in jobs)
    print(f"起始 {start} ~ {end}（约 {weeks} 周），将创建 {len(jobs)} 个会议：")
    for name in names:
        if cnt.get(name):
            m = meetings[name]
            print(f"  {name}：{WEEKDAY_CN[m['weekday']]} {m['time']} × {cnt[name]} 次")
    if args.dry_run:
        if args.json:
            return out({"total": len(jobs), "weeks": weeks, "start": str(start), "end": str(end), "jobs": jobs}, True)
        print("（--dry-run 预览，未创建。去掉 --dry-run 才真正创建。）")
        return jobs
    results = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(_create_one, creds, jb): i for i, jb in enumerate(jobs)}
        for fut in futs:
            results[futs[fut]] = fut.result()
    okc = sum(1 for r in results if r and r["ok"])
    if args.json:
        return out({"total": len(jobs), "ok": okc, "results": results}, True)
    print(f"\n创建完成：成功 {okc}/{len(jobs)}")
    for r in results:
        if not (r and r["ok"]):
            print(f"  ❌ {r.get('date')} {r.get('time')} {r.get('topic')}: {r.get('error') or r.get('msg')}")
    return results


# ---------------------------------------------------------------- argparse
def add_common(parser, suppress):
    """让 --token / --json 既能放在子命令前、也能放后面。
    子命令侧用 SUPPRESS，使其在未显式给出时不覆盖主命令侧已解析的值。"""
    parser.add_argument("--token", default=(argparse.SUPPRESS if suppress else None),
                        help="覆盖 user_token（默认读凭据文件 / SJTU_MEETING_TOKEN）")
    parser.add_argument("--json", action="store_true",
                        default=(argparse.SUPPRESS if suppress else False),
                        help="输出结构化 JSON")


def build_parser():
    p = argparse.ArgumentParser(description="SJTU 云视频会议 API CLI（atomic 操作）")
    add_common(p, suppress=False)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_sub(name, **kw):
        sp = sub.add_parser(name, **kw)
        add_common(sp, suppress=True)
        return sp

    sp = add_sub("whoami", help="验证 token + 显示账户信息")
    sp.set_defaults(func=cmd_whoami)

    sp = add_sub("list", help="列出我的会议")
    sp.add_argument("--search", help="主题关键词")
    sp.add_argument("--from", dest="date_from", help="起始日期 YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", help="结束日期 YYYY-MM-DD")
    sp.add_argument("--limit", type=int, default=100, help="最多返回条数（默认 100）")
    sp.add_argument("--all", action="store_true", help="包含历史会议（默认只看未来一年）")
    sp.set_defaults(func=cmd_list)

    sp = add_sub("get", help="单会议详情（含 join_url 入会链接）")
    sp.add_argument("id", type=int, help="会议内部 id（从 list 拿）")
    sp.set_defaults(func=cmd_get)

    sp = add_sub("create", help="创建会议（单条或 --batch 批量并发）")
    sp.add_argument("--topic")
    sp.add_argument("--date", help="YYYY-MM-DD")
    sp.add_argument("--time", help="HH:MM（分钟须 00 或 30）")
    sp.add_argument("--duration", default="3", help="时长，默认按小时：3 / 0.5 / 90m（默认 3）")
    sp.add_argument("--group", type=int, help="会议室组 id（默认 14=50人）")
    sp.add_argument("--password", help="6 位数字密码（默认 000000）")
    sp.add_argument("--cohost", help="联席主持 jAccount，逗号分隔")
    sp.add_argument("--batch", help="批量 JSON 文件路径，或 - 从 stdin 读；元素 {topic,date,time,duration,group,password,cohost}")
    sp.add_argument("--concurrency", type=int, default=4, help="并发数（默认 4，实测零限流）")
    sp.set_defaults(func=cmd_create)

    sp = add_sub("delete", help="删除会议（可多个 id，并发）")
    sp.add_argument("ids", type=int, nargs="+", help="会议 id，可多个")
    sp.add_argument("--concurrency", type=int, default=4)
    sp.set_defaults(func=cmd_delete)

    sp = add_sub("recurring", help="按固定会议模板批量建（每周固定那些会）")
    sp.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    sp.add_argument("--weeks", type=int, help="持续周数（默认读模板 default_weeks）")
    sp.add_argument("--only", help="只建这些（逗号分隔主题），默认建模板 default_batch")
    sp.add_argument("--all-templates", action="store_true", help="建模板里全部会议（含周四/周六会）")
    sp.add_argument("--dry-run", action="store_true", help="只预览清单不创建（建议先 dry-run 给用户确认）")
    sp.add_argument("--concurrency", type=int, default=4)
    sp.set_defaults(func=cmd_recurring)

    sp = add_sub("calendar", help="会议日历视图（day/week/month）")
    sp.add_argument("--view", choices=["day", "week", "month"], default="month")
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.set_defaults(func=cmd_calendar)

    sp = add_sub("busy", help="某日某会议室组的时段占用")
    sp.add_argument("--date", required=True, help="YYYY-MM-DD")
    sp.add_argument("--duration", default="3", help="时长（默认 3 小时）")
    sp.add_argument("--group", type=int, help="会议室组 id（默认 14）")
    sp.set_defaults(func=cmd_busy)
    return p


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except AuthError as e:
        sys.exit(f"[认证失败] {e}")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
