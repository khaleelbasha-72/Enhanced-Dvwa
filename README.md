# 🛡️ Enhanced DVWA — Security Training Lab

A fully functional **Deliberately Vulnerable Web Application (DVWA)** built in Python for learning and practicing **web security and penetration testing**.

---

## 🚀 Features

* 🔓 23+ Vulnerability Modules
* 🎯 Hands-on exploitation environment
* ⚙️ Multiple security levels (Low / Medium / High)
* 🧪 Real-world attack simulations
* 🔐 Session & authentication system
* 📊 Interactive UI with payload suggestions

---

## 🧠 Vulnerabilities Covered

* SQL Injection & Blind SQLi
* XSS (Reflected, Stored, DOM)
* CSRF
* File Upload (RCE)
* File Inclusion (LFI)
* Command Injection
* IDOR
* SSRF
* XXE
* SSTI
* JWT Attacks
* CORS Misconfig
* Clickjacking
* Brute Force & Rate Limiting
* And more...

---

## 🏗️ Architecture

* Backend: Python (http.server)
* Database: SQLite
* Frontend: HTML, CSS, JavaScript
* Session Management: Custom token-based system

---

## ⚙️ Installation

```bash
git clone https://github.com/yourusername/enhanced-dvwa
cd enhanced-dvwa
python dvwa_khalil_v1.py
```

Open in browser:

```
http://127.0.0.1:8000
```

---

## 🔑 Default Credentials

```
admin / password
gordonb / abc123
pablo / letmein
smithy / password
alice / password123
```

---

## 🎮 How to Use

1. Select vulnerability module
2. Try payloads (provided in UI)
3. Observe behavior at different security levels
4. Learn exploitation techniques

---

## 🧪 Example Attacks

* SQL Injection:

```sql
1 OR 1=1-- -
```

* XSS:

```html
<script>alert(1)</script>
```

* File Upload:

```php
<?php system($_GET['cmd']); ?>
```

---

## 🔐 Security Levels

| Level  | Description           |
| ------ | --------------------- |
| Low    | Fully vulnerable      |
| Medium | Partial protections   |
| High   | Secure implementation |

---

## ⚠️ Disclaimer

This project is for **educational purposes only**.
Run only on **localhost or isolated environments**.

---

## 📚 Learning Outcome

* Understand **OWASP Top 10 vulnerabilities**
* Practice **real-world exploitation techniques**
* Learn **secure coding practices**

---

## 👨‍💻 Author

**G Khaleel Basha**

---

## ⭐ Support

If you found this useful, give it a ⭐ and share!
