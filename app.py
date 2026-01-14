import os
import base64
import pickle
import subprocess
import logging
import random
import datetime
import uuid
import json
import sqlite3
import hashlib
import time
import jwt
from functools import wraps
from flask import Flask, request, render_template_string, render_template, jsonify, abort, Response, send_file, session, redirect, url_for, flash
from jinja2 import DictLoader
import io

# --- CONFIGURATION (VULNERABLE) ---
class Config:
    SECRET_KEY = "dev-key-very-secret-do-not-share" # ID: 141 (Hardcoded Secret)
    AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE" # ID: 142 (Leaked Secret)
    AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" # ID: 143 (Leaked Secret)
    DEBUG = True # ID: 128 (Debug Enabled -> Stack Traces)

app = Flask(__name__)
app.config.from_object(Config)

# --- AUTH DATABASE ---
DB_NAME = "devops_auth.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, email TEXT, otp_secret TEXT, reset_token TEXT)")
    # Create Admin
    try:
        pw = hashlib.md5("admin123".encode()).hexdigest()
        conn.execute("INSERT INTO users (username, password, email, otp_secret) VALUES (?, ?, ?, ?)", ("admin", pw, "admin@teghlabs.com", "1234"))
        conn.commit()
    except: pass
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- AUTH DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- MOCK DATA & SERVICES ---
BUILD_LOGS = {}
JOBS = {}
INTERNAL_METADATA = {
    "instance-id": "i-0abcdef1234567890",
    "ami-id": "ami-0abcdef1234567890",
    "iam-info": {
        "role": "TeghLabs-DevOps-Admin-Role",
        "access_token": "ASIAIOSFODNN7EXAMPLETOKEN" # ID: 185 (SSRF Target)
    }
}

# --- TEMPLATES (EMBEDDED) ---
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="dark scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TeghCloud | Enterprise DevOps Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        cyan: { 400: '#22d3ee', 500: '#06b6d4', 600: '#0891b2' }
                    }
                }
            }
        }
    </script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        :root {
            --bg-primary: #ffffff;
            --bg-secondary: #f3f4f6;
            --text-primary: #111827;
            --text-secondary: #4b5563;
            --glass-bg: rgba(255, 255, 255, 0.7);
            --glass-border: rgba(0, 0, 0, 0.1);
            --accent-color: #06b6d4;
        }
        .dark {
            --bg-primary: #0a0a0a;
            --bg-secondary: #171717;
            --text-primary: #e5e5e5;
            --text-secondary: #9ca3af;
            --glass-bg: rgba(20, 20, 20, 0.7);
            --glass-border: rgba(255, 255, 255, 0.08);
            --accent-color: #22d3ee;
        }

        body { font-family: 'Inter', sans-serif; background-color: var(--bg-primary); color: var(--text-primary); transition: background-color 0.3s, color 0.3s; overflow-x: hidden; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .glass-panel { background: var(--glass-bg); backdrop-filter: blur(12px); border: 1px solid var(--glass-border); box-shadow: 0 4px 30px rgba(0, 0, 0, 0.05); transition: border-color 0.3s; }
        .text-accent { color: var(--accent-color); }
        
        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-primary); }
        ::-webkit-scrollbar-thumb { background: var(--text-secondary); border-radius: 4px; opacity: 0.5; }
        
        .code-bg {
            background-image: radial-gradient(var(--text-secondary) 1px, transparent 1px);
            background-size: 20px 20px;
            opacity: 0.1;
        }
    </style>
</head>
<body class="antialiased min-h-screen relative flex flex-col">
    <!-- Navbar -->
    <nav class="fixed top-0 w-full z-50 glass-panel border-b border-[var(--glass-border)] transition-colors duration-300">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <!-- Logo -->
                <div class="flex items-center gap-2 cursor-pointer" onclick="window.location.href='/'">
                    <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white font-bold text-lg">T</div>
                    <span class="font-bold text-xl tracking-tight text-[var(--text-primary)]">Tegh<span class="text-accent">Cloud</span></span>
                </div>
                
                <!-- Desktop Nav -->
                <div class="hidden md:flex items-center gap-8 font-mono text-sm">
                    <a href="/" class="hover:text-accent transition-colors">./home</a>
                    <a href="/about" class="hover:text-accent transition-colors">./about</a>
                    <a href="/dashboard" class="hover:text-accent transition-colors">./pipeline</a>
                    <a href="/console" class="hover:text-accent transition-colors">./console</a>
                    
                    <div class="h-4 w-[1px] bg-[var(--text-secondary)] opacity-30"></div>
                    
                    <!-- Theme Toggle -->
                    <button onclick="toggleTheme()" class="p-2 rounded-full hover:bg-[var(--bg-secondary)] transition-colors text-[var(--text-primary)]" title="Toggle Theme">
                        <i data-lucide="sun" class="w-4 h-4 hidden dark:block"></i>
                        <i data-lucide="moon" class="w-4 h-4 block dark:hidden"></i>
                    </button>

                    {% if session.user_id %}
                         <a href="/logout" class="px-4 py-2 border border-red-500/30 text-red-500 rounded hover:bg-red-500/10 transition-colors">Logout</a>
                    {% else %}
                         <a href="/login" class="px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 text-white rounded hover:opacity-90 transition-opacity border-none">Login</a>
                    {% endif %}
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="pt-16 flex-grow relative z-10 transition-colors duration-300">
        {% block content %}{% endblock %}
    </main>

    <!-- Rich Footer -->
    <footer class="border-t border-[var(--glass-border)] bg-[var(--bg-secondary)] pt-12 pb-8 mt-auto transition-colors duration-300">
        <div class="max-w-7xl mx-auto px-4">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
                <div class="col-span-1 md:col-span-2">
                    <div class="flex items-center gap-2 mb-4">
                         <div class="w-6 h-6 rounded bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white font-bold text-xs">T</div>
                         <span class="font-bold text-lg text-[var(--text-primary)]">Tegh<span class="text-accent">Cloud</span></span>
                    </div>
                    <p class="text-[var(--text-secondary)] text-sm max-w-sm leading-relaxed">
                        The next-generation cloud infrastructure platform. Secure, scalable, and developer-first. 
                        Empowering teams to ship code faster with military-grade security simulations.
                    </p>
                </div>
                <div>
                    <h4 class="font-bold text-[var(--text-primary)] mb-4">Platform</h4>
                    <ul class="space-y-2 text-sm text-[var(--text-secondary)] font-mono">
                        <li><a href="/dashboard" class="hover:text-accent">CI/CD Pipeline</a></li>
                        <li><a href="/console" class="hover:text-accent">Cloud Console</a></li>
                        <li><a href="#" class="hover:text-accent">Artifacts</a></li>
                        <li><a href="#" class="hover:text-accent">Security Scan</a></li>
                    </ul>
                </div>
                <div>
                    <h4 class="font-bold text-[var(--text-primary)] mb-4">Company</h4>
                    <ul class="space-y-2 text-sm text-[var(--text-secondary)] font-mono">
                        <li><a href="/about" class="hover:text-accent">About Us</a></li>
                        <li><a href="#" class="hover:text-accent">Careers</a></li>
                        <li><a href="#" class="hover:text-accent">Legal</a></li>
                        <li><a href="#" class="hover:text-accent">Contact</a></li>
                    </ul>
                </div>
            </div>
            <div class="border-t border-[var(--glass-border)] pt-8 text-center md:text-left flex flex-col md:flex-row justify-between items-center text-xs text-[var(--text-secondary)] font-mono">
                <p>&copy; 2026 TeghCloud Inc. All rights reserved. // <span class="text-red-400">CONFIDENTIAL</span></p>
                <div class="flex gap-4 mt-4 md:mt-0">
                    <span>v3.0.0-E (Enterprise)</span>
                    <span>Powered by Node.js Runtime (v20.9.0)</span>
                </div>
            </div>
        </div>
    </footer>

    <script>
        lucide.createIcons();
        
        // Theme Logic
        function toggleTheme() {
            const html = document.documentElement;
            if (html.classList.contains('dark')) {
                html.classList.remove('dark');
                localStorage.setItem('theme', 'light');
            } else {
                html.classList.add('dark');
                localStorage.setItem('theme', 'dark');
            }
        }

        // Init Theme
        if (localStorage.theme === 'light') {
            document.documentElement.classList.remove('dark');
        } else {
            document.documentElement.classList.add('dark');
        }
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
"""

PAGE_ABOUT = """
{% extends "base" %}
{% block content %}
<div class="relative overflow-hidden py-20 px-4">
    <!-- Background Decor -->
    <div class="absolute top-0 right-0 w-1/3 h-full bg-gradient-to-l from-cyan-500/10 to-transparent pointer-events-none"></div>

    <div class="max-w-6xl mx-auto">
        <!-- Hero Section -->
        <div class="text-center mb-16">
            <h1 class="text-4xl md:text-6xl font-bold mb-6 text-[var(--text-primary)]">We Are <span class="text-accent underline decoration-4 decoration-cyan-500/30 underline-offset-8">TeghCloud</span>.</h1>
            <p class="text-xl text-[var(--text-secondary)] max-w-2xl mx-auto leading-relaxed">
                Building the secure foundation for the future of software. 
                We combine speed, reliability, and advanced security to empower the world's best engineering teams.
            </p>
        </div>

        <!-- Mission Grid -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-20">
            <div class="glass-panel p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300 border-l-4 border-cyan-500">
                <i data-lucide="shield" class="w-10 h-10 text-cyan-500 mb-4"></i>
                <h3 class="text-xl font-bold mb-3 text-[var(--text-primary)]">Security First</h3>
                <p class="text-[var(--text-secondary)]">Embedded security controls at every layer of the stack. From code commit to production deployment.</p>
            </div>
            <div class="glass-panel p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300 border-l-4 border-purple-500">
                <i data-lucide="cpu" class="w-10 h-10 text-purple-500 mb-4"></i>
                <h3 class="text-xl font-bold mb-3 text-[var(--text-primary)]">High Performance</h3>
                <p class="text-[var(--text-secondary)]">Distributed edge computing ensuring your applications run with near-zero latency worldwide.</p>
            </div>
            <div class="glass-panel p-8 rounded-2xl hover:-translate-y-2 transition-transform duration-300 border-l-4 border-green-500">
                <i data-lucide="users" class="w-10 h-10 text-green-500 mb-4"></i>
                <h3 class="text-xl font-bold mb-3 text-[var(--text-primary)]">Developer Focus</h3>
                <p class="text-[var(--text-secondary)]">Tools built by developers, for developers. Intuitive CLIs, APIs, and beautiful dashboards.</p>
            </div>
        </div>

        <!-- Team Section -->
        <div class="glass-panel rounded-2xl p-10 relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-cyan-500 to-purple-600"></div>
            <div class="flex flex-col md:flex-row items-center gap-10">
                <div class="flex-1">
                    <h2 class="text-3xl font-bold mb-4 text-[var(--text-primary)]">Meet the Minds</h2>
                    <p class="text-[var(--text-secondary)] mb-6">
                        TeghCloud is driven by a passionate team of engineers, security researchers, and dreamers. 
                        Led by our visionary founder, we are pushing the boundaries of what's possible in the cloud.
                    </p>
                    <a href="#" class="inline-flex items-center gap-2 text-accent font-bold hover:underline">View Open Positions <i data-lucide="arrow-right" class="w-4 h-4"></i></a>
                </div>
                <div class="flex-1 grid grid-cols-2 gap-4">
                     <!-- Fake Team Members -->
                     <div class="text-center">
                        <div class="w-24 h-24 mx-auto rounded-full bg-gray-700 mb-2 overflow-hidden border-2 border-cyan-500 p-1">
                            <img src="https://ui-avatars.com/api/?name=Tegh+Singh&background=0D8ABC&color=fff" class="rounded-full w-full h-full">
                        </div>
                        <h4 class="font-bold text-[var(--text-primary)]">Tegh Singh</h4>
                        <p class="text-xs text-[var(--text-secondary)] font-mono">Founder & CEO</p>
                     </div>
                     <div class="text-center">
                        <div class="w-24 h-24 mx-auto rounded-full bg-gray-700 mb-2 overflow-hidden border-2 border-purple-500 p-1">
                             <img src="https://ui-avatars.com/api/?name=Sarah+Connor&background=6b21a8&color=fff" class="rounded-full w-full h-full">
                        </div>
                        <h4 class="font-bold text-[var(--text-primary)]">hunter op </h4>
                        <p class="text-xs text-[var(--text-secondary)] font-mono">CTO</p>
                     </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
"""

PAGE_HOME = """
{% extends "base" %}
{% block content %}
<div class="relative overflow-hidden h-[90vh] flex items-center justify-center">
    <!-- Background Elements -->
    <div class="absolute inset-0 code-bg z-0"></div>
    <div class="absolute top-20 left-20 w-72 h-72 bg-purple-900/20 rounded-full blur-3xl parallax-float" data-speed="2"></div>
    <div class="absolute bottom-20 right-20 w-96 h-96 bg-cyan-900/20 rounded-full blur-3xl parallax-float" data-speed="-2"></div>

    <div class="relative z-10 text-center max-w-4xl mx-auto px-4">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 mb-8 backdrop-blur animate-fade-in-up">
            <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            <span class="text-xs font-mono text-gray-400">SYSTEM STATUS: OPTIMAL</span>
        </div>
        
        <h1 class="text-6xl md:text-8xl font-bold tracking-tighter mb-6 bg-clip-text text-transparent bg-gradient-to-r from-white via-gray-200 to-gray-600">
            SECURE. BUILD. <br/><span class="text-cyan-400">DEPLOY.</span>
        </h1>
        
        <p class="text-xl text-gray-400 mb-10 max-w-2xl mx-auto font-light leading-relaxed">
            The next-generation CI/CD orchestration platform for TeghLabs engineering teams. 
            Automated pipelines, secure artifact management, and real-time build telemetry.
        </p>
        
        <div class="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a href="/dashboard" class="group relative px-8 py-4 bg-cyan-500 text-black font-bold text-sm tracking-wide rounded-md overflow-hidden transition-all hover:bg-cyan-400">
                <span class="relative z-10 flex items-center gap-2">
                    ACCESS PIPELINE <i data-lucide="arrow-right" class="w-4 h-4"></i>
                </span>
            </a>
            <a href="/console" class="px-8 py-4 bg-white/5 border border-white/10 rounded-md font-mono text-sm hover:bg-white/10 transition-all flex items-center gap-2">
                <i data-lucide="terminal" class="w-4 h-4 text-gray-400"></i>
                DEBUG CONSOLE
            </a>
        </div>
    </div>
</div>

<section class="py-24 bg-black/50 border-y border-white/5">
    <div class="max-w-7xl mx-auto px-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div class="p-6 glass-panel rounded-xl hover:border-cyan-500/50 transition-colors group">
                <i data-lucide="shield-check" class="w-10 h-10 text-cyan-400 mb-4 group-hover:scale-110 transition-transform"></i>
                <h3 class="text-xl font-bold mb-2">Enterprise Security</h3>
                <p class="text-gray-400 text-sm leading-relaxed">Built with industry-leading security standards. (Audit Log #2291: Pending Review)</p>
            </div>
            <div class="p-6 glass-panel rounded-xl hover:border-cyan-500/50 transition-colors group">
                <i data-lucide="zap" class="w-10 h-10 text-purple-400 mb-4 group-hover:scale-110 transition-transform"></i>
                <h3 class="text-xl font-bold mb-2">Fast Builds</h3>
                <p class="text-gray-400 text-sm leading-relaxed">Distributed build runners with optimized caching layers.</p>
            </div>
            <div class="p-6 glass-panel rounded-xl hover:border-cyan-500/50 transition-colors group">
                <i data-lucide="package" class="w-10 h-10 text-pink-400 mb-4 group-hover:scale-110 transition-transform"></i>
                <h3 class="text-xl font-bold mb-2">Artifact Storage</h3>
                <p class="text-gray-400 text-sm leading-relaxed">Secure S3-compatible storage for all build outputs and assets.</p>
            </div>
        </div>
    </div>
</section>
{% endblock %}
"""

PAGE_DASHBOARD = """
{% extends "base" %}
{% block content %}
<div class="max-w-7xl mx-auto px-4 py-8">
    <div class="flex items-center justify-between mb-8">
        <div>
            <h2 class="text-3xl font-bold text-white">Pipeline Dashboard</h2>
            <p class="text-gray-400 mt-1 font-mono text-sm">Environment: <span class="text-green-400">PRODUCTION</span></p>
        </div>
        <button onclick="document.getElementById('new-pipeline-modal').classList.remove('hidden')" class="px-4 py-2 bg-cyan-600/20 text-cyan-400 border border-cyan-500/50 rounded hover:bg-cyan-600/30 transition-colors font-mono text-sm flex items-center gap-2">
            <i data-lucide="plus"></i> New Pipeline
        </button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <!-- Pipeline List -->
        <div class="lg:col-span-2 space-y-4">
            <div class="glass-panel p-6 rounded-xl relative overflow-hidden">
                <div class="flex items-start justify-between mb-4">
                    <div class="flex items-center gap-4">
                        <div class="w-10 h-10 rounded bg-green-900/30 flex items-center justify-center border border-green-500/30">
                            <i data-lucide="check-circle" class="w-5 h-5 text-green-500"></i>
                        </div>
                        <div>
                            <h3 class="font-bold text-lg">Backend API Service</h3>
                            <p class="text-xs text-gray-500 font-mono">Commit: 8f2a1d • 2 mins ago</p>
                        </div>
                    </div>
                    <span class="px-2 py-1 bg-green-500/10 text-green-400 text-xs rounded border border-green-500/20 font-mono">PASSING</span>
                </div>
                <!-- Mock Terminal Output in Card -->
                <div class="bg-black/80 rounded p-4 font-mono text-xs text-gray-300 overflow-x-auto">
                    <p class="text-gray-500">$ loading build config...</p>
                    <p class="text-green-400">> ENV loaded. AWS_ACCESS_KEY_ID=****</p>
                    <p>> Running tests... 142 passed.</p>
                    <p class="text-blue-400">> Deploying to us-east-1...</p>
                </div>
                <div class="mt-4 flex gap-2">
                    <a href="/logs/view" class="text-xs text-cyan-400 hover:underline">View Full Logs</a>
                    <span class="text-gray-600 text-xs">|</span>
                    <a href="#" class="text-xs text-cyan-400 hover:underline">Download Artifacts</a>
                </div>
            </div>

             <div class="glass-panel p-6 rounded-xl opacity-75">
                <div class="flex items-start justify-between mb-4">
                    <div class="flex items-center gap-4">
                        <div class="w-10 h-10 rounded bg-red-900/30 flex items-center justify-center border border-red-500/30">
                            <i data-lucide="x-circle" class="w-5 h-5 text-red-500"></i>
                        </div>
                        <div>
                            <h3 class="font-bold text-lg">Legacy Authentication</h3>
                            <p class="text-xs text-gray-500 font-mono">Commit: fa12b9 • 2 hours ago</p>
                        </div>
                    </div>
                    <span class="px-2 py-1 bg-red-500/10 text-red-400 text-xs rounded border border-red-500/20 font-mono">FAILED</span>
                </div>
                <div class="bg-black/80 rounded p-4 font-mono text-xs text-gray-300">
                    <p class="text-red-400">Error: Dependency conflict in requirements.txt</p>
                </div>
            </div>
        </div>

        <!-- Sidebar / Tools -->
        <div class="space-y-6">
            <div class="glass-panel p-6 rounded-xl">
                <h3 class="font-bold mb-4 flex items-center gap-2">
                    <i data-lucide="settings" class="w-4 h-4 text-cyan-400"></i> Settings
                </h3>
                <div class="space-y-4">
                   <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">Pipeline Manifest Source</label>
                        <div class="flex gap-2">
                            <input type="text" id="manifest-url" placeholder="http://repo/pipeline.yaml" class="w-full bg-black/50 border border-white/10 rounded px-3 py-2 text-xs font-mono focus:border-cyan-400 outline-none text-white">
                            <button onclick="fetchManifest()" class="bg-cyan-600/20 border border-cyan-500/30 text-cyan-400 px-3 py-1 rounded text-xs hover:bg-cyan-600/40">Fetch</button>
                        </div>
                        <p id="manifest-result" class="text-[10px] text-gray-500 mt-1 truncate"></p>
                   </div>
                   
                    <div class="pt-4 border-t border-white/5">
                        <label class="block text-xs font-mono text-gray-500 mb-1">Session State (Base64)</label>
                        <input type="text" id="session-state" placeholder="e30=..." class="w-full bg-black/50 border border-white/10 rounded px-3 py-2 text-xs font-mono focus:border-cyan-400 outline-none text-white">
                        <button onclick="restoreState()" class="mt-2 w-full bg-white/5 border border-white/10 py-1 rounded text-xs hover:bg-white/10">Restore Session</button>
                   </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- New Pipeline Modal -->
<div id="new-pipeline-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
    <div class="glass-panel w-full max-w-2xl rounded-xl p-6 relative">
        <button onclick="document.getElementById('new-pipeline-modal').classList.add('hidden')" class="absolute top-4 right-4 text-gray-500 hover:text-white">
            <i data-lucide="x" class="w-5 h-5"></i>
        </button>
        
        <h3 class="text-xl font-bold mb-4">Define Pipeline (YAML)</h3>
        <p class="text-xs text-gray-400 mb-4">Configure your build steps. Use 'hook' for post-processing scripts.</p>
        
        <textarea id="yaml-config" class="w-full h-64 bg-black border border-white/10 rounded font-mono text-sm p-4 text-green-400 focus:border-cyan-500/50 outline-none resize-none" spellcheck="false">name: production-build
steps:
  - checkout
  - install-deps
  - run-tests
# Hooks are executed in the build shell
hook: echo "Build configured successfully"
</textarea>
        
        <div class="flex justify-end gap-3 mt-4">
            <button onclick="document.getElementById('new-pipeline-modal').classList.add('hidden')" class="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
            <button onclick="submitPipeline()" class="px-6 py-2 bg-cyan-600 text-black font-bold text-sm rounded hover:bg-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.5)]">
                Run Pipeline
            </button>
        </div>
        <div id="build-output" class="mt-4 hidden p-2 bg-black rounded border border-white/10 font-mono text-xs text-gray-300 max-h-32 overflow-y-auto"></div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    // SSRF Logic
    async function fetchManifest() {
        const url = document.getElementById('manifest-url').value;
        const resEl = document.getElementById('manifest-result');
        resEl.innerText = "Fetching...";
        resEl.className = "text-[10px] text-yellow-500 mt-1";
        
        try {
            const formData = new FormData();
            formData.append('url', url);
            const response = await fetch('/api/fetch_manifest', {
                method: 'POST',
                body: formData
            });
            const text = await response.text();
            resEl.innerText = response.status === 200 ? "Success: " + text.substring(0, 50) + "..." : "Error: " + text;
            resEl.className = response.status === 200 ? "text-[10px] text-green-400 mt-1" : "text-[10px] text-red-400 mt-1";
        } catch (e) {
            resEl.innerText = "Network Error";
        }
    }

    // Pickle Logic
    async function restoreState() {
        const state = document.getElementById('session-state').value;
        try {
            const response = await fetch('/api/v1/state', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({state: state})
            });
            alert('State Restored');
        } catch(e) { console.error(e); }
    }

    // Command Injection Logic
    async function submitPipeline() {
        const yaml = document.getElementById('yaml-config').value;
        const outDiv = document.getElementById('build-output');
        outDiv.classList.remove('hidden');
        outDiv.innerHTML = '<span class="animate-pulse">Initializing build environment...</span>';
        
        try {
            const response = await fetch('/api/v1/build', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({config: yaml})
            });
            const data = await response.json();
            
            // Simulate streaming logs related to the output
            let outputHtml = `<div class="text-green-400">$ tegh-ci run --config pipeline.yaml</div>`;
            if (data.status === 'success') {
                outputHtml += `<div class="text-gray-400">Parsing YAML configuration...</div>`;
                outputHtml += `<div class="text-gray-400">Executing hook...</div>`;
                outputHtml += `<div class="text-white mt-2 pl-2 border-l-2 border-cyan-500">${data.output}</div>`;
                outputHtml += `<div class="text-green-500 mt-2">Build Job Created: ${data.job_id}</div>`;
            } else {
                outputHtml += `<div class="text-red-500">Error: ${data.message}</div>`;
            }
            outDiv.innerHTML = outputHtml;
            
        } catch (e) {
            outDiv.innerHTML = '<span class="text-red-500">System Error: Connection Refused</span>';
        }
    }
</script>
{% endblock %}
"""

PAGE_CONSOLE = """
{% extends "base" %}
{% block content %}
<div class="max-w-7xl mx-auto px-4 py-8 h-[80vh] flex flex-col">
    <div class="mb-4 flex items-center justify-between">
        <h2 class="text-2xl font-bold font-mono flex items-center gap-2">
            <i data-lucide="terminal-square" class="text-cyan-400"></i> Developer Console
        </h2>
        
        <!-- Hidden Asset Link (Discovery Challenge) -->
        <a href="/assets/private" class="text-black hover:text-gray-900 text-[10px] cursor-default">debug_assets</a>
    </div>

    <div class="flex-1 glass-panel rounded-lg flex flex-col overflow-hidden border border-white/10 shadow-2xl">
        <!-- Terminal Header -->
        <div class="bg-white/5 border-b border-white/5 px-4 py-2 flex items-center justify-between">
            <div class="flex gap-2">
                <div class="w-3 h-3 rounded-full bg-red-500/50"></div>
                <div class="w-3 h-3 rounded-full bg-yellow-500/50"></div>
                <div class="w-3 h-3 rounded-full bg-green-500/50"></div>
            </div>
            <div class="text-xs font-mono text-gray-500">user@teghlabs-dev: ~</div>
        </div>

        <!-- Terminal Output -->
        <div id="console-output" class="flex-1 bg-black/90 p-4 font-mono text-sm text-gray-300 overflow-y-auto space-y-2">
            <div class="text-cyan-400">Welcome to TeghLabs Developer Utility v1.0</div>
            <div>Type 'help' for available commands.</div>
            <br/>
        </div>

        <!-- Input Area -->
        <div class="p-4 bg-black border-t border-white/10 flex items-center gap-2">
            <span class="text-cyan-400 font-mono">➜</span>
            <input type="text" id="console-input" class="flex-1 bg-transparent border-none outline-none text-white font-mono text-sm" placeholder="Type command..." autocomplete="off">
        </div>
    </div>
    
    <div class="mt-4 grid grid-cols-2 gap-4">
        <div class="glass-panel p-4 rounded border border-yellow-500/20">
            <h4 class="text-yellow-400 text-xs font-bold mb-2 uppercase tracking-wider">Warning</h4>
            <p class="text-xs text-gray-500">This console runs in a sandboxed JS worker. Do not paste untrusted code.</p>
        </div>
        <!-- Client Side RCE Trigger (Eval) -->
        <div class="glass-panel p-4 rounded border border-transparent">
             <h4 class="text-gray-400 text-xs font-bold mb-2 uppercase tracking-wider">Quick Utilities</h4>
             <div class="flex gap-2">
                <button onclick="runUtil('Date.now()')" class="px-2 py-1 bg-white/5 text-xs rounded hover:bg-white/10">Timestamp</button>
                <button onclick="runUtil('navigator.userAgent')" class="px-2 py-1 bg-white/5 text-xs rounded hover:bg-white/10">UserAgent</button>
                <button onclick="loadPlugin()" class="px-2 py-1 bg-red-500/10 text-red-400 text-xs rounded hover:bg-red-500/20 border border-red-500/30">Load Plugin (Alpha)</button>
             </div>
        </div>
    </div>
</div>

<script>
    const output = document.getElementById('console-output');
    const input = document.getElementById('console-input');

    input.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            const cmd = this.value;
            this.value = '';
            log(`➜ ${cmd}`, 'text-gray-500');
            processCommand(cmd);
        }
    });

    function log(text, className = 'text-gray-300') {
        const div = document.createElement('div');
        div.className = className;
        div.innerText = text;
        output.appendChild(div);
        output.scrollTop = output.scrollHeight;
    }

    // Client-Side RCE (Eval)
    function processCommand(cmd) {
        if (cmd === 'help') {
            log('Available commands: help, clear, echo, calc <expr>', 'text-cyan-400');
        } else if (cmd === 'clear') {
            output.innerHTML = '';
        } else if (cmd.startsWith('echo ')) {
            log(cmd.slice(5));
        } else if (cmd.startsWith('calc ')) {
            const expr = cmd.slice(5);
            try {
                // VULNERABILITY: Unsafe Eval 
                // Attack: calc alert(1)
                const result = eval(expr); 
                log(`Result: ${result}`, 'text-green-400');
            } catch (e) {
                log(`Error: ${e.message}`, 'text-red-500');
            }
        } else {
            log(`Command not found: ${cmd}`, 'text-red-400');
        }
    }
    
    // Quick Utils also use eval path indirectly for demonstration consistency
    function runUtil(code) {
        input.value = 'calc ' + code;
        processCommand('calc ' + code);
    }

    // ID 200: Client-side RCE (Unsafe Script/Worker Execution)
    function loadPlugin() {
        // Vulnerable to loading malicious external scripts
        const url = prompt("Enter Plugin URL (e.g., http://attacker.com/pwn.js):");
        if(url) {
             log(`Loading plugin from ${url}...`, 'text-yellow-400');
             const script = document.createElement('script');
             script.src = url;
             document.body.appendChild(script);
             log('Plugin loaded (Check Console)', 'text-green-400');
        }
    }
</script>
{% endblock %}
"""

# --- CONFIG TEMPLATES FOR AUTH ---
# --- CONFIG TEMPLATES FOR AUTH ---
TEMPLATES = {
    'base': BASE_TEMPLATE,
    'about.html': PAGE_ABOUT,
    'login.html': """
        {% extends "base" %}
        {% block content %}
        <div class="flex items-center justify-center h-[80vh]">
            <div class="w-full max-w-md bg-black/50 border border-white/10 p-8 rounded-xl backdrop-blur-md">
                <h2 class="text-2xl font-bold mb-6 text-white text-center">TeghOps <span class="text-cyan-400">Portal</span></h2>
                
                {% if error %}
                <div class="bg-red-500/20 text-red-400 p-3 rounded mb-4 text-xs">{{ error }}</div>
                {% endif %}
                {% if message %}
                <div class="bg-green-500/20 text-green-400 p-3 rounded mb-4 text-xs">{{ message }}</div>
                {% endif %}
                
                <form action="/login" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">IDENTITY</label>
                        <input type="text" name="username" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">CREDENTIAL</label>
                        <input type="password" name="password" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <button type="submit" class="w-full bg-cyan-600 hover:bg-cyan-500 text-black font-bold py-2 rounded transition">AUTHENTICATE</button>
                    <div class="text-center mt-4">
                        <a href="/register" class="text-xs text-gray-500 hover:text-white">Initialize New Identity</a>
                        <span class="text-gray-600 mx-2">|</span>
                        <a href="/forgot-password" class="text-xs text-gray-500 hover:text-white">Forgot Password?</a>
                    </div>
                </form>
            </div>
        </div>
        {% endblock %}
    """,
    'register.html': """
        {% extends "base" %}
        {% block content %}
        <div class="flex items-center justify-center h-[80vh]">
            <div class="w-full max-w-md bg-black/50 border border-white/10 p-8 rounded-xl backdrop-blur-md">
                <h2 class="text-2xl font-bold mb-6 text-white text-center">New <span class="text-cyan-400">Identity</span></h2>
                
                {% if error %}
                <div class="bg-red-500/20 text-red-400 p-3 rounded mb-4 text-xs">{{ error }}</div>
                {% endif %}
                
                <form action="/register" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">USERNAME</label>
                        <input type="text" name="username" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">EMAIL</label>
                        <input type="email" name="email" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">PASSWORD</label>
                        <input type="password" name="password" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <button type="submit" class="w-full bg-cyan-600 hover:bg-cyan-500 text-black font-bold py-2 rounded transition">PROVISION</button>
                    <div class="text-center mt-4">
                        <a href="/login" class="text-xs text-gray-500 hover:text-white">Return to Login</a>
                    </div>
                </form>
            </div>
        </div>
        {% endblock %}
    """,
    'forgot.html': """
        {% extends "base" %}
        {% block content %}
        <div class="flex items-center justify-center h-[80vh]">
            <div class="w-full max-w-md bg-black/50 border border-white/10 p-8 rounded-xl backdrop-blur-md">
                <h2 class="text-2xl font-bold mb-6 text-white text-center">Account <span class="text-cyan-400">Recovery</span></h2>
                <form action="/forgot-password" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">REGISTERED EMAIL</label>
                        <input type="email" name="email" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <button type="submit" class="w-full bg-cyan-600 hover:bg-cyan-500 text-black font-bold py-2 rounded transition">SEND RESET LINK</button>
                    <div class="text-center mt-4">
                         <a href="/login" class="text-xs text-gray-500 hover:text-white">Back to Login</a>
                    </div>
                </form>
            </div>
        </div>
        {% endblock %}
    """,
    'reset.html': """
        {% extends "base" %}
        {% block content %}
        <div class="flex items-center justify-center h-[80vh]">
            <div class="w-full max-w-md bg-black/50 border border-white/10 p-8 rounded-xl backdrop-blur-md">
                 <h2 class="text-2xl font-bold mb-6 text-white text-center">Set <span class="text-cyan-400">Credential</span></h2>
                 <form action="/reset-password/{{ token }}" method="POST" class="space-y-4">
                    <div>
                        <label class="block text-xs font-mono text-gray-500 mb-1">NEW PASSWORD</label>
                        <input type="password" name="password" class="w-full bg-black border border-white/20 rounded px-3 py-2 text-white focus:border-cyan-400 outline-none" required>
                    </div>
                    <button type="submit" class="w-full bg-cyan-600 hover:bg-cyan-500 text-black font-bold py-2 rounded transition">UPDATE PASSWORD</button>
                </form>
            </div>
        </div>
        {% endblock %}
    """
}
app.jinja_loader = DictLoader(TEMPLATES)

# --- ROUTES ---

# --- ROUTES ---

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/dashboard')
    # If not logged in, show the Landing Page (PAGE_HOME) instead of redirecting strictly to login
    # This allows users to see the "About Us" and "Home" content before logging in.
    return render_template_string(PAGE_HOME, flask_version="2.2.2")

@app.route('/about')
def about():
    # Render the new About page
    return render_template('about.html', flask_version="2.2.2")

# --- AUTH ROUTES (Merged from app2.py) ---
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        return render_template('login.html')
        
    u, p = request.form.get('username'), request.form.get('password')
    if u: u = u.strip()
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username LIKE ? OR email LIKE ?", (u, u)).fetchone()
    conn.close()
    
    if user and user['password'] == hashlib.md5(p.encode()).hexdigest():
        # Direct login for demo (skip OTP for simplicity in this merge, or re-add if requested)
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect('/dashboard')
        
    return render_template('login.html', error="Invalid Credentials")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
        
    u, p, e = request.form.get('username'), request.form.get('password'), request.form.get('email')
    conn = get_db()
    try:
        pw = hashlib.md5(p.encode()).hexdigest()
        conn.execute("INSERT INTO users (username, password, email, otp_secret) VALUES (?, ?, ?, ?)", (u, pw, e, "0000"))
        conn.commit()
        return redirect('/login')
    except Exception as err:
        return render_template('register.html', error=str(err))
    finally:
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# --- PROTECTED PORTAL ROUTES ---
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template_string(PAGE_DASHBOARD, username=session.get('username'), flask_version="2.2.2")

@app.route('/console')
@login_required
def console():
    return render_template_string(PAGE_CONSOLE, flask_version="2.2.2")

# --- VULNERABLE API ENDPOINTS (Protected) ---

# 1. SSRF (ID: 181-185)
@app.route('/api/fetch_manifest', methods=['POST'])
@login_required
def fetch_manifest():
    target_url = request.form.get('url')
    if not target_url:
        return "URL required", 400
    
    # [VULNERABLE] No blacklist/whitelist. Can hit localhost:5000/internal/metadata
    try:
        import requests
        r = requests.get(target_url, timeout=2) 
        return Response(r.text, status=200, mimetype='text/plain')
    except Exception as e:
        return str(e), 500

# 2. Insecure Deserialization (ID: 196-197)
@app.route('/api/v1/state', methods=['POST'])
@login_required
def update_state():
    data = request.json
    if not data or 'state' not in data:
        return jsonify({"error": "No state data"}), 400
    
    try:
        # SECURED: Replaced unsafe pickle.loads with JSON handling
        # obj = pickle.loads(pickled_data) 
        # For compatibility with potential JSON data in state:
        try:
            import json
            current_state = json.loads(base64.b64decode(data['state']).decode('utf-8'))
            return jsonify({"status": "updated", "type": "safe_json"})
        except:
             return jsonify({"status": "ignored", "message": "Unsafe serialization disabled"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 3. Command Injection (ID: 198)
@app.route('/api/v1/build', methods=['POST'])
@login_required
def trigger_build():
    data = request.json
    config_yaml = data.get('config', '')
    
    hook_cmd = None
    for line in config_yaml.split('\n'):
        if line.strip().startswith('hook:'):
            hook_cmd = line.split(':', 1)[1].strip()
            
    output = "No hook defined"
    if hook_cmd:
        # [SECURED] Parsing command safely and preventing source code access
        import shlex
        try:
            # Prevent shell injection by avoiding shell=True
            args = shlex.split(hook_cmd)
            
            # Simple blacklist to prevent viewing source
            forbidden = ['cat', 'less', 'more', 'head', 'tail', 'grep', 'awk', 'sed', 'app.py', 'app2.py', 'app3.py']
            if any(bad in hook_cmd for bad in forbidden):
                 return jsonify({"status": "failed", "message": "Security Violation: Command contains forbidden terms."}), 403

            output = subprocess.check_output(args, shell=False, stderr=subprocess.STDOUT)
            output = output.decode('utf-8')
        except subprocess.CalledProcessError as e:
            output = e.output.decode('utf-8')
            return jsonify({"status": "failed", "message": "Hook failed", "output": output}), 400
        except Exception as e:
             return jsonify({"status": "failed", "message": f"Execution error: {str(e)}"}), 400

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "queued", "config": config_yaml}
    return jsonify({"status": "success", "job_id": job_id, "output": output})

# 4. Internal Metadata Service (SSRF Target)
@app.route('/internal/metadata')
def internal_metadata():
    if request.remote_addr != '127.0.0.1':
        return "Access Denied: Metadata service only accessible from localhost", 403
    return jsonify(INTERNAL_METADATA)

# 5. Cloud Bucket Exposure (ID: 161-165)
@app.route('/assets/private')
def list_private_assets():
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
    <Name>teghlabs-internal-assets-prod</Name>
    <Contents><Key>logo.png</Key></Contents>
</ListBucketResult>
"""
    return Response(xml_response, mimetype='application/xml')

# --- LOG VIEWER (LFI / Leak Target) ---
@app.route('/logs/view')
@login_required
def view_logs():
    # [VULNERABLE] Log Viewer (LFI)
    # Reads any file from disk based on user input
    log_file = request.args.get('file', 'build.log')

    try:
        # [SECURED] Log Viewer
        # 1. Restrict to current directory using os.path.basename
        # 2. Enforce .log extension
        filename = os.path.basename(log_file)
        
        if not filename.endswith('.log'):
            return "Security Error: Only .log files are allowed.", 403

        # Construct full path safely (assuming logs are in current dir or specific log dir)
        # For this app, simply reading from local works if files are local.
        if not os.path.exists(filename):
             raise FileNotFoundError
             
        with open(filename, 'r') as f:
            content = f.read()
            
        return render_template_string("""
        {% extends "base" %}
        {% block content %}
        <div class="max-w-7xl mx-auto px-4 py-8">
            <a href="/dashboard" class="text-cyan-400 hover:underline mb-4 inline-block">&larr; Back to Dashboard</a>
            <div class="bg-black border border-white/10 rounded-lg p-6 overflow-hidden shadow-2xl">
                <div class="flex items-center justify-between mb-4 border-b border-white/5 pb-4">
                    <h1 class="text-xl font-mono font-bold text-white">Build Log Viewer</h1>
                    <div class="text-xs font-mono text-gray-500">File: {{ filename }}</div>
                </div>
                <pre class="font-mono text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap leading-relaxed">{{ logs }}</pre>
            </div>
        </div>
        {% endblock %}
        """, logs=content, filename=log_file)
    except FileNotFoundError:
         return render_template_string(BASE_TEMPLATE + "<div class='p-10 text-yellow-500'>Error: Log file not found.</div>")


# 💀 LOGICAL VULNERABILITY: Predictable Token
# ==========================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        
        if user:
            # [VULNERABILITY] Predictable Randomness (Time-based seeding)
            try:
                # Intentionally weak token generation
                token_seed = str(int(time.time())) 
                token = hashlib.md5(token_seed.encode()).hexdigest()
                
                conn.execute("UPDATE users SET reset_token = ? WHERE id = ?", (token, user['id']))
                conn.commit()
                
                # In real app sending email, here just printing to console
                reset_link = f"http://localhost:5000/reset-password/{token}"
                print(f"\n[EMAIL SERVICE] To: {email} | Body: Click here to reset: {reset_link}\n")
            except Exception as e:
                print(e)
            finally:
                conn.close()
            return render_template('login.html', message=f"Recovery email sent to {email}. (Check Server Console)")
        
        conn.close()
        return render_template('login.html', message=f"Recovery email sent to {email}. (Check Server Console)")
        
    return render_template('forgot.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()
    
    if not user:
        conn.close()
        return render_template('login.html', error="Invalid or expired reset token.")
    
    if request.method == 'POST':
        new_pass = request.form.get('password')
        hashed_pass = hashlib.md5(new_pass.encode()).hexdigest()
        
        conn.execute("UPDATE users SET password = ?, reset_token = NULL WHERE id = ?", (hashed_pass, user['id']))
        conn.commit()
        conn.close()
        return render_template('login.html', message="Password successfully updated.")
        
    conn.close()
    return render_template('reset.html', token=token)

if __name__ == '__main__':
    # Banner
    init_db()
    print("Starting TeghLabs Dev Portal...")
    print("WARNING: This application contains INTENTIONAL VULNERABILITIES.")
    print("Do not deploy to production networks.")
    app.run(host='0.0.0.0', port=5067)
