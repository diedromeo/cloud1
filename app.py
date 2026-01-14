
import os
import time
import zipfile
import threading
import requests
import mimetypes
from flask import Flask, request, send_file, render_template_string, jsonify, abort, Response, redirect, url_for, session, make_response
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

# ==========================================
# CONFIGURATION & SETUP
# ==========================================
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# VULNERABILITY: Weak Secret Key (Hardcoded)
app.config['SECRET_KEY'] = 'tegh-cloud-super-secret-key-12345'

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Database Setup
engine = create_engine('sqlite:///database.db', connect_args={'check_same_thread': False})
db_session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

# ==========================================
# MODELS
# ==========================================
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String) # VULNERABILITY: Plaintext password storage (simulated bad practice)

class FileRecord(Base):
    __tablename__ = 'files'
    id = Column(Integer, primary_key=True)
    filename = Column(String)
    filepath = Column(String)
    folder = Column(String)
    content_type = Column(String)
    processed = Column(Boolean, default=False)
    # Could link to user, but for "Public CDN" simulation we keep it loose
    
Base.metadata.create_all(engine)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

# ==========================================
# VULNERABLE LOGIC (WORKER & UTILS)
# ==========================================

def dangerous_path_join(base, *paths):
    """
    VULNERABILITY: Arbitrary File Write / Path Traversal
    Does not check if the resulting path is within the base directory.
    """
    return os.path.join(base, *paths)

def process_file_task(file_id):
    """
    Background worker that processes files.
    VULNERABILITY: SSRF & Zip Slip
    """
    session_scoped = db_session() 
    try:
        file_record = session_scoped.query(FileRecord).filter_by(id=file_id).first()
        if not file_record: return

        print(f"[*] Processing file: {file_record.filepath}")
        
        # 1. Zip Slip
        if file_record.filename.endswith('.zip'):
            try:
                with zipfile.ZipFile(file_record.filepath, 'r') as zf:
                    for member in zf.namelist():
                        extract_path = os.path.join(app.config['UPLOAD_FOLDER'], member)
                        os.makedirs(os.path.dirname(extract_path), exist_ok=True)
                        with open(extract_path, 'wb') as f:
                            f.write(zf.read(member))
            except Exception as e:
                print(f"[-] Zip processing failed: {e}")

        # 2. SSRF
        mime_type = file_record.content_type or 'application/octet-stream'
        if 'text' in mime_type or file_record.filename.endswith('.txt'):
            try:
                with open(file_record.filepath, 'r', errors='ignore') as f:
                    content = f.read()
                    import re
                    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', content)
                    for url in urls:
                        try:
                            requests.get(url, timeout=5)
                        except: pass
            except: pass

        file_record.processed = True
        session_scoped.commit()
    except:
        session_scoped.rollback()
    finally:
        session_scoped.close()
        db_session.remove()

def allowed_file(filename):
    # VULNERABILITY: Upload Validation Bypass (Double ext or spoofing)
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip'}
    parts = filename.split('.')
    if len(parts) > 1:
        return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    return False

# ==========================================
# MIDDLEWARE VULNERABILITIES
# ==========================================
@app.after_request
def add_security_headers(response):
    # Standard Security Headers (Simulated Production Readiness)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # VULNERABILITY: Cache Control
    # Private user data might be cached by intermediate proxies
    if request.path.startswith('/api/files'):
        response.headers['Cache-Control'] = 'public, max-age=3600'
    else:
        # For other pages, we can be "secure"
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        
    return response

# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def landing():
    return render_template_string(HTML_LANDING)

@app.route('/about')
def about():
    return render_template_string(HTML_ABOUT)

@app.route('/pricing')
def pricing():
    return render_template_string(HTML_PRICING)

@app.route('/dashboard')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template_string(HTML_DASHBOARD)

# ... (Previous routes like /login, /signup, /logout remain similar but redirect to /dashboard on success)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            error = "User not found"
        elif user.password != pwd:
            error = "Invalid password"
        else:
            session['user_id'] = user.id
            session['email'] = user.email
            return redirect(url_for('index'))
            
    return render_template_string(HTML_AUTH, mode='Login', error=error)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            error = "Email already exists"
        else:
            new_user = User(email=email, password=pwd)
            db_session.add(new_user)
            db_session.commit()
            
            session['user_id'] = new_user.id
            session['email'] = new_user.email
            return redirect(url_for('index'))
            
    return render_template_string(HTML_AUTH, mode='Sign Up', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Use provided folder or default
    folder = request.form.get('folder', 'mixed')
    folder = secure_filename(folder) # Basic sanitization
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_dir = os.path.join(app.config['UPLOAD_FOLDER'], folder)
        
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        filepath = os.path.join(save_dir, filename)
        file.save(filepath)
        
        new_file = FileRecord(
            filename=filename,
            filepath=filepath,
            folder=folder,
            content_type=file.content_type
        )
        db_session.add(new_file)
        db_session.commit()
        
        # Trigger background processing
        threading.Thread(target=process_file_task, args=(new_file.id,)).start()
        
        return jsonify({'message': 'File uploaded', 'id': new_file.id})
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/api/files')
def list_files_route():
    # Only show files. In a real app we might filter by user.
    files = FileRecord.query.all()
    out = []
    for f in files:
        out.append({
            'filename': f.filename,
            'folder': f.folder,
            'url': f'/api/download?path={f.folder}/{f.filename}',
            'processed': f.processed
        })
    return jsonify(out)

@app.route('/api/download')
def download_file_route():
    path = request.args.get('path')
    if not path:
        return abort(400, "Path required")
    
    # VULNERABILITY: Path Traversal Enabled
    # Allow accessing files outside the upload directory (LFI)
    base_dir = os.path.abspath(app.config['UPLOAD_FOLDER'])
    target_path = os.path.abspath(os.path.join(base_dir, path))
    
    # EXCEPTION: Explicitly hide/protect app.py
    if os.path.basename(target_path).lower() == 'app.py':
        return abort(403, "Access denied: Source code is protected")

    if not os.path.exists(target_path):
        return abort(404, "File not found")
        
    return send_file(target_path, as_attachment=True)

@app.route('/internal-metadata')
def internal_metadata():
    return jsonify({
        "service": "metadata-worker-v1",
        "cpu_usage": "12%",
        "memory": "512MB",
        "uptime": "48h",
        "node_id": "worker-77a"
    })

# TEMPLATES

COMMON_HEAD = """
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tegh Cloud | Enterprise Storage Solutions</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root {
            --primary: #0f172a;
            --accent: #3b82f6; --accent-hover: #2563eb;
            --bg: #ffffff;
            --text-main: #1e293b; --text-muted: #64748b;
            --grad-1: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
            --grad-dark: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body { 
            font-family: 'Inter', sans-serif; 
            background: var(--bg); 
            color: var(--text-main); 
            overflow-x: hidden;
            scroll-behavior: smooth;
            display: flex; flex-direction: column; min-height: 100vh;
        }
        
        h1, h2, h3, h4, .brand { font-family: 'Outfit', sans-serif; }
        a { text-decoration: none; color: inherit; transition: 0.3s; }
        
        /* PARALLAX & ANIMATIONS */
        .parallax {
            background-attachment: fixed;
            background-position: center;
            background-repeat: no-repeat;
            background-size: cover;
            position: relative;
        }
        
        .fade-in-up { animation: fadeInUp 0.8s ease-out forwards; opacity: 0; transform: translateY(20px); }
        .delay-1 { animation-delay: 0.2s; }
        .delay-2 { animation-delay: 0.4s; }
        
        @keyframes fadeInUp {
            to { opacity: 1; transform: translateY(0); }
        }

        /* COMPONENT STYLES */
        nav {
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid rgba(0,0,0,0.05);
            padding: 1.2rem 5%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 1000;
            transition: all 0.3s;
        }
        
        .brand { font-size: 1.6rem; font-weight: 800; color: var(--primary); display: flex; align-items: center; gap: 0.5rem; letter-spacing: -0.5px; }
        .brand span { color: var(--accent); }
        
        .nav-links { display: flex; gap: 2.5rem; align-items: center; font-weight: 500; font-size: 0.95rem; color: var(--text-muted); }
        .nav-links a:hover { color: var(--primary); transform: translateY(-1px); }
        
        .btn { 
            background: var(--primary); color: white; border: none; 
            padding: 0.8rem 1.8rem; border-radius: 50px; 
            font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 0.5rem;
            box-shadow: 0 4px 14px 0 rgba(15, 23, 42, 0.2);
            transition: all 0.2s;
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4); background: var(--accent); }
        .btn-outline { background: transparent; border: 1px solid #e2e8f0; color: var(--primary); box-shadow: none; }
        .btn-outline:hover { border-color: var(--primary); background: #f8fafc; }

        .container { max-width: 1280px; margin: 0 auto; padding: 0 1.5rem; position: relative; width: 100%; }
        
        /* FOOTER */
        footer { background: #0f172a; color: white; padding: 5rem 5% 2rem; position: relative; overflow: hidden; margin-top: auto; }
        .footer-grid { display: grid; grid-template-columns: 2fr 1fr 1fr 1.5fr; gap: 4rem; max-width: 1200px; margin: 0 auto; relative; z-index: 10; }
        .footer-col h4 { margin-bottom: 1.5rem; font-size: 1.1rem; color: white; opacity: 0.9; }
        .footer-col a { display: block; margin-bottom: 0.8rem; color: #94a3b8; font-size: 0.95rem; }
        .footer-col a:hover { color: white; padding-left: 5px; }
        .newsletter input { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 0.8rem; border-radius: 8px; width: 100%; margin-bottom: 0.5rem; }
        .newsletter input:focus { outline: none; border-color: var(--accent); }
    </style>
</head>
"""

NAV_HTML = """
<nav>
    <a href="/" class="brand"><i data-lucide="cloud"></i> Tegh<span>Cloud</span></a>
    <div class="nav-links">
        <a href="/">Product</a>
        <a href="/pricing">Pricing</a>
        <a href="/about">Mission</a>
        {% if session.get('user_id') %}
            <a href="/dashboard">Console</a>
            <a href="/logout" style="color: #ef4444;">Sign Out</a>
        {% else %}
            <a href="/login">Log In</a>
            <a href="/signup" class="btn">Get Started</a>
        {% endif %}
    </div>
</nav>
<script>lucide.createIcons();</script>
"""

HTML_PRICING = """
<!DOCTYPE html>
<html lang="en">
""" + COMMON_HEAD + """
<body>

""" + NAV_HTML + """

<div style="text-align: center; padding: 6rem 1rem 4rem; background: var(--grad-1);">
    <h1 style="font-size: 3.5rem; margin-bottom: 1rem;">Simple, Transparent Pricing</h1>
    <p style="font-size: 1.25rem; color: var(--text-muted); padding-bottom: 2rem;">Pay for what you use. No hidden fees.</p>
    
    <div class="container" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 2rem; max-width: 1000px; align-items: center;">
        
        <!-- FREE TIER -->
        <div class="fade-in-up delay-1" style="background: white; border: 1px solid #e2e8f0; border-radius: 16px; padding: 2.5rem; text-align: left; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <h3 style="color: var(--text-muted); font-size: 1.1rem; margin-bottom: 0.5rem;">Develper</h3>
            <div style="font-size: 3rem; font-weight: 800; color: var(--primary); margin-bottom: 1.5rem;">$0<span style="font-size: 1rem; font-weight: 500; color: var(--text-muted);">/mo</span></div>
            <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 2rem;">Perfect for testing vulnerabilities and learning exploits.</p>
            
            <ul style="list-style: none; margin-bottom: 2rem; display: grid; gap: 1rem;">
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#22c55e"></i> 1GB Storage</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#22c55e"></i> Public Buckets</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#22c55e"></i> No API Keys Needed</li>
            </ul>
            <a href="/signup" class="btn-outline" style="width: 100%; justify-content: center; padding: 0.8rem; border-radius: 8px; font-weight: 600;">Get Started</a>
        </div>
        
        <!-- PRO TIER -->
        <div class="fade-in-up" style="background: #0f172a; color: white; border-radius: 16px; padding: 3rem 2.5rem; text-align: left; box-shadow: 0 20px 40px -10px rgba(15, 23, 42, 0.4); position: relative; transform: scale(1.05);">
            <div style="position: absolute; top: -12px; left: 50%; transform: translateX(-50%); background: #3b82f6; color: white; padding: 0.3rem 1rem; border-radius: 99px; font-size: 0.8rem; font-weight: 600;">RECOMMENDED</div>
            <h3 style="color: #94a3b8; font-size: 1.1rem; margin-bottom: 0.5rem;">Pro Team</h3>
            <div style="font-size: 3rem; font-weight: 800; color: white; margin-bottom: 1.5rem;">$29<span style="font-size: 1rem; font-weight: 500; color: #94a3b8;">/mo</span></div>
            <p style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 2rem;">For teams that need more arbitrary file writes.</p>
            
             <ul style="list-style: none; margin-bottom: 2rem; display: grid; gap: 1rem;">
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#3b82f6"></i> 1TB Storage</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#3b82f6"></i> Auto-Unzip Support</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#3b82f6"></i> Faster SSRF Responses</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#3b82f6"></i> Prioritized Exploits</li>
            </ul>
            <a href="/signup" class="btn" style="width: 100%; justify-content: center; padding: 0.8rem; border-radius: 8px;">Start Free Trial</a>
        </div>
        
        <!-- ENTERPRISE TIER -->
        <div class="fade-in-up delay-2" style="background: white; border: 1px solid #e2e8f0; border-radius: 16px; padding: 2.5rem; text-align: left; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <h3 style="color: var(--text-muted); font-size: 1.1rem; margin-bottom: 0.5rem;">Enterprise</h3>
            <div style="font-size: 3rem; font-weight: 800; color: var(--primary); margin-bottom: 1.5rem;">Custom</div>
            <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 2rem;">Dedicated bad practices for large organizations.</p>
            
             <ul style="list-style: none; margin-bottom: 2rem; display: grid; gap: 1rem;">
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#22c55e"></i> Unlimited Buckets</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#22c55e"></i> 24/7 Incident Ignoring</li>
                <li style="display: flex; gap: 0.5rem; align-items: center;"><i data-lucide="check" size="16" color="#22c55e"></i> On-Prem Deployment</li>
            </ul>
            <a href="/about" class="btn-outline" style="width: 100%; justify-content: center; padding: 0.8rem; border-radius: 8px; font-weight: 600;">Contact Sales</a>
        </div>
    </div>
    
    <div style="margin-top: 4rem;">
        <h3 style="margin-bottom: 1rem;">Compare Features</h3>
        <p style="color: var(--text-muted);">View our full feature comparison matrix in the <a href="/about" style="color: var(--accent); font-weight: 600;">docs</a>.</p>
    </div>
</div>

<footer>
    <div class="footer-grid">
        <div class="footer-col">
            <div class="brand" style="color: white; margin-bottom: 1.5rem;"><i data-lucide="cloud"></i> Tegh<span>Cloud</span></div>
            <p style="color: #94a3b8; line-height: 1.6; font-size: 0.95rem;">
                Building the future of insecure infrastructure. Since 2024, we've simulated over 10 million vulnerabilities.
            </p>
        </div>
        <div class="footer-col">
            <h4>Product</h4>
            <a href="#">Simulated S3</a>
            <a href="#">Edge Worker</a>
            <a href="/pricing">Pricing</a>
        </div>
        <div class="footer-col">
            <h4>Company</h4>
            <a href="/about">About</a>
            <a href="#">Bug Bounty</a>
            <a href="#">Careers</a>
        </div>
        <div class="footer-col newsletter">
            <h4>Stay Updated</h4>
             <p style="margin-bottom: 1rem; font-size: 0.9rem; color: #94a3b8;">Subscribe to our zero-day feed.</p>
            <form action="" onclick="alert('Subscribed to Null!')">
                <input type="email" placeholder="Enter your email">
                <button type="button" class="btn" style="width: 100%; justify-content: center; padding: 0.6rem;">Subscribe</button>
            </form>
        </div>
    </div>
     <div style="text-align: center; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 4rem; padding-top: 2rem; color: #475569; font-size: 0.85rem;">
        &copy; 2026 Tegh Cloud Inc. All rights reserved. Do not use in production.
    </div>
</footer>
<script>lucide.createIcons();</script>
</body>
</html>
"""

HTML_LANDING = """
<!DOCTYPE html>
<html lang="en">
""" + COMMON_HEAD + """
<body>

""" + NAV_HTML + """

<!-- HERO SECTION -->
<div style="background: var(--grad-1); padding: 8rem 0 6rem; position: relative; overflow: hidden;">
    <div class="container" style="text-align: center; position: relative; z-index: 10;">
        <div class="fade-in-up">
            <span style="background: rgba(59, 130, 246, 0.1); color: var(--accent); padding: 0.4rem 1rem; border-radius: 99px; font-weight: 600; font-size: 0.85rem; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 1.5rem; display: inline-block;">v8.2 Now Live</span>
            <h1 style="font-size: 4.5rem; line-height: 1.1; margin-bottom: 1.5rem; letter-spacing: -2px; color: var(--primary);">
                Store globally.<br>Access <span style="background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">instantly.</span>
            </h1>
            <p style="font-size: 1.25rem; color: var(--text-muted); max-width: 650px; margin: 0 auto 3rem; line-height: 1.6;">
                The enterprise standard for object storage. Infinite scalability, 
                bank-grade security simulation, and zero-latency CDN integration.
            </p>
            <div style="display: flex; gap: 1rem; justify-content: center;">
                <a href="/signup" class="btn" style="padding: 1rem 2.5rem; font-size: 1.1rem;">Start Building Free <i data-lucide="arrow-right" style="width:18px; margin-left:5px;"></i></a>
                <a href="/about" class="btn btn-outline" style="padding: 1rem 2.5rem; font-size: 1.1rem;">Read Documentation</a>
            </div>
        </div>
        
        <!-- MOCKUP -->
        <div class="fade-in-up delay-2" style="margin-top: 5rem; perspective: 1000px;">
            <div style="background: #fff; border-radius: 12px; box-shadow: 0 50px 100px -20px rgba(50, 50, 93, 0.25), 0 30px 60px -30px rgba(0, 0, 0, 0.3); max-width: 900px; margin: 0 auto; overflow: hidden; border: 1px solid #e2e8f0; transform: rotateX(2deg);">
                <div style="background: #f8fafc; padding: 0.8rem 1rem; border-bottom: 1px solid #e2e8f0; display: flex; gap: 0.5rem; align-items: center;">
                    <div style="width: 10px; height: 10px; border-radius: 50%; background: #ef4444;"></div>
                    <div style="width: 10px; height: 10px; border-radius: 50%; background: #f59e0b;"></div>
                    <div style="width: 10px; height: 10px; border-radius: 50%; background: #22c55e;"></div>
                    <div style="margin-left: 1rem; font-size: 0.8rem; color: #94a3b8; background: white; padding: 0.2rem 1rem; border-radius: 4px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">files.targetlab.com/dashboard</div>
                </div>
                <div style="padding: 3rem; text-align: left;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 2rem;">
                        <div style="width: 200px; height: 10px; background: #e2e8f0; border-radius: 4px;"></div>
                        <div style="width: 100px; height: 30px; background: var(--primary); border-radius: 6px;"></div>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;">
                        <div style="height: 100px; background: #f1f5f9; border-radius: 8px;"></div>
                        <div style="height: 100px; background: #f1f5f9; border-radius: 8px;"></div>
                        <div style="height: 100px; background: #f1f5f9; border-radius: 8px;"></div>
                        <div style="height: 100px; background: #f1f5f9; border-radius: 8px;"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- PARALLAX / QUOTE -->
<div class="parallax" style="background-image: url('https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop'); padding: 8rem 0; position: relative;">
    <div style="position: absolute; inset: 0; background: rgba(15, 23, 42, 0.8);"></div>
    <div class="container" style="position: relative; z-index: 10; text-align: center; color: white;">
        <h2 style="font-size: 2.5rem; margin-bottom: 1.5rem; font-weight: 300;">"Finally, a storage solution that doesn't verify anything."</h2>
        <p style="font-size: 1.2rem; opacity: 0.8; margin-bottom: 2rem;">- Chief Security Officer, Vulnerable Corp</p>
        <div style="display: flex; gap: 3rem; justify-content: center; opacity: 0.6;">
            <div><i data-lucide="shield-off" size="32"></i><br><small>Zero Checks</small></div>
            <div><i data-lucide="zap" size="32"></i><br><small>Instant Access</small></div>
            <div><i data-lucide="globe" size="32"></i><br><small>Global CDN</small></div>
        </div>
    </div>
</div>

<!-- FEATURES -->
<div class="container" style="padding: 6rem 1.5rem;">
    <div style="text-align: center; margin-bottom: 5rem;">
        <h2 style="font-size: 2.5rem; margin-bottom: 1rem; color: var(--primary);">Engineered for Control</h2>
        <p style="color: var(--text-muted); font-size: 1.1rem;">Everything you need to manage your digital assets, and maybe some things you shouldn't.</p>
    </div>
    
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 3rem;">
        <div style="padding: 2rem; border-radius: 12px; background: white; border: 1px solid #e2e8f0; transition: 0.3s;">
            <div style="width: 50px; height: 50px; background: #eff6ff; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: var(--accent); margin-bottom: 1.5rem;">
                <i data-lucide="network"></i>
            </div>
            <h3 style="font-size: 1.3rem; margin-bottom: 0.5rem;">Edge CDN</h3>
            <p style="color: var(--text-muted); line-height: 1.6;">Content is replicated across 0 regions for maximum latency minimization (simulated).</p>
        </div>
        <div style="padding: 2rem; border-radius: 12px; background: white; border: 1px solid #e2e8f0; transition: 0.3s; box-shadow: 0 10px 40px -10px rgba(0,0,0,0.1);">
            <div style="width: 50px; height: 50px; background: #eff6ff; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: var(--accent); margin-bottom: 1.5rem;">
                <i data-lucide="bot"></i>
            </div>
            <h3 style="font-size: 1.3rem; margin-bottom: 0.5rem;">Auto-Processing</h3>
            <p style="color: var(--text-muted); line-height: 1.6;">Our background workers tirelessly extract zips and fetch internal metadata.</p>
        </div>
        <div style="padding: 2rem; border-radius: 12px; background: white; border: 1px solid #e2e8f0; transition: 0.3s;">
            <div style="width: 50px; height: 50px; background: #eff6ff; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: var(--accent); margin-bottom: 1.5rem;">
                <i data-lucide="lock"></i>
            </div>
            <h3 style="font-size: 1.3rem; margin-bottom: 0.5rem;">Flexible Security</h3>
            <p style="color: var(--text-muted); line-height: 1.6;">We believe in the "Honor System". If you say you're admin, who are we to judge?</p>
        </div>
    </div>
</div>

<footer>
    <div class="footer-grid">
        <div class="footer-col">
            <div class="brand" style="color: white; margin-bottom: 1.5rem;"><i data-lucide="cloud"></i> Tegh<span>Cloud</span></div>
            <p style="color: #94a3b8; line-height: 1.6; font-size: 0.95rem;">
                Building the future of insecure infrastructure. Since 2024, we've simulated over 10 million vulnerabilities.
            </p>
            <div style="display: flex; gap: 1rem; margin-top: 2rem; opacity: 0.7;">
                <i data-lucide="twitter"></i> <i data-lucide="github"></i> <i data-lucide="linkedin"></i>
            </div>
        </div>
        <div class="footer-col">
            <h4>Product</h4>
            <a href="#">Simulated S3</a>
            <a href="#">Edge Worker</a>
            <a href="#">Vulnerability List</a>
        </div>
        <div class="footer-col">
            <h4>Company</h4>
            <a href="/about">About</a>
            <a href="#">Bug Bounty</a>
            <a href="#">Careers</a>
        </div>
        <div class="footer-col newsletter">
            <h4>Stay Updated</h4>
            <p style="margin-bottom: 1rem; font-size: 0.9rem; color: #94a3b8;">Subscribe to our zero-day feed.</p>
            <form action="" onclick="alert('Subscribed to Null!')">
                <input type="email" placeholder="Enter your email">
                <button type="button" class="btn" style="width: 100%; justify-content: center; padding: 0.6rem;">Subscribe</button>
            </form>
        </div>
    </div>
    <div style="text-align: center; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 4rem; padding-top: 2rem; color: #475569; font-size: 0.85rem;">
        &copy; 2026 Tegh Cloud Inc. All rights reserved. Do not use in production.
    </div>
</footer>
<script>lucide.createIcons();</script>
</body>
</html>
"""

HTML_ABOUT = """
<!DOCTYPE html>
<html lang="en">
""" + COMMON_HEAD + """
<body>

""" + NAV_HTML + """

<!-- HEADER -->
<div style="background: var(--grad-dark); color: white; padding: 6rem 0; text-align: center;">
    <div class="container">
        <h1 style="font-size: 3.5rem; margin-bottom: 1rem;">We are Tegh Cloud.</h1>
        <p style="font-size: 1.25rem; opacity: 0.8; max-width: 600px; margin: 0 auto;">
            Democratizing file storage vulnerabilities for security researchers everywhere.
        </p>
    </div>
</div>

<!-- IMAGE PARALLAX -->
<div class="parallax" style="height: 400px; background-image: url('https://images.unsplash.com/photo-1558494949-efc52728101c?q=80&w=2070&auto=format&fit=crop');"></div>

<!-- CONTENT -->
<div class="container" style="padding: 5rem 1.5rem; max-width: 900px;">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4rem; align-items: start;">
        <div>
            <h2 style="font-size: 2rem; margin-bottom: 1.5rem; color: var(--primary);">The Mission</h2>
            <p style="color: var(--text-muted); line-height: 1.8; margin-bottom: 1.5rem;">
                Tegh Cloud wasn't built to be secure. It was built to be <b style="color: var(--primary);">educational</b>. 
                We provide a realistic simulation of a modern cloud environment, complete with the subtle flaws that plague real-world applications.
            </p>
            <p style="color: var(--text-muted); line-height: 1.8;">
                From SSRF to Zip Slip, our architecture is painstakingly crafted to fail in the most interesting ways possible.
            </p>
        </div>
        <div style="background: #f8fafc; padding: 2rem; border-radius: 12px; border: 1px solid #e2e8f0;">
            <div style="display: flex; gap: 1rem; margin-bottom: 2rem;">
                <div style="width: 4rem; height: 4rem; background: #cbd5e1; border-radius: 50%; overflow: hidden;">
                    <img src="https://ui-avatars.com/api/?name=Parth+Bhandari&background=0D8ABC&color=fff" width="100%">
                </div>
                <div>
                    <h4 style="font-size: 1.1rem; margin-bottom: 0.2rem;">Parth Bhandari</h4>
                    <span style="font-size: 0.9rem; color: var(--accent); font-weight: 500;">Founder & Architect</span>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">"I like my buckets public."</p>
                </div>
            </div>
            
             <div style="display: flex; gap: 1rem;">
                <div style="width: 4rem; height: 4rem; background: #cbd5e1; border-radius: 50%; overflow: hidden;">
                     <img src="https://ui-avatars.com/api/?name=Antigravity+AI&background=0f172a&color=fff" width="100%">
                </div>
                <div>
                    <h4 style="font-size: 1.1rem; margin-bottom: 0.2rem;">Antigravity AI</h4>
                    <span style="font-size: 0.9rem; color: var(--accent); font-weight: 500;">Security Lead</span>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">"This code is safely unsafe."</p>
                </div>
            </div>
        </div>
    </div>
</div>

<footer>
     <div class="footer-grid">
        <div class="footer-col">
            <div class="brand" style="color: white; margin-bottom: 1.5rem;"><i data-lucide="cloud"></i> Tegh<span>Cloud</span></div>
        </div>
        <div class="footer-col"></div>
        <div class="footer-col"></div>
         <div class="footer-col">
            <p style="color: #64748b;">(c) 2026. Security Research Purpose Only.</p>
         </div>
     </div>
</footer>
<script>lucide.createIcons();</script>
</body>
</html>
"""

# ... (Auth & Dashboard Templates remain similar but using new CSS/Scripts)
HTML_AUTH = """
<!DOCTYPE html>
<html lang="en">
""" + COMMON_HEAD + """
<body style="background: var(--bg); display: flex; flex-direction: column;">
""" + NAV_HTML + """
    <div style="flex: 1; display: flex; align-items: center; justify-content: center; padding: 4rem 1rem; background: var(--grad-1);">
        <div class="fade-in-up" 
             style="background: white; width: 100%; max-width: 420px; padding: 2.5rem; border-radius: 16px; box-shadow: 0 10px 40px -10px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
            
            <div style="text-align: center; margin-bottom: 2rem;">
                <h2 style="font-size: 1.8rem; margin-bottom: 0.5rem;">{{ mode }}</h2>
                <p style="color: var(--text-muted); font-size: 0.95rem;">Enter your credentials to access the console</p>
            </div>
            
            {% if error %}
                <div style="background: #fef2f2; color: #dc2626; padding: 0.8rem; border-radius: 8px; margin-bottom: 1.5rem; font-size: 0.9rem; text-align: center; border: 1px solid #fecaca; display: flex; align-items: center; gap: 0.5rem; justify-content: center;">
                    <i data-lucide="alert-circle" size="16"></i> {{ error }}
                </div>
            {% endif %}
            
            <form method="POST">
                <label style="display: block; margin-bottom: 0.5rem; font-weight: 500; font-size: 0.9rem;">Email Address</label>
                <div style="position: relative; margin-bottom: 1.2rem;">
                    <input type="email" name="email" required placeholder="name@company.com" 
                           style="width: 100%; padding: 0.8rem 0.8rem 0.8rem 2.5rem; border: 1px solid #e2e8f0; border-radius: 8px; outline: none; transition: 0.2s;">
                    <i data-lucide="mail" size="16" style="position: absolute; left: 12px; top: 12px; color: #94a3b8;"></i>
                </div>
                
                <label style="display: block; margin-bottom: 0.5rem; font-weight: 500; font-size: 0.9rem;">Password</label>
                <div style="position: relative; margin-bottom: 1.5rem;">
                    <input type="password" name="password" required 
                           style="width: 100%; padding: 0.8rem 0.8rem 0.8rem 2.5rem; border: 1px solid #e2e8f0; border-radius: 8px; outline: none; transition: 0.2s;">
                    <i data-lucide="lock" size="16" style="position: absolute; left: 12px; top: 12px; color: #94a3b8;"></i>
                </div>
                
                <button class="btn" style="width: 100%; justify-content: center; padding: 0.9rem;">{{ mode }}</button>
            </form>
            
            <p style="margin-top: 1.5rem; text-align: center; font-size: 0.9rem; color: var(--text-muted);">
                {% if mode == 'Login' %}
                    No account? <a href="/signup" style="color: var(--accent); font-weight: 600;">Create one free</a>
                {% else %}
                    Have an account? <a href="/login" style="color: var(--accent); font-weight: 600;">Log in</a>
                {% endif %}
            </p>
        </div>
    </div>
<script>lucide.createIcons();</script>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
""" + COMMON_HEAD + """
<body style="background: #f8fafc;">

""" + NAV_HTML + """

<div class="container" style="display: grid; grid-template-columns: 320px 1fr; gap: 2rem; padding-top: 2rem; padding-bottom: 4rem;">
    <!-- SIDEBAR -->
    <div class="sidebar fade-in-up">
        <div style="background: white; padding: 1.5rem; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02); margin-bottom: 1.5rem;">
            <h3 style="margin-bottom: 1.2rem; font-size: 1.1rem; display: flex; align-items: center; gap: 0.5rem;">
                <i data-lucide="upload-cloud" size="20" color="var(--accent)"></i> Upload File
            </h3>
            
            <div id="drop-zone" style="border: 2px dashed #cbd5e1; border-radius: 8px; padding: 2rem 1rem; text-align: center; cursor: pointer; transition: 0.2s; background: #f8fafc;">
                 <i data-lucide="file-plus" style="margin-bottom: 0.5rem; color: #64748b;"></i>
                 <p style="color: var(--text-muted); font-size: 0.9rem; font-weight: 500;">Click or Drop files</p>
                 <input type="file" id="file-input" style="display: none;">
            </div>
            
            <div style="margin-top: 1rem;">
                <label style="font-size: 0.85rem; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 0.4rem;">Target Bucket</label>
                <div style="position: relative;">
                    <i data-lucide="folder" size="14" style="position: absolute; left: 10px; top: 11px; color: #94a3b8;"></i>
                    <input type="text" id="upload-folder" value="uploads" style="width: 100%; padding: 0.6rem 0.6rem 0.6rem 2.2rem; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 0.9rem;">
                </div>
            </div>
            
            <button id="upload-btn" class="btn" style="width: 100%; margin-top: 1rem; justify-content: center; padding: 0.7rem;">Init Transfer</button>
            <div id="upload-status" style="margin-top: 1rem; text-align: center; font-size: 0.85rem; font-weight: 500; min-height: 1.2rem;"></div>
        </div>
        
         <div style="background: linear-gradient(145deg, #0f172a 0%, #334155 100%); color: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 10px 30px -5px rgba(15, 23, 42, 0.3);">
            <h3 style="color: white; margin-bottom: 1rem; font-size: 1rem; opacity: 0.9; text-transform: uppercase; letter-spacing: 1px;">System Health</h3>
            <div style="font-size: 0.85rem; display: grid; gap: 0.8rem;">
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem;">
                    <span style="opacity: 0.7;">Edge Node</span> <span>US-East-1</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem;">
                    <span style="opacity: 0.7;">Worker Status</span> <span style="color: #4ade80;">Online</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="opacity: 0.7;">Storage Used</span> <span>0.0 TB</span>
                </div>
            </div>
        </div>
    </div>

    <!-- MAIN CONTENT -->
    <div class="main-content fade-in-up delay-1">
        <div style="background: white; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02); min-height: 600px; display: flex; flex-direction: column;">
            <div style="padding: 1.5rem; border-bottom: 1px solid #f1f5f9; display: flex; justify-content: space-between; align-items: center;">
                <h2 style="font-size: 1.2rem; display: flex; align-items: center; gap: 0.5rem;">
                    <i data-lucide="hard-drive" color="var(--primary)"></i> File Explorer
                </h2>
                <button onclick="loadFiles()" class="btn-outline" style="padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem;">
                    <i data-lucide="refresh-cw" size="14"></i> Refresh
                </button>
            </div>
            
            <div id="file-grid" style="padding: 1.5rem; display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1.5rem;">
                <!-- Files injected here -->
            </div>
            
            <!-- Empty State (hidden by default, shown if needed logic) -->
            <div id="empty-state" style="display: none; text-align: center; padding: 4rem; color: #94a3b8;">
                <i data-lucide="inbox" size="48" style="opacity: 0.5; margin-bottom: 1rem;"></i>
                <p>No files found in this bucket.</p>
            </div>
        </div>
    </div>
</div>

<script>
    // JS Logic (Same as before, just updated class names/icons)
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const statusDiv = document.getElementById('upload-status');

    dropZone.onclick = () => fileInput.click();
    fileInput.onchange = () => { if(fileInput.files.length) statusDiv.textContent = `Selected: ${fileInput.files[0].name}`; };
    
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--accent)'; dropZone.style.background = '#eff6ff'; });
    dropZone.addEventListener('dragleave', (e) => { dropZone.style.borderColor = '#cbd5e1'; dropZone.style.background = '#f8fafc'; });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#cbd5e1'; dropZone.style.background = '#f8fafc';
        if(e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            statusDiv.textContent = `Selected: ${fileInput.files[0].name}`;
        }
    });

    document.getElementById('upload-btn').onclick = async () => {
        if(!fileInput.files.length) { statusDiv.textContent = 'Select a file first'; statusDiv.style.color = '#ef4444'; return; }
        
        statusDiv.textContent = 'Uploading...'; statusDiv.style.color = 'var(--accent)';
        
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        fd.append('folder', document.getElementById('upload-folder').value);
        
        try {
            const res = await fetch('/api/upload', { method: 'POST', body: fd });
            const d = await res.json();
            if(res.ok) {
                statusDiv.textContent = 'Upload Complete!'; statusDiv.style.color = '#22c55e';
                loadFiles();
                setTimeout(() => statusDiv.textContent = '', 3000);
            } else {
                statusDiv.textContent = d.error; statusDiv.style.color = '#ef4444';
            }
        } catch(e) { statusDiv.textContent = 'Network Error'; }
    };

    async function loadFiles() {
        const grid = document.getElementById('file-grid');
        try {
            const res = await fetch('/api/files');
            if(res.status === 401) window.location.href = '/login';
            const files = await res.json();
            
            grid.innerHTML = '';
            if(files.length === 0) { document.getElementById('empty-state').style.display = 'block'; }
            else { document.getElementById('empty-state').style.display = 'none'; }

            files.forEach(f => {
                const ext = f.filename.split('.').pop().substring(0,4).toUpperCase();
                const processed = f.processed 
                    ? '<span style="color:#15803d; background:#dcfce7; padding:2px 8px; border-radius:99px; font-size:0.75rem; font-weight:600;">Synced</span>' 
                    : '<span style="color:#64748b; background:#f1f5f9; padding:2px 8px; border-radius:99px; font-size:0.75rem; font-weight:600;">Processing</span>';
                
                grid.innerHTML += `
                    <div style="border: 1px solid #e2e8f0; border-radius: 10px; padding: 1rem; transition: 0.2s; position: relative; background: white;" onmouseover="this.style.borderColor='var(--accent)'; this.style.transform='translateY(-2px)';" onmouseout="this.style.borderColor='#e2e8f0'; this.style.transform='none';">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                             <div style="width: 40px; height: 40px; background: #eff6ff; display: flex; align-items: center; justify-content: center; border-radius: 8px; font-weight: 700; color: var(--accent); font-size: 0.8rem;">${ext}</div>
                             ${processed}
                        </div>
                        <div style="font-weight: 600; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 0.2rem;" title="${f.filename}">${f.filename}</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem;">/${f.folder}</div>
                         <div style="margin-top: auto; display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                            <a href="${f.url}" target="_blank" style="text-align: center; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.4rem; font-size: 0.85rem; font-weight: 500; color: var(--text-main);">View</a>
                            <a href="/api/download?path=${f.folder}/${f.filename}" style="text-align: center; background: var(--primary); color: white; border-radius: 6px; padding: 0.4rem; font-size: 0.85rem; font-weight: 500;">Download</a>
                        </div>
                    </div>
                `;
            });
        } catch(e) { console.error(e); }
    }
    
    loadFiles();
    setInterval(loadFiles, 5000);
    lucide.createIcons();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5099)
