#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-command credential setup for the SJTU meeting skill.

The script opens a dedicated local Chrome/Edge profile with Chrome DevTools
Protocol enabled on 127.0.0.1, waits for the user to complete SJTU SSO login,
extracts only the token field from the meeting.sjtu.edu.cn user_info cookie,
and writes ~/.config/sjtu-meeting/creds.json with restrictive permissions.

It deliberately never prints the token.
"""

import argparse
import base64
import hashlib
import json
import os
import platform
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


MEETING_URL = "https://meeting.sjtu.edu.cn"
API_URL = "https://meeting.sjtu.edu.cn/api/v1/user/incomplete"
DEFAULT_CREDS = "~/.config/sjtu-meeting/creds.json"
DEFAULT_PROFILE = "~/.config/sjtu-meeting/browser-profile"
VERIFY_COMMAND = "python3 scripts/sjtu_meeting.py whoami"
DEFAULT_ATTACH_PORTS = "9222,9223,9224"


class SetupError(RuntimeError):
    pass


def expand(path):
    return os.path.abspath(os.path.expanduser(path))


def pick_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def urlopen_json(url, timeout=3, method=None):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_browser(browser, browser_path=None):
    if browser_path:
        path = expand(browser_path)
        if not os.path.exists(path):
            raise SetupError(f"指定的浏览器不存在: {path}")
        return path

    system = platform.system().lower()
    candidates = []

    if system == "darwin":
        mac_apps = {
            "chrome": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ],
            "edge": [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ],
            "chromium": [
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "~/Applications/Chromium.app/Contents/MacOS/Chromium",
            ],
        }
        order = ["chrome", "edge", "chromium"] if browser == "auto" else [browser]
        for name in order:
            candidates.extend(mac_apps.get(name, []))

    elif system == "windows":
        roots = [
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
        ]
        win_rel = {
            "chrome": [os.path.join("Google", "Chrome", "Application", "chrome.exe")],
            "edge": [os.path.join("Microsoft", "Edge", "Application", "msedge.exe")],
            "chromium": [os.path.join("Chromium", "Application", "chrome.exe")],
        }
        order = ["chrome", "edge", "chromium"] if browser == "auto" else [browser]
        for name in order:
            for root in roots:
                if root:
                    candidates.extend(os.path.join(root, rel) for rel in win_rel.get(name, []))

    else:
        names = {
            "chrome": ["google-chrome", "google-chrome-stable", "chrome"],
            "edge": ["microsoft-edge", "microsoft-edge-stable", "msedge"],
            "chromium": ["chromium", "chromium-browser"],
        }
        order = ["chrome", "edge", "chromium"] if browser == "auto" else [browser]
        for name in order:
            for exe in names.get(name, []):
                found = shutil.which(exe)
                if found:
                    return found

    for candidate in candidates:
        path = expand(candidate)
        if os.path.exists(path):
            return path

    raise SetupError("没有找到 Chrome/Edge/Chromium。可用 --browser-path 指定浏览器可执行文件。")


def launch_browser(browser_path, profile_dir, port):
    os.makedirs(profile_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(profile_dir, 0o700)
    except OSError:
        pass

    cmd = [
        browser_path,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        MEETING_URL,
    ]

    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_for_debug_endpoint(port, timeout):
    deadline = time.time() + timeout
    version_url = f"http://127.0.0.1:{port}/json/version"
    last_error = None
    while time.time() < deadline:
        try:
            return urlopen_json(version_url, timeout=2)
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise SetupError(f"无法连接本机浏览器调试端口 127.0.0.1:{port}: {last_error}")


def list_targets(port):
    try:
        return urlopen_json(f"http://127.0.0.1:{port}/json", timeout=3)
    except Exception:
        return []


def target_on_meeting_site(target):
    if target.get("type") != "page":
        return False
    url = target.get("url") or ""
    try:
        host = urllib.parse.urlparse(url).hostname
    except Exception:
        host = None
    return host == "meeting.sjtu.edu.cn"


def create_meeting_target(port):
    quoted = urllib.parse.quote(MEETING_URL, safe="")
    urls = [
        (f"http://127.0.0.1:{port}/json/new?{quoted}", "PUT"),
        (f"http://127.0.0.1:{port}/json/new?{quoted}", "GET"),
    ]
    for url, method in urls:
        try:
            return urlopen_json(url, timeout=3, method=method)
        except Exception:
            continue
    return None


def recv_exact(sock, n):
    chunks = []
    remaining = n
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise SetupError("浏览器调试连接已关闭。")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class WebSocket:
    def __init__(self, ws_url):
        parsed = urllib.parse.urlparse(ws_url)
        if parsed.scheme != "ws":
            raise SetupError(f"只支持本机 ws:// DevTools 地址: {ws_url}")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        header = response.decode("iso-8859-1", errors="replace")
        if " 101 " not in header.split("\r\n", 1)[0]:
            raise SetupError("浏览器拒绝 DevTools WebSocket 连接。")
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if f"Sec-WebSocket-Accept: {accept}".lower() not in header.lower():
            raise SetupError("DevTools WebSocket 握手校验失败。")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def send_text(self, text):
        data = text.encode("utf-8")
        frame = bytearray([0x81])
        length = len(data)
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(0x80 | 127)
            frame.extend(length.to_bytes(8, "big"))
        mask = secrets.token_bytes(4)
        frame.extend(mask)
        frame.extend(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(frame)

    def recv_text(self):
        fragments = []
        while True:
            first, second = recv_exact(self.sock, 2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(recv_exact(self.sock, 2), "big")
            elif length == 127:
                length = int.from_bytes(recv_exact(self.sock, 8), "big")
            mask = recv_exact(self.sock, 4) if masked else b""
            payload = recv_exact(self.sock, length) if length else b""
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == 8:
                raise SetupError("浏览器关闭了 DevTools WebSocket。")
            if opcode == 9:
                self._send_pong(payload)
                continue
            if opcode in (1, 0):
                fragments.append(payload)
                if fin:
                    return b"".join(fragments).decode("utf-8")
            elif opcode == 10:
                continue
            else:
                continue

    def _send_pong(self, payload):
        frame = bytearray([0x8A])
        length = len(payload)
        if length >= 126:
            return
        frame.append(0x80 | length)
        mask = secrets.token_bytes(4)
        frame.extend(mask)
        frame.extend(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(frame)


class CDPClient:
    def __init__(self, ws_url):
        self.ws = WebSocket(ws_url)
        self.next_id = 1

    def close(self):
        self.ws.close()

    def call(self, method, params=None, timeout=10):
        msg_id = self.next_id
        self.next_id += 1
        self.ws.send_text(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv_text()
            message = json.loads(raw)
            if message.get("id") != msg_id:
                continue
            if "error" in message:
                raise SetupError(f"DevTools 调用失败 {method}: {message['error']}")
            return message.get("result") or {}
        raise SetupError(f"DevTools 调用超时: {method}")


EXTRACT_JS = r"""
(() => {
  if (location.hostname !== "meeting.sjtu.edu.cn") {
    return {ok: false, reason: "wrong-origin", href: location.href};
  }

  const cookieType = typeof document.cookie;
  const cookieValue = cookieType === "string" ? document.cookie : "";
  const m = cookieValue.match(/(?:^|;\s*)user_info=([^;]+)/);
  if (!m) {
    return {
      ok: false,
      reason: "missing-user-info",
      href: location.href,
      cookieType,
      cookieLength: cookieValue.length
    };
  }

  let info = JSON.parse(decodeURIComponent(m[1]));
  if (typeof info === "string") {
    info = JSON.parse(info);
  }
  if (!info || !info.token) {
    return {ok: false, reason: "missing-token", href: location.href};
  }

  return {
    ok: true,
    token: info.token,
    profile: {
      name: info.name || "",
      user_id: info.user_id || "",
      email: info.email || "",
      allow_room_group: info.allow_room_group || []
    }
  };
})()
"""


def evaluate_target(target):
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        return {"ok": False, "reason": "missing-debugger-url"}
    client = CDPClient(ws_url)
    try:
        client.call("Runtime.enable", timeout=5)
        result = client.call(
            "Runtime.evaluate",
            {
                "expression": EXTRACT_JS,
                "returnByValue": True,
                "awaitPromise": True,
                "timeout": 5000,
            },
            timeout=10,
        )
    finally:
        client.close()

    if result.get("exceptionDetails"):
        return {"ok": False, "reason": "js-exception"}
    remote = result.get("result") or {}
    value = remote.get("value")
    if isinstance(value, dict):
        return value
    return {"ok": False, "reason": "unexpected-result"}


def wait_for_token(port, timeout, prompt=True, create_if_missing=True):
    deadline = time.time() + timeout
    last_report = ""
    target_created = False

    while time.time() < deadline:
        targets = list_targets(port)
        meeting_targets = [t for t in targets if target_on_meeting_site(t)]
        if not meeting_targets and create_if_missing and not target_created:
            create_meeting_target(port)
            target_created = True

        for target in meeting_targets:
            try:
                result = evaluate_target(target)
            except Exception as exc:
                result = {"ok": False, "reason": f"devtools-error: {exc}"}
            if result.get("ok") and result.get("token"):
                return result

            reason = result.get("reason", "waiting")
            if prompt and reason != last_report:
                if reason == "missing-user-info":
                    print("等待登录完成：还没有看到 meeting.sjtu.edu.cn 的 user_info cookie。")
                elif reason == "wrong-origin":
                    print("等待回到 meeting.sjtu.edu.cn 页面。")
                elif reason != "waiting":
                    print(f"等待中：{reason}")
                last_report = reason

        if prompt and not meeting_targets and last_report != "no-meeting-target":
            print("请在打开的浏览器窗口完成 SJTU 登录；脚本会自动继续。")
            last_report = "no-meeting-target"
        time.sleep(2)

    raise SetupError("超时：没有在浏览器里抓到 user_info token。请确认已登录并停留在 meeting.sjtu.edu.cn。")


def load_existing_creds(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_creds(path, token, profile):
    path = expand(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

    creds = load_existing_creds(path)
    creds.update(
        {
            "user_token": token,
            "name": profile.get("name") or creds.get("name", ""),
            "user_id": profile.get("user_id") or creds.get("user_id", ""),
            "email": profile.get("email") or creds.get("email", ""),
            "allow_room_group": profile.get("allow_room_group") or creds.get("allow_room_group", []),
            "default_group_id": creds.get("default_group_id", 14),
            "default_cohost": creds.get("default_cohost", ""),
            "default_password": creds.get("default_password", "000000"),
        }
    )

    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(creds, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path, creds


def verify_token(token):
    body = urllib.parse.urlencode({"user_token": token}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "user-token": token,
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read().decode("utf-8")
    parsed = json.loads(data)
    return parsed


def parse_port_list(raw):
    ports = []
    for item in str(raw or "").replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            port = int(item)
        except ValueError:
            continue
        if 0 < port < 65536 and port not in ports:
            ports.append(port)
    return ports


def finish_setup(args, result):
    token = result["token"]
    profile = result.get("profile") or {}
    path, creds = write_creds(args.creds, token, profile)

    verify_ok = None
    verify_data = None
    if not args.no_verify:
        try:
            verify_data = verify_token(token)
            verify_ok = bool(verify_data and verify_data.get("success"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            verify_ok = False
            verify_data = {"error": str(exc)}

    print(f"已写入凭据文件：{path}")
    print("权限已设置为 600；token 未打印。")
    name = creds.get("name") or "unknown"
    user_id = creds.get("user_id") or "unknown"
    email = creds.get("email") or ""
    print(f"账号: {name} ({user_id}) {email}".rstrip())

    if args.no_verify:
        print("已跳过 API 验证。")
        return 0

    if verify_ok:
        print(f"API 验证成功。待办数量: {verify_data.get('data')}")
        return 0

    print("凭据已保存，但 API 验证失败；请重新登录后再运行一次。")
    return 2


def try_existing_debug_ports(args):
    ports = parse_port_list(args.try_ports)
    for port in ports:
        try:
            wait_for_debug_endpoint(port, timeout=1)
        except Exception:
            continue
        print(f"先尝试已有浏览器调试端口 127.0.0.1:{port}。")
        try:
            result = wait_for_token(
                port,
                timeout=args.existing_timeout,
                prompt=False,
                create_if_missing=True,
            )
            print(f"已从已有浏览器调试端口 127.0.0.1:{port} 读取登录态。")
            return finish_setup(args, result)
        except Exception:
            continue
    return None


def manual_fallback_text(creds_path):
    return f"""
Manual fallback, if the automatic browser setup cannot read the cookie.
No Console JavaScript is required.

1. Open https://meeting.sjtu.edu.cn in Chrome or Edge.
2. Complete SJTU SSO login yourself.
3. After the meeting page loads, open DevTools:
   - macOS: Cmd+Option+I
   - Windows/Linux: F12 or Ctrl+Shift+I
4. Preferred path: open Application > Storage > Cookies > https://meeting.sjtu.edu.cn.
5. Find the cookie named user_info, double-click/copy its Value.
6. If the Application tab is hard to find, use Network instead:
   - Open Network.
   - Refresh the meeting page.
   - Click a request under meeting.sjtu.edu.cn/api/v1, for example user/incomplete.
   - In Headers > Request Headers, copy the user_info=... part from Cookie.
7. Create or edit this local file and paste the copied value into user_info_cookie:

{creds_path}

Example shape:

{{
  "user_info_cookie": "PASTE_USER_INFO_COOKIE_VALUE_HERE",
  "default_group_id": 14,
  "default_cohost": "",
  "default_password": "000000"
}}

8. Save the file, then tell your agent:

I pasted user_info_cookie into {creds_path}. Please verify the SJTU meeting credential.

If you are using the CLI without an agent, verify with:
{VERIFY_COMMAND}

Do not paste the token or cookie into chat, logs, issues, commits, or screenshots.
"""


def build_parser():
    parser = argparse.ArgumentParser(
        description="打开本机 Chrome/Edge 登录 meeting.sjtu.edu.cn，并把 token 写入凭据文件（不打印 token）。"
    )
    parser.add_argument("--browser", choices=["auto", "chrome", "edge", "chromium"], default="auto",
                        help="要启动的浏览器，默认 auto。")
    parser.add_argument("--browser-path", help="浏览器可执行文件路径。")
    parser.add_argument("--profile-dir", default=os.environ.get("SJTU_MEETING_BROWSER_PROFILE", DEFAULT_PROFILE),
                        help="专用浏览器 profile 目录，默认 ~/.config/sjtu-meeting/browser-profile。")
    parser.add_argument("--creds", default=os.environ.get("SJTU_MEETING_CREDS", DEFAULT_CREDS),
                        help="凭据输出路径，默认 ~/.config/sjtu-meeting/creds.json。")
    parser.add_argument("--port", type=int, default=0,
                        help="本机 DevTools 端口，默认自动选择空闲端口。")
    parser.add_argument("--attach-port", type=int,
                        help="不启动浏览器，改为连接已有 127.0.0.1:<port> DevTools 实例。")
    parser.add_argument("--try-ports", default=os.environ.get("SJTU_MEETING_ATTACH_PORTS", DEFAULT_ATTACH_PORTS),
                        help="默认先尝试这些已有浏览器 DevTools 端口，逗号分隔。默认 9222,9223,9224。")
    parser.add_argument("--skip-existing", action="store_true",
                        help="不尝试已有浏览器调试端口，直接打开专用浏览器。")
    parser.add_argument("--existing-timeout", type=int, default=8,
                        help="每个已有浏览器端口最多探测秒数，默认 8。")
    parser.add_argument("--timeout", type=int, default=300,
                        help="等待用户登录的最长秒数，默认 300。")
    parser.add_argument("--no-verify", action="store_true",
                        help="只写凭据，不调用会议 API 验证。")
    parser.add_argument("--manual-guide", action="store_true",
                        help="只打印手动 DevTools 复制 token 的步骤，不启动浏览器。")
    return parser


def run_setup(args):
    if args.attach_port:
        port = args.attach_port
        print(f"连接已有本机浏览器调试端口 127.0.0.1:{port}。")
        wait_for_debug_endpoint(port, timeout=20)
        result = wait_for_token(port, timeout=args.timeout)
        return finish_setup(args, result)
    else:
        if not args.skip_existing:
            existing_result = try_existing_debug_ports(args)
            if existing_result is not None:
                return existing_result
            print("未在已有浏览器调试端口找到可用登录态；改为打开专用浏览器窗口。")

        port = args.port or pick_free_port()
        browser_path = find_browser(args.browser, args.browser_path)
        profile_dir = expand(args.profile_dir)
        launch_browser(browser_path, profile_dir, port)
        print(f"已打开专用浏览器窗口：{os.path.basename(browser_path)}")
        print(f"profile: {profile_dir}")
        print("请在这个窗口完成 SJTU SSO 登录；看到会议平台页面后保持窗口打开。")

    wait_for_debug_endpoint(port, timeout=20)
    result = wait_for_token(port, timeout=args.timeout)
    return finish_setup(args, result)


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.manual_guide:
        print(manual_fallback_text(expand(args.creds)))
        return 0
    try:
        return run_setup(args)
    except SetupError as exc:
        print(f"失败: {exc}", file=sys.stderr)
        print(manual_fallback_text(expand(args.creds)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(130)
