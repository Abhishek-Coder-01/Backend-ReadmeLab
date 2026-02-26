from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import io
import logging
import re
from urllib.parse import quote

load_dotenv()

# ─── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
# Allow local dev by default; set CORS_ORIGINS to a comma-separated list for production.
cors_origins_env = os.getenv("CORS_ORIGINS", "*").strip()
if cors_origins_env == "*":
    cors_origins = "*"
else:
    cors_origins = []
    for o in cors_origins_env.split(","):
        o = o.strip()
        if not o:
            continue
        # Normalize: remove trailing slash so it matches Origin header
        if o.endswith("/"):
            o = o[:-1]
        cors_origins.append(o)

CORS(app, resources={r"/*": {"origins": cors_origins}})


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return app.make_default_options_response()

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    origin_norm = origin[:-1] if origin.endswith("/") else origin
    if cors_origins == "*" or origin_norm in (cors_origins if isinstance(cors_origins, list) else []):
        response.headers["Access-Control-Allow-Origin"] = origin_norm or "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise EnvironmentError("OPENROUTER_API_KEY is not set in the environment.")

# ─── Bot Identity ──────────────────────────────────────────────────────────────
OWNER_NAME = "Abhishek"
BOT_NAME   = "ReadmeLab"
AI_MODEL   = "openai/gpt-4o-mini"

# ─── Trigger Keywords ──────────────────────────────────────────────────────────
README_TRIGGERS = [
    "create readme", "make readme", "generate readme", "build readme",
    "create a readme", "make a readme", "generate a readme", "build a readme",
    "readme banao", "readme banana", "readme chahiye", "readme bana do",
    "new readme", "i want readme", "i need readme", "help me create readme",
    "help me with readme", "write readme", "write a readme",
    "create me readme", "make me readme",
]

OWNER_KEYWORDS = [
    "who made you", "who created you", "who built you", "who is your owner",
    "who is your creator", "who is your developer", "who developed you",
    "who is your maker", "your owner", "your creator", "your developer",
    "your maker", "who made this", "who created this", "who built this",
    "tumhe kisne banaya", "kisne banaya", "owner kaun hai", "creator kaun hai",
    "aapko kisne banaya", "apko kisne banaya", "tumhara owner", "apka owner",
    "who is abhishek", "tell me about your owner",
]

EDIT_FIELD_MAP = {
    ("project", "title", "name"): ("readme_ask_title",       "Sure! What should the **project name** be?"),
    ("description",):             ("readme_ask_description",  "Sure! Give me the new **description**:"),
    ("tech", "stack"):            ("readme_ask_tech",         "Sure! What **tech stack** should I use?"),
    ("live", "link", "demo"):     ("readme_ask_live",         "Sure! What's the **live demo link**?"),
}

# ─── File Type Emoji Mapping ───────────────────────────────────────────────────
FILE_EMOJIS = {
    # Config files
    ".env": "🔐", ".env.example": "📋", ".env.local": "🔐",
    ".gitignore": "🚫", ".dockerignore": "🚫",
    "dockerfile": "🐳", "docker-compose.yml": "🐳", "docker-compose.yaml": "🐳",
    ".eslintrc": "📏", ".prettierrc": "✨", ".editorconfig": "⚙️",
    
    # JavaScript/TypeScript
    ".js": "📜", ".jsx": "⚛️", ".ts": "📘", ".tsx": "⚛️",
    "package.json": "📦", "package-lock.json": "🔒", "yarn.lock": "🧶",
    "tsconfig.json": "⚙️", "webpack.config.js": "📦", "vite.config.js": "⚡",
    "next.config.js": "▲", "nuxt.config.js": "💚",
    
    # Python
    ".py": "🐍", "requirements.txt": "📋", "setup.py": "⚙️", "pyproject.toml": "📦",
    "manage.py": "🎯", "wsgi.py": "🌐", "asgi.py": "⚡",
    
    # Java
    ".java": "☕", ".kt": "🟣", ".gradle": "🐘", "pom.xml": "📦",
    
    # Web
    ".html": "🌐", ".css": "🎨", ".scss": "💅", ".sass": "💅",
    ".vue": "💚", ".svelte": "🧡",
    
    # Data/Config
    ".json": "📋", ".yaml": "📄", ".yml": "📄", ".xml": "📄", ".toml": "📄",
    ".csv": "📊", ".sql": "🗃️",
    
    # Documentation
    ".md": "📖", "readme.md": "📚", ".txt": "📝",
    
    # Images
    ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".svg": "🎨", ".gif": "🎞️",
    ".ico": "🎯", "favicon.ico": "🌟",
    
    # Other
    ".sh": "🔧", ".bat": "⚙️", ".exe": "⚙️",
    "license": "⚖️", ".gitattributes": "📋",
}

# --- Title Emoji & Tech Badge Helpers ---
TITLE_EMOJI_PATTERNS = [
    (r"\bpdf\b", "📄"),
    (r"\bai\b|artificial intelligence", "🤖"),
    (r"\bml\b|machine learning", "🧠"),
    (r"\bchat(bot)?\b", "💬"),
    (r"\bresume\b|\bcv\b", "📝"),
    (r"\bimage\b|\bphoto\b|\bocr\b", "🖼️"),
]

TECH_BADGES = {
    "html": {"label": "HTML5", "color": "E34F26", "logo": "html5", "logoColor": "white"},
    "css": {"label": "CSS3", "color": "1572B6", "logo": "css3", "logoColor": "white"},
    "javascript": {"label": "JavaScript", "color": "F7DF1E", "logo": "javascript", "logoColor": "000000"},
    "react": {"label": "React", "color": "20232A", "logo": "react", "logoColor": "61DAFB"},
    "nextjs": {"label": "Next.js", "color": "000000", "logo": "nextdotjs", "logoColor": "white"},
    "vue": {"label": "Vue.js", "color": "35495E", "logo": "vuedotjs", "logoColor": "4FC08D"},
    "nuxt": {"label": "Nuxt", "color": "00C58E", "logo": "nuxtdotjs", "logoColor": "white"},
    "angular": {"label": "Angular", "color": "DD0031", "logo": "angular", "logoColor": "white"},
    "svelte": {"label": "Svelte", "color": "FF3E00", "logo": "svelte", "logoColor": "white"},
    "node": {"label": "Node.js", "color": "339933", "logo": "nodedotjs", "logoColor": "white"},
    "express": {"label": "Express", "color": "000000", "logo": "express", "logoColor": "white"},
    "nestjs": {"label": "NestJS", "color": "E0234E", "logo": "nestjs", "logoColor": "white"},
    "django": {"label": "Django", "color": "092E20", "logo": "django", "logoColor": "white"},
    "flask": {"label": "Flask", "color": "000000", "logo": "flask", "logoColor": "white"},
    "fastapi": {"label": "FastAPI", "color": "009688", "logo": "fastapi", "logoColor": "white"},
    "spring": {"label": "Spring Boot", "color": "6DB33F", "logo": "springboot", "logoColor": "white"},
    "laravel": {"label": "Laravel", "color": "FF2D20", "logo": "laravel", "logoColor": "white"},
    "rails": {"label": "Ruby on Rails", "color": "CC0000", "logo": "rubyonrails", "logoColor": "white"},
    "go": {"label": "Go", "color": "00ADD8", "logo": "go", "logoColor": "white"},
    "rust": {"label": "Rust", "color": "000000", "logo": "rust", "logoColor": "white"},
    "mongodb": {"label": "MongoDB", "color": "47A248", "logo": "mongodb", "logoColor": "white"},
    "postgresql": {"label": "PostgreSQL", "color": "4169E1", "logo": "postgresql", "logoColor": "white"},
    "mysql": {"label": "MySQL", "color": "4479A1", "logo": "mysql", "logoColor": "white"},
    "redis": {"label": "Redis", "color": "DC382D", "logo": "redis", "logoColor": "white"},
    "sqlite": {"label": "SQLite", "color": "003B57", "logo": "sqlite", "logoColor": "white"},
    "firebase": {"label": "Firebase", "color": "FFCA28", "logo": "firebase", "logoColor": "000000"},
    "supabase": {"label": "Supabase", "color": "3ECF8E", "logo": "supabase", "logoColor": "white"},
    "prisma": {"label": "Prisma", "color": "2D3748", "logo": "prisma", "logoColor": "white"},
    "redux": {"label": "Redux", "color": "764ABC", "logo": "redux", "logoColor": "white"},
    "zustand": {"label": "Zustand", "color": "443E38", "logo": "zustand", "logoColor": "white"},
    "recoil": {"label": "Recoil", "color": "3578E5", "logo": "recoil", "logoColor": "white"},
    "mobx": {"label": "MobX", "color": "FF9955", "logo": "mobx", "logoColor": "white"},
    "react_native": {"label": "React Native", "color": "20232A", "logo": "react", "logoColor": "61DAFB"},
    "flutter": {"label": "Flutter", "color": "02569B", "logo": "flutter", "logoColor": "white"},
    "ionic": {"label": "Ionic", "color": "3880FF", "logo": "ionic", "logoColor": "white"},
    "electron": {"label": "Electron", "color": "47848F", "logo": "electron", "logoColor": "white"},
    "tauri": {"label": "Tauri", "color": "FFC131", "logo": "tauri", "logoColor": "000000"},
    "typescript": {"label": "TypeScript", "color": "3178C6", "logo": "typescript", "logoColor": "white"},
    "python": {"label": "Python", "color": "3776AB", "logo": "python", "logoColor": "white"},
    "java": {"label": "Java", "color": "ED8B00", "logo": "openjdk", "logoColor": "white"},
    "kotlin": {"label": "Kotlin", "color": "7F52FF", "logo": "kotlin", "logoColor": "white"},
    "swift": {"label": "Swift", "color": "FA7343", "logo": "swift", "logoColor": "white"},
    "docker": {"label": "Docker", "color": "2496ED", "logo": "docker", "logoColor": "white"},
    "kubernetes": {"label": "Kubernetes", "color": "326CE5", "logo": "kubernetes", "logoColor": "white"},
    "aws": {"label": "AWS", "color": "232F3E", "logo": "amazonaws", "logoColor": "FF9900"},
    "azure": {"label": "Azure", "color": "0078D4", "logo": "microsoftazure", "logoColor": "white"},
    "gcp": {"label": "GCP", "color": "4285F4", "logo": "googlecloud", "logoColor": "white"},
    "vercel": {"label": "Vercel", "color": "000000", "logo": "vercel", "logoColor": "white"},
    "netlify": {"label": "Netlify", "color": "00C7B7", "logo": "netlify", "logoColor": "white"},
    "webpack": {"label": "Webpack", "color": "8DD6F9", "logo": "webpack", "logoColor": "000000"},
    "vite": {"label": "Vite", "color": "646CFF", "logo": "vite", "logoColor": "white"},
    "rollup": {"label": "Rollup", "color": "EC4A3F", "logo": "rollupdotjs", "logoColor": "white"},
    "parcel": {"label": "Parcel", "color": "F0DB4F", "logo": "parcel", "logoColor": "000000"},
    "jest": {"label": "Jest", "color": "C21325", "logo": "jest", "logoColor": "white"},
    "mocha": {"label": "Mocha", "color": "8D6748", "logo": "mocha", "logoColor": "white"},
    "pytest": {"label": "PyTest", "color": "0A9EDC", "logo": "pytest", "logoColor": "white"},
    "cypress": {"label": "Cypress", "color": "17202C", "logo": "cypress", "logoColor": "white"},
    "tailwind": {"label": "Tailwind CSS", "color": "06B6D4", "logo": "tailwindcss", "logoColor": "white"},
    "bootstrap": {"label": "Bootstrap", "color": "7952B3", "logo": "bootstrap", "logoColor": "white"},
    "materialui": {"label": "MUI", "color": "007FFF", "logo": "mui", "logoColor": "white"},
    "chakra": {"label": "Chakra UI", "color": "319795", "logo": "chakraui", "logoColor": "white"},
}

TECH_BADGE_ORDER = list(TECH_BADGES.keys())

# ─── Helpers ───────────────────────────────────────────────────────────────────

def get_file_emoji(filename: str) -> str:
    """Get appropriate emoji for a file based on its name/extension."""
    filename_lower = filename.lower()
    
    # Check exact filename match first
    if filename_lower in FILE_EMOJIS:
        return FILE_EMOJIS[filename_lower]
    
    # Check extension match
    for ext, emoji in FILE_EMOJIS.items():
        if ext.startswith(".") and filename_lower.endswith(ext):
            return emoji
    
    # Default
    return "📄"


def _has_emoji(text: str) -> bool:
    return bool(re.search(r"[\U0001F300-\U0001FAFF]", text))


def add_title_emoji(title: str) -> str:
    """Add a context-aware emoji prefix to the title when keywords match."""
    if not title:
        return title
    if _has_emoji(title):
        return title
    lower = title.lower()
    for pattern, emoji in TITLE_EMOJI_PATTERNS:
        if re.search(pattern, lower):
            return f"{emoji} {title}"
    return title


def _badge_url(label: str, color: str, logo: str = None, logo_color: str = None) -> str:
    base = f"https://img.shields.io/badge/{quote(label)}-{color}"
    params = ["style=for-the-badge"]
    if logo:
        params.append(f"logo={quote(logo)}")
    if logo_color:
        params.append(f"logoColor={quote(logo_color)}")
    return base + "?" + "&".join(params)


def _stack_tokens(stack_str: str) -> list:
    return [t.strip() for t in re.split(r"[,/|]+", stack_str or "") if t.strip()]


def build_tech_badges_block(stack_str: str) -> str:
    tech = detect_technologies(stack_str)
    badges = []
    used = set()

    for key in TECH_BADGE_ORDER:
        if tech.get(key):
            info = TECH_BADGES[key]
            label = info["label"]
            url = _badge_url(
                label=label,
                color=info["color"],
                logo=info.get("logo"),
                logo_color=info.get("logoColor"),
            )
            badges.append((label, url))
            used.add(label.lower())

    for token in _stack_tokens(stack_str):
        token_norm = re.sub(r"\s+", " ", token).strip()
        if not token_norm:
            continue
        token_lower = token_norm.lower()
        if any(u in token_lower or token_lower in u for u in used):
            continue
        url = _badge_url(label=token_norm, color="4B5563")
        badges.append((token_norm, url))
        used.add(token_lower)

    if not badges:
        return ""

    imgs = "\n  ".join([f'<img src="{url}" alt="{label}"/>' for label, url in badges])
    return f"<p align=\"center\">\n  {imgs}\n</p>"


def is_readme_trigger(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in README_TRIGGERS)


def is_owner_question(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in OWNER_KEYWORDS)


def owner_reply(suffix: str = "", next_step: str = "free_chat", user_data: dict = None) -> dict:
    """Return a standardised owner-question response."""
    msg = f"I was created by **{OWNER_NAME}** 🧑‍💻"
    if suffix:
        msg += f"\n\n{suffix}"
    return {"reply": msg, "next_step": next_step, "user_data": user_data or {}}


def sanitize_history(history: list, max_messages: int = 12, max_chars: int = 2000) -> list:
    """Validate and trim conversation history before sending to the AI."""
    if not isinstance(history, list):
        return []

    cleaned = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role    = item.get("role")
        content = item.get("content", "")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        cleaned.append({"role": role, "content": content})

    return cleaned[-max_messages:]


def call_ai(system_prompt: str, user_prompt: str, timeout: int = 60, history: list = None) -> str:
    """Call the OpenRouter AI API and return the assistant's reply."""
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(sanitize_history(history))
    messages.append({"role": "user", "content": user_prompt})

    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "HTTP-Referer": "http://localhost",
            "X-Title": BOT_NAME,
        },
        json={"model": AI_MODEL, "messages": messages},
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()

    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Unexpected API response structure: {result}") from exc


def detect_technologies(stack_str: str) -> dict:
    """
    Enhanced technology detection with support for more frameworks and libraries.
    Returns a dict with boolean flags for detected technologies.
    """
    stack_lower = stack_str.lower()
    
    # Helper function for flexible matching
    def has_tech(*keywords):
        return any(kw in stack_lower for kw in keywords)
    def has_word(pattern: str):
        return re.search(pattern, stack_lower) is not None
    
    return {
        # Frontend Frameworks
        "react": has_tech("react", "reactjs", "react.js"),
        "nextjs": has_tech("next", "nextjs", "next.js"),
        "vue": has_tech("vue", "vuejs", "vue.js"),
        "nuxt": has_tech("nuxt", "nuxtjs", "nuxt.js"),
        "angular": has_tech("angular"),
        "svelte": has_tech("svelte", "sveltekit"),
        
        # Backend Frameworks
        "node": has_tech("node", "nodejs", "node.js"),
        "express": has_tech("express", "expressjs", "express.js"),
        "nestjs": has_tech("nest", "nestjs", "nest.js"),
        "django": has_tech("django"),
        "flask": has_tech("flask"),
        "fastapi": has_tech("fastapi", "fast-api"),
        "spring": has_tech("spring", "spring boot", "springboot"),
        "laravel": has_tech("laravel"),
        "rails": has_tech("rails", "ruby on rails", "ror"),
        "go": has_tech("go", "golang", "gin", "fiber"),
        "rust": has_tech("rust", "actix", "rocket"),
        
        # Databases
        "mongodb": has_tech("mongo", "mongodb"),
        "postgresql": has_tech("postgres", "postgresql", "pg"),
        "mysql": has_tech("mysql"),
        "redis": has_tech("redis"),
        "sqlite": has_tech("sqlite", "sqlite3"),
        "firebase": has_tech("firebase", "firestore"),
        "supabase": has_tech("supabase"),
        "prisma": has_tech("prisma"),
        
        # State Management
        "redux": has_tech("redux", "redux-toolkit"),
        "zustand": has_tech("zustand"),
        "recoil": has_tech("recoil"),
        "mobx": has_tech("mobx"),
        
        # Mobile
        "react_native": has_tech("react native", "react-native", "rn"),
        "flutter": has_tech("flutter", "dart"),
        "ionic": has_tech("ionic"),
        
        # Desktop
        "electron": has_tech("electron", "electronjs"),
        "tauri": has_tech("tauri"),
        
        # Languages
        "typescript": has_tech("typescript") or has_word(r"\bts\b"),
        "javascript": has_tech("javascript", "ecmascript") or has_word(r"\bjs\b"),
        "python": has_tech("python"),
        "java": has_tech("java"),
        "kotlin": has_tech("kotlin"),
        "swift": has_tech("swift"),

        # Static Web
        "html": has_tech("html"),
        "css": has_tech("css"),
        "static_site": (
            has_tech("html", "css", "javascript", "vanilla", "static") or
            has_word(r"\bjs\b")
        ),
        
        # Deployment/DevOps
        "docker": has_tech("docker", "container"),
        "kubernetes": has_tech("kubernetes", "k8s"),
        "aws": has_tech("aws", "amazon web services"),
        "azure": has_tech("azure"),
        "gcp": has_tech("gcp", "google cloud"),
        "vercel": has_tech("vercel"),
        "netlify": has_tech("netlify"),
        
        # Build Tools
        "webpack": has_tech("webpack"),
        "vite": has_tech("vite"),
        "rollup": has_tech("rollup"),
        "parcel": has_tech("parcel"),
        
        # Testing
        "jest": has_tech("jest"),
        "mocha": has_tech("mocha"),
        "pytest": has_tech("pytest"),
        "cypress": has_tech("cypress"),
        
        # CSS Frameworks
        "tailwind": has_tech("tailwind", "tailwindcss"),
        "bootstrap": has_tech("bootstrap"),
        "materialui": has_tech("material-ui", "mui", "material ui"),
        "chakra": has_tech("chakra", "chakra-ui", "chakra ui"),
    }


def _infer_structure(stack_str: str, project_name: str) -> str:
    """
    Dynamically build a detailed, annotated directory tree based on the
    detected tech stack with appropriate emojis for each file type.
    """
    tech = detect_technologies(stack_str)
    
    # Determine file extension
    ext = "ts" if tech["typescript"] else "js"
    py_ext = "py"
    
    # Sanitize folder name
    folder = re.sub(r'[^a-z0-9-]', '-', project_name.lower()).strip('-') or "my-project"
    
    lines = [f"{folder}/", "│"]
    
    # ══════════════════════════════════════════════════════════════════════════
    # FRONTEND
    # ══════════════════════════════════════════════════════════════════════════
    
    if tech["nextjs"]:
        lines += [
            "├── 📂 app/                             # Next.js 13+ App Router",
            "│   ├── 📂 (auth)/                      # Route group for authentication",
            "│   │   ├── 📂 login/",
            f"│   │   │   └── {get_file_emoji(f'page.{ext}')} page.{ext}           # Login page",
            "│   │   └── 📂 register/",
            f"│   │   │   └── {get_file_emoji(f'page.{ext}')} page.{ext}           # Register page",
            "│   │",
            "│   ├── 📂 dashboard/",
            f"│   │   ├── {get_file_emoji(f'page.{ext}')} page.{ext}               # Dashboard page",
            f"│   │   └── {get_file_emoji(f'layout.{ext}')} layout.{ext}           # Dashboard layout",
            "│   │",
            "│   ├── 📂 api/                         # API routes",
            "│   │   ├── 📂 auth/",
            f"│   │   │   └── {get_file_emoji(f'route.{ext}')} route.{ext}        # Auth API endpoints",
            "│   │   └── 📂 data/",
            f"│   │   │   └── {get_file_emoji(f'route.{ext}')} route.{ext}        # Data API endpoints",
            "│   │",
            f"│   ├── {get_file_emoji(f'layout.{ext}')} layout.{ext}               # Root layout",
            f"│   ├── {get_file_emoji(f'page.{ext}')} page.{ext}                   # Home page",
            f"│   └── {get_file_emoji('globals.css')} globals.css                  # Global styles",
            "│",
            "├── 📂 components/                      # Reusable React components",
            f"│   ├── {get_file_emoji(f'Navbar.{ext}x')} Navbar.{ext}x            # Navigation bar",
            f"│   ├── {get_file_emoji(f'Footer.{ext}x')} Footer.{ext}x            # Footer component",
            f"│   └── {get_file_emoji(f'Button.{ext}x')} Button.{ext}x            # Custom button",
            "│",
            "├── 📂 lib/                             # Utility libraries",
            f"│   ├── {get_file_emoji(f'db.{ext}')} db.{ext}                       # Database connection",
            f"│   └── {get_file_emoji(f'utils.{ext}')} utils.{ext}                 # Helper functions",
            "│",
        ]
        
    elif tech["react"]:
        lines += [
            "├── 📂 client/                          # React frontend application",
            "│   ├── 📂 public/                      # Static assets served directly",
            f"│   │   ├── {get_file_emoji('index.html')} index.html               # Root HTML template",
            f"│   │   └── {get_file_emoji('favicon.ico')} favicon.ico             # Browser tab icon",
            "│   │",
            "│   └── 📂 src/                         # All React source code",
            "│       ├── 📂 components/              # Reusable UI components",
            f"│       │   ├── {get_file_emoji(f'Navbar.{ext}x')} Navbar.{ext}x    # Top navigation bar",
            f"│       │   ├── {get_file_emoji(f'Footer.{ext}x')} Footer.{ext}x    # Site-wide footer",
            f"│       │   ├── {get_file_emoji(f'Loader.{ext}x')} Loader.{ext}x    # Loading spinner",
            f"│       │   └── {get_file_emoji(f'ErrorBoundary.{ext}x')} ErrorBoundary.{ext}x  # Error handler",
            "│       │",
            "│       ├── 📂 pages/                   # Route-level page components",
            f"│       │   ├── {get_file_emoji(f'Home.{ext}x')} Home.{ext}x        # Landing page",
            f"│       │   ├── {get_file_emoji(f'About.{ext}x')} About.{ext}x      # About page",
            f"│       │   ├── {get_file_emoji(f'Dashboard.{ext}x')} Dashboard.{ext}x  # User dashboard",
            f"│       │   ├── {get_file_emoji(f'Login.{ext}x')} Login.{ext}x      # Login page",
            f"│       │   └── {get_file_emoji(f'Register.{ext}x')} Register.{ext}x  # Registration page",
            "│       │",
        ]
        
        if tech["redux"]:
            lines += [
                "│       ├── 📂 redux/                   # Redux Toolkit store & slices",
                f"│       │   ├── {get_file_emoji(f'store.{ext}')} store.{ext}         # Global Redux store",
                f"│       │   ├── {get_file_emoji(f'authSlice.{ext}')} authSlice.{ext} # Auth state slice",
                f"│       │   └── {get_file_emoji(f'dataSlice.{ext}')} dataSlice.{ext} # Data state slice",
                "│       │",
            ]
        
        lines += [
            "│       ├── 📂 hooks/                   # Custom React hooks",
            f"│       │   ├── {get_file_emoji(f'useAuth.{ext}')} useAuth.{ext}     # Auth hook",
            f"│       │   └── {get_file_emoji(f'useFetch.{ext}')} useFetch.{ext}   # Fetch hook",
            "│       │",
            "│       ├── 📂 utils/                   # Helper functions",
            f"│       │   ├── {get_file_emoji(f'api.{ext}')} api.{ext}             # API client",
            f"│       │   └── {get_file_emoji(f'helpers.{ext}')} helpers.{ext}     # Utilities",
            "│       │",
            f"│       ├── {get_file_emoji(f'App.{ext}x')} App.{ext}x               # Root component",
            f"│       ├── {get_file_emoji(f'index.{ext}')} index.{ext}             # Entry point",
            f"│       └── {get_file_emoji('index.css')} index.css                  # Global styles",
            "│",
        ]

    elif tech["static_site"]:
        lines += [
            "├── 📂 src/                             # Static website source",
            f"│   ├── {get_file_emoji('index.html')} index.html                   # Main HTML file",
            "│   ├── 📂 css/                          # Stylesheets",
            f"│   │   └── {get_file_emoji('styles.css')} styles.css               # Main styles",
            "│   ├── 📂 js/                           # Scripts",
            f"│   │   └── {get_file_emoji('app.js')} app.js                       # Main script",
            "│   └── 📂 assets/                       # Images/icons/fonts",
            f"│       └── {get_file_emoji('logo.png')} logo.png                   # Branding asset",
            "│",
        ]

    elif tech["vue"]:
        lines += [
            "├── 📂 frontend/                        # Vue.js frontend application",
            "│   ├── 📂 public/                      # Static assets",
            "│   └── 📂 src/",
            "│       ├── 📂 components/              # Reusable Vue components",
            f"│       │   ├── {get_file_emoji('Navbar.vue')} Navbar.vue           # Navigation",
            f"│       │   └── {get_file_emoji('Footer.vue')} Footer.vue           # Footer",
            "│       │",
            "│       ├── 📂 views/                   # Page components",
            f"│       │   ├── {get_file_emoji('Home.vue')} Home.vue               # Home page",
            f"│       │   └── {get_file_emoji('About.vue')} About.vue             # About page",
            "│       │",
            "│       ├── 📂 store/                   # Vuex store",
            f"│       │   └── {get_file_emoji('index.js')} index.js               # Store config",
            "│       │",
            "│       ├── 📂 router/                  # Vue Router",
            f"│       │   └── {get_file_emoji('index.js')} index.js               # Routes",
            "│       │",
            f"│       └── {get_file_emoji('main.js')} main.js                     # Entry point",
            "│",
        ]
    
    elif tech["angular"]:
        lines += [
            "├── 📂 frontend/                        # Angular frontend",
            "│   └── 📂 src/",
            "│       ├── 📂 app/",
            "│       │   ├── 📂 components/          # Reusable components",
            "│       │   ├── 📂 pages/               # Page modules",
            "│       │   ├── 📂 services/            # Business logic services",
            "│       │   └── 📂 guards/              # Route guards",
            f"│       └── {get_file_emoji('main.ts')} main.ts                     # Bootstrap",
            "│",
        ]
    
    # ══════════════════════════════════════════════════════════════════════════
    # BACKEND
    # ══════════════════════════════════════════════════════════════════════════
    
    if tech["node"] or tech["express"] or tech["nestjs"]:
        backend_name = "server" if not tech["nestjs"] else "backend"
        lines += [
            f"├── 📂 {backend_name}/                          # Backend application",
        ]
        
        if tech["nestjs"]:
            lines += [
                "│   ├── 📂 src/",
                "│   │   ├── 📂 auth/                    # Authentication module",
                f"│   │   │   ├── {get_file_emoji('auth.controller.ts')} auth.controller.ts  # Auth endpoints",
                f"│   │   │   ├── {get_file_emoji('auth.service.ts')} auth.service.ts        # Auth logic",
                f"│   │   │   └── {get_file_emoji('auth.module.ts')} auth.module.ts          # Auth module",
                "│   │   │",
                "│   │   ├── 📂 users/                   # Users module",
                f"│   │   │   ├── {get_file_emoji('users.controller.ts')} users.controller.ts",
                f"│   │   │   ├── {get_file_emoji('users.service.ts')} users.service.ts",
                f"│   │   │   └── {get_file_emoji('user.entity.ts')} user.entity.ts        # User entity",
                "│   │   │",
                f"│   │   ├── {get_file_emoji('app.module.ts')} app.module.ts             # Root module",
                f"│   │   └── {get_file_emoji('main.ts')} main.ts                         # Entry point",
                "│   │",
            ]
        else:
            lines += [
                "│   ├── 📂 config/                      # Configuration files",
                f"│   │   ├── {get_file_emoji(f'db.{ext}')} db.{ext}                    # Database connection",
            ]
            if tech["redis"]:
                lines.append(f"│   │   └── {get_file_emoji(f'redis.{ext}')} redis.{ext}                # Redis client")
            else:
                lines.append(f"│   │   └── {get_file_emoji(f'env.{ext}')} env.{ext}                    # Env validation")
            
            lines += [
                "│   │",
                "│   ├── 📂 controllers/                 # Request handlers",
                f"│   │   ├── {get_file_emoji(f'authController.{ext}')} authController.{ext}      # Auth logic",
                f"│   │   ├── {get_file_emoji(f'userController.{ext}')} userController.{ext}      # User CRUD",
                f"│   │   └── {get_file_emoji(f'dataController.{ext}')} dataController.{ext}      # Data operations",
                "│   │",
                "│   ├── 📂 models/                      # Database schemas",
                f"│   │   ├── {get_file_emoji(f'User.{ext}')} User.{ext}                  # User model",
                f"│   │   └── {get_file_emoji(f'Resource.{ext}')} Resource.{ext}            # Resource model",
                "│   │",
                "│   ├── 📂 routes/                      # API routes",
                f"│   │   ├── {get_file_emoji(f'authRoutes.{ext}')} authRoutes.{ext}          # /api/auth",
                f"│   │   ├── {get_file_emoji(f'userRoutes.{ext}')} userRoutes.{ext}          # /api/users",
                f"│   │   └── {get_file_emoji(f'dataRoutes.{ext}')} dataRoutes.{ext}          # /api/data",
                "│   │",
                "│   ├── 📂 middleware/                  # Express middleware",
                f"│   │   ├── {get_file_emoji(f'authMiddleware.{ext}')} authMiddleware.{ext}    # JWT verify",
                f"│   │   ├── {get_file_emoji(f'roleMiddleware.{ext}')} roleMiddleware.{ext}    # RBAC",
                f"│   │   └── {get_file_emoji(f'errorHandler.{ext}')} errorHandler.{ext}       # Error handler",
                "│   │",
                f"│   └── {get_file_emoji(f'server.{ext}')} server.{ext}                   # App entry point",
                "│",
            ]
    
    elif tech["django"]:
        lines += [
            "├── 📂 backend/                         # Django backend",
            "│   ├── 📂 config/                      # Django project settings",
            f"│   │   ├── {get_file_emoji('settings.py')} settings.py             # Settings",
            f"│   │   ├── {get_file_emoji('urls.py')} urls.py                     # URL config",
            f"│   │   └── {get_file_emoji('wsgi.py')} wsgi.py                     # WSGI entry",
            "│   │",
            "│   ├── 📂 apps/                        # Django apps",
            "│   │   ├── 📂 users/                   # User app",
            f"│   │   │   ├── {get_file_emoji('models.py')} models.py             # Models",
            f"│   │   │   ├── {get_file_emoji('views.py')} views.py               # Views",
            f"│   │   │   └── {get_file_emoji('serializers.py')} serializers.py   # DRF serializers",
            "│   │   │",
            "│   │   └── 📂 api/                     # Core API app",
            f"│   │       ├── {get_file_emoji('models.py')} models.py",
            f"│   │       └── {get_file_emoji('views.py')} views.py",
            "│   │",
            f"│   ├── {get_file_emoji('manage.py')} manage.py                     # Django CLI",
            f"│   └── {get_file_emoji('requirements.txt')} requirements.txt       # Dependencies",
            "│",
        ]
    
    elif tech["flask"]:
        lines += [
            "├── 📂 backend/                         # Flask backend",
            "│   ├── 📂 app/                         # Application package",
            f"│   │   ├── {get_file_emoji('__init__.py')} __init__.py             # App factory",
            "│   │   ├── 📂 routes/                  # Blueprint routes",
            f"│   │   │   ├── {get_file_emoji('auth.py')} auth.py                 # Auth routes",
            f"│   │   │   └── {get_file_emoji('api.py')} api.py                   # API routes",
            "│   │   │",
            "│   │   ├── 📂 models/                  # Database models",
            f"│   │   │   └── {get_file_emoji('user.py')} user.py                 # User model",
            "│   │   │",
            "│   │   └── 📂 utils/                   # Utilities",
            f"│   │       └── {get_file_emoji('helpers.py')} helpers.py           # Helper functions",
            "│   │",
            f"│   ├── {get_file_emoji('app.py')} app.py                           # Entry point",
            f"│   ├── {get_file_emoji('config.py')} config.py                     # Config classes",
            f"│   └── {get_file_emoji('requirements.txt')} requirements.txt       # Dependencies",
            "│",
        ]
    
    elif tech["fastapi"]:
        lines += [
            "├── 📂 backend/                         # FastAPI backend",
            "│   ├── 📂 app/",
            f"│   │   ├── {get_file_emoji('main.py')} main.py                     # FastAPI entry",
            "│   │   ├── 📂 routers/                 # API routers",
            f"│   │   │   ├── {get_file_emoji('auth.py')} auth.py                 # Auth endpoints",
            f"│   │   │   └── {get_file_emoji('users.py')} users.py               # User endpoints",
            "│   │   │",
            "│   │   ├── 📂 models/                  # ORM models",
            f"│   │   │   └── {get_file_emoji('user.py')} user.py                 # User model",
            "│   │   │",
            "│   │   ├── 📂 schemas/                 # Pydantic schemas",
            f"│   │   │   └── {get_file_emoji('user.py')} user.py                 # User schema",
            "│   │   │",
            "│   │   └── 📂 dependencies/            # FastAPI dependencies",
            f"│   │       └── {get_file_emoji('auth.py')} auth.py                 # Auth dependency",
            "│   │",
            f"│   └── {get_file_emoji('requirements.txt')} requirements.txt       # Dependencies",
            "│",
        ]
    
    elif tech["python"]:
        lines += [
            "├── 📂 backend/                         # Python backend",
            "│   ├── 📂 app/                         # Application package",
            f"│   │   ├── {get_file_emoji('__init__.py')} __init__.py             # App init",
            "│   │   ├── 📂 routes/                  # API routes",
            f"│   │   │   └── {get_file_emoji('api.py')} api.py                   # API endpoints",
            "│   │   ├── 📂 models/                  # Data models",
            f"│   │   │   └── {get_file_emoji('models.py')} models.py             # Models",
            "│   │   └── 📂 services/                # Business logic",
            f"│   │       └── {get_file_emoji('services.py')} services.py         # Services",
            "│   │",
            f"│   ├── {get_file_emoji('app.py')} app.py                           # Entry point",
            f"│   ├── {get_file_emoji('config.py')} config.py                     # Config",
            f"│   └── {get_file_emoji('requirements.txt')} requirements.txt       # Dependencies",
            "│",
        ]
    
    # ══════════════════════════════════════════════════════════════════════════
    # MOBILE
    # ══════════════════════════════════════════════════════════════════════════
    
    if tech["react_native"]:
        lines += [
            "├── 📂 mobile/                          # React Native app",
            "│   ├── 📂 src/",
            "│   │   ├── 📂 screens/                 # Screen components",
            "│   │   ├── 📂 components/              # Reusable components",
            "│   │   ├── 📂 navigation/              # Navigation config",
            "│   │   └── 📂 services/                # API services",
            "│   │",
            f"│   ├── {get_file_emoji('App.js')} App.js                           # Root component",
            f"│   └── {get_file_emoji('package.json')} package.json               # Dependencies",
            "│",
        ]
    
    elif tech["flutter"]:
        lines += [
            "├── 📂 mobile/                          # Flutter app",
            "│   ├── 📂 lib/",
            "│   │   ├── 📂 screens/                 # Screen widgets",
            "│   │   ├── 📂 widgets/                 # Reusable widgets",
            "│   │   ├── 📂 services/                # API services",
            "│   │   └── 📄 main.dart                # Entry point",
            "│   │",
            f"│   └── {get_file_emoji('pubspec.yaml')} pubspec.yaml               # Dependencies",
            "│",
        ]
    
    # ══════════════════════════════════════════════════════════════════════════
    # DOCKER / DOCS / ROOT FILES
    # ══════════════════════════════════════════════════════════════════════════
    
    if tech["docker"]:
        lines += [
            f"├── {get_file_emoji('dockerfile')} Dockerfile                       # Container image definition",
            f"├── {get_file_emoji('docker-compose.yml')} docker-compose.yml       # Multi-service orchestration",
            f"├── {get_file_emoji('.dockerignore')} .dockerignore                 # Docker ignore file",
            "│",
        ]
    
    lines += [
        "├── 📂 docs/                                # Documentation",
        f"│   ├── {get_file_emoji('API.md')} API.md                           # API reference",
        f"│   ├── {get_file_emoji('SETUP.md')} SETUP.md                       # Setup guide",
        f"│   └── {get_file_emoji('CONTRIBUTING.md')} CONTRIBUTING.md         # Contribution guidelines",
        "│",
    ]
    
    # Root files
    lines += [
        f"├── {get_file_emoji('.env.example')} .env.example                       # Environment template",
        f"├── {get_file_emoji('.gitignore')} .gitignore                           # Git ignore rules",
    ]
    
    if tech["node"] or tech["react"] or tech["vue"]:
        lines.append(f"├── {get_file_emoji('package.json')} package.json                         # Node dependencies & scripts")
        lines.append(f"├── {get_file_emoji('package-lock.json')} package-lock.json                   # Lock file")
    
    if tech["python"]:
        lines.append(f"├── {get_file_emoji('requirements.txt')} requirements.txt                     # Python dependencies")
    
    if tech["typescript"]:
        lines.append(f"├── {get_file_emoji('tsconfig.json')} tsconfig.json                         # TypeScript config")
    
    if tech["tailwind"]:
        lines.append(f"├── {get_file_emoji('tailwind.config.js')} tailwind.config.js                   # Tailwind config")
    
    if tech["jest"]:
        lines.append(f"├── {get_file_emoji('jest.config.js')} jest.config.js                         # Jest test config")
    
    lines += [
        f"├── {get_file_emoji('license')} LICENSE                               # Project license",
        f"└── {get_file_emoji('readme.md')} README.md                           # You are here 📍",
    ]
    
    return "\n".join(lines)


def build_readme_prompt(user_data: dict) -> str:
    """
    Build a rich, structured prompt that instructs the AI to produce
    a professional, fully-featured README.md.
    """
    current_year  = datetime.now().year
    project_name  = user_data.get("project_name", "My Project")
    description   = user_data.get("description",  "A software project.")
    tech_stack    = user_data.get("tech_stack",    "Not specified")
    live          = user_data.get("live",          "Not available")
    author        = OWNER_NAME

    title_with_emoji = add_title_emoji(project_name)
    badges_block = build_tech_badges_block(tech_stack)
    structure     = _infer_structure(tech_stack, project_name)

    return f"""
You are a world-class technical writer and open-source README expert.
Create a COMPLETE, professional README.md for the project below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project Name : {project_name}
Title (use EXACTLY for README H1) : {title_with_emoji}
Description  : {description}
Tech Stack   : {tech_stack}
Live Demo    : {live}
Author       : {author}
Year         : {current_year}

BADGES BLOCK (use EXACTLY as-is under the title if not empty)
{badges_block or "(none)"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT STRUCTURE  (use EXACTLY as-is inside a code block)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{structure}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED SECTIONS (in this order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1.  TITLE SECTION

    - The FIRST line of the README must be:
          # {{Title (use EXACTLY as provided above)}}

    - Immediately below the title, render centered shields.io badges.

    - If BADGES BLOCK is provided (not "(none)"):
          • Paste it EXACTLY as-is.
          • Do NOT modify.
          • Do NOT regenerate.
          • Do NOT change styling.

    - If BADGES BLOCK is "(none)":
          • Automatically generate shields.io badges for each technology in Tech Stack.
          • Use style=for-the-badge.
          • Use official logo (logo= parameter).
          • Center them inside:
                <p align="center"> ... </p>
2.  BANNER image
    IMPORTANT:
    - Use the EXACT HTML below.
    - Do NOT change type, color, animation, height, fontSize, layout, or styling.
    - Do NOT redesign.
    - Keep shark type and gradient EXACTLY the same.
    - Only replace text and desc values if necessary.
    
    <p align="center">
  <img src="https://capsule-render.vercel.app/api?type=shark&color=0:4158D0,100:C850C0&height=300&section=header&text=AI%20Revolution&fontSize=70&fontColor=ffffff&animation=twinkling&fontAlignY=35&desc=Intelligent%20Automation%20Platform&descAlignY=55&descSize=25" width="100%"/>
</p>

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=24&duration=3000&pause=1000&color=00C4F7&center=true&vCenter=true&width=600&lines=Building+The+Future+of+AI;Intelligent+Automation+Solutions;Next-Gen+Machine+Learning;Production-Ready+AI+Systems" alt="Typing SVG" />
</p>
    
3.  TABLE OF CONTENTS   →  anchor links to every section
4.  OVERVIEW            →  2-3 sentences, what problem it solves
5.  KEY FEATURES        →  bullet list, each item one sentence, with emoji prefix
6.  TECH STACK TABLE    →  3 columns: Layer | Technology | Purpose
7.  PROJECT STRUCTURE   →  paste the exact annotated tree provided above inside a code block
8.  GETTING STARTED
        Prerequisites   →  exact version requirements
        Installation    →  numbered steps with code blocks
        Environment     →  .env.example table (Variable | Required | Description)
        Run             →  dev + production commands
9.  USAGE               →  2-3 concrete examples with code snippets
10. API REFERENCE       →  table of main endpoints if a backend exists
        (Method | Endpoint | Description | Auth Required)
11. SCREENSHOTS         →  placeholder section with HTML img tags + captions inside a flex container
                             (use a <div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;"> and
                              each screenshot in a <figure> with <img> + <figcaption>)
12. LIVE DEMO           →  badge + link (or "Coming Soon" if not available)
13. REQUIREMENTS        →  two sub-sections:
        Functional Requirements     →  [ ] checklist of what the app must DO
        Non-Functional Requirements →  [ ] checklist of quality attributes
                                        (performance, security, scalability,
                                         accessibility, reliability, etc.)
14. ROADMAP             →  [ ] unchecked items grouped under Near-term / Future
15. CONTRIBUTING        →  fork → branch → commit → PR steps + code style note
16. LICENSE             →  MIT badge + one-line description
17. CONTACT             →  Author name, GitHub link placeholder, email placeholder
18. FOOTER              →  centered: © {current_year} {project_name}. All Rights Reserved. Built with ❤️ by {author}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STYLE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Use relevant emojis in section headings (one per heading, not more).
- All shields.io badges must use style=for-the-badge.
- Use logos (logo=) in badges wherever possible.
- Every code block must declare its language (bash, js, python, env, etc.).
- Keep heading hierarchy: # for title, ## for sections, ### for sub-sections.
- Use HTML <details><summary> blocks for long sub-sections (e.g. full API table).
- Do NOT wrap the output in triple backticks — return raw Markdown only.
- Do NOT add any preamble, commentary, or closing note outside the Markdown.
"""


# ─── Routes ────────────────────────────────────────────────────────────────────

# 🔹 Standard API Response Function
def api_response(status="success", message="", data=None, code=200):
    return jsonify({
        "status": status,
        "message": message,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    }), code


# 🔹 Health Check Route (BEST PRACTICE)
@app.route("/api/health", methods=["GET"])
def health_check():
    return api_response(
        status="success",
        message="Backend is running perfectly 🚀",
        data={"server": "Flask", "version": "1.0.0"},
        code=200
    )


# 🔹 Root Route
@app.route("/", methods=["GET"])
def index():
    return api_response(
        message="Welcome to ReadmeLab Backend API",
        data={"status_code": 200}
    )


# 🔹 404 Error Handler
@app.errorhandler(404)
def not_found(error):
    return api_response(
        status="error",
        message="Route not found",
        code=404
    )


# 🔹 500 Error Handler
@app.errorhandler(500)
def server_error(error):
    return api_response(
        status="error",
        message="Internal server error",
        code=500
    )


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data         = request.get_json(silent=True) or {}
        step         = data.get("step", "free_chat")
        user_data    = data.get("user_data", {})
        user_message = data.get("user_message", "").strip()
        history      = data.get("history", [])

        # ── Initial greeting ────────────────────────────────────────────────────
        if step == "init":
            return jsonify({
                "reply": (
                    f"Hey there! 👋 I'm **{BOT_NAME}**, your AI assistant.\n\n"
                    "I can **chat with you** about anything, and also help you create a "
                    "**professional README.md** for your project. 🚀\n\n"
                    "Just ask me anything, or say **\"create README\"** whenever you're ready!"
                ),
                "next_step": "free_chat",
                "user_data": user_data,
            })

        # ── Owner question (global shortcut) ───────────────────────────────────
        if is_owner_question(user_message):
            return jsonify(owner_reply(next_step=step, user_data=user_data))

        # ── Dispatch to step handlers ──────────────────────────────────────────
        if step == "free_chat":
            return _handle_free_chat(user_message, user_data, history)

        if step == "readme_ask_name":
            user_data["name"] = user_message
            return jsonify({
                "reply": (
                    f"Nice to meet you, **{user_message}**! 🙌\n\n"
                    "What is the **title / name** of your project?"
                ),
                "next_step": "readme_ask_title",
                "user_data": user_data,
            })

        if step == "readme_ask_title":
            user_data["project_name"] = user_message
            return jsonify({
                "reply": (
                    f"**{user_message}** — love it! 🚀\n\n"
                    "Give me a **brief description** of what your project does:"
                ),
                "next_step": "readme_ask_description",
                "user_data": user_data,
            })

        if step == "readme_ask_description":
            user_data["description"] = user_message
            return jsonify({
                "reply": (
                    "Great description! 📝\n\n"
                    "What **tech stack** are you using?\n"
                    "*(e.g. React, Node.js, Python, Flask, MongoDB…)*"
                ),
                "next_step": "readme_ask_tech",
                "user_data": user_data,
            })

        if step == "readme_ask_tech":
            user_data["tech_stack"] = user_message
            return jsonify({
                "reply": (
                    "Nice stack! 💻\n\n"
                    "Do you have a **live demo link**?\n"
                    "*(Paste the URL, or type `none`)*"
                ),
                "next_step": "readme_ask_live",
                "user_data": user_data,
            })

        if step == "readme_ask_live":
            user_data["live"] = user_message if user_message.lower() != "none" else "Not available"
            name = user_data.get("name", "there")
            return jsonify({
                "reply": (
                    f"Almost done, **{name}**! ✨ Here's your summary:\n\n"
                    f"📌 **Project:** {user_data.get('project_name')}\n"
                    f"📝 **Description:** {user_data.get('description')}\n"
                    f"💻 **Tech Stack:** {user_data.get('tech_stack')}\n"
                    f"🌐 **Live Demo:** {user_data.get('live')}\n\n"
                    "Type **`yes`** to generate your README, or let me know if you want to change anything."
                ),
                "next_step": "readme_confirm",
                "user_data": user_data,
            })

        if step == "readme_confirm":
            return _handle_readme_confirm(user_message, user_data)

        if step == "post_readme":
            return _handle_post_readme(user_message, user_data, history)

        return jsonify({"reply": "Let's start fresh! 🙂", "next_step": "free_chat", "user_data": {}})

    except requests.exceptions.Timeout:
        logger.error("AI API request timed out.")
        return jsonify({
            "reply": "⏳ The AI took too long to respond. Please try again.",
            "next_step": "free_chat",
            "user_data": {},
        }), 504

    except requests.exceptions.RequestException as exc:
        logger.error("Network error calling AI API: %s", exc)
        return jsonify({
            "reply": "❌ Network error. Please check your connection.",
            "next_step": "free_chat",
            "user_data": {},
        }), 502

    except Exception as exc:
        logger.exception("Unexpected error in /chat")
        return jsonify({
            "reply": f"❌ Unexpected error: {exc}",
            "next_step": "free_chat",
            "user_data": {},
        }), 500


# ─── Step Handlers ─────────────────────────────────────────────────────────────

def _handle_free_chat(user_message: str, user_data: dict, history: list):
    if is_readme_trigger(user_message):
        return jsonify({
            "reply": "Awesome! Let's create your **README.md**! 🎉\n\nFirst, what is your **name**?",
            "next_step": "readme_ask_name",
            "user_data": {},
        })

    system = (
        f"You are {BOT_NAME}, a friendly and helpful AI assistant created by {OWNER_NAME}. "
        "You can answer any question — coding, general knowledge, advice, jokes, anything. "
        "Keep responses concise and friendly. "
        "If the user wants to create a README, tell them to say 'create README'. "
        "Never reveal that you are GPT or any other model. You are ReadmeLab, made by Abhishek."
    )
    reply = call_ai(system, user_message, timeout=45, history=history)
    return jsonify({"reply": reply, "next_step": "free_chat", "user_data": user_data})


def _handle_readme_confirm(user_message: str, user_data: dict):
    msg_lower = user_message.lower()

    # ── Handle field-edit requests ─────────────────────────────────────────────
    if any(k in msg_lower for k in ("change", "edit", "update", "modify")):
        for keywords, (next_step, reply_text) in EDIT_FIELD_MAP.items():
            if any(k in msg_lower for k in keywords):
                return jsonify({
                    "reply": reply_text,
                    "next_step": next_step,
                    "user_data": user_data,
                })

    # ── Confirmed — generate README ────────────────────────────────────────────
    if "yes" in msg_lower or msg_lower == "y":
        readme_content = call_ai(
            system_prompt=(
                "You are a professional GitHub README.md generator and technical writer. "
                "You produce exhaustive, beautiful, well-structured Markdown documents. "
                "Return ONLY raw Markdown — no code fences wrapping the full document, "
                "no preamble, no closing remarks."
            ),
            user_prompt=build_readme_prompt(user_data),
            timeout=120,
        )
        user_name = user_data.get("name", "there")
        return jsonify({
            "reply": f"🎉 Your **README.md** is ready, **{user_name}**! Check it out below 👇",
            "next_step": "post_readme",
            "readme": readme_content,
            "user_data": user_data,
            "generated": True,
        })

    return jsonify({
        "reply": "No problem! Type **`yes`** whenever you're ready, or tell me what to change. 😊",
        "next_step": "readme_confirm",
        "user_data": user_data,
    })


def _handle_post_readme(user_message: str, user_data: dict, history: list):
    msg_lower = user_message.lower().strip()

    if is_readme_trigger(user_message) or msg_lower in ("new", "restart", "start over"):
        return jsonify({
            "reply": "Let's create a **new README**! 🎉\n\nWhat is your **name**?",
            "next_step": "readme_ask_name",
            "user_data": {},
        })

    project_context = (
        f"Project: {user_data.get('project_name', '')}, "
        f"Tech: {user_data.get('tech_stack', '')}, "
        f"Desc: {user_data.get('description', '')}"
    )
    system = (
        f"You are {BOT_NAME}, a helpful AI assistant created by {OWNER_NAME}. "
        f"Project context: {project_context}. "
        "You can answer ANY question — general, coding, README-related, or anything else. "
        "Be concise and friendly. Never reveal you are GPT or any other model."
    )
    reply = call_ai(system, user_message, timeout=45, history=history)
    return jsonify({"reply": reply, "next_step": "post_readme", "user_data": user_data})


# ─── Download ──────────────────────────────────────────────────────────────────

@app.route("/download", methods=["POST"])
def download_readme():
    try:
        payload = request.get_json(silent=True) or {}
        content = payload.get("content", "")
        if not content:
            return jsonify({"success": False, "error": "No content provided."}), 400

        stream = io.BytesIO(content.encode("utf-8"))
        return send_file(
            stream,
            mimetype="text/markdown",
            as_attachment=True,
            download_name="README.md",
        )
    except Exception as exc:
        logger.exception("Error in /download")
        return jsonify({"success": False, "error": str(exc)}), 500


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        port=int(os.getenv("PORT", 5000)),
    )
