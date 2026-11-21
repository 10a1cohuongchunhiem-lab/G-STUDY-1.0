#!/usr/bin/env python3
"""G-Study / English10 application server (Python standard library + SQLite)."""
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(ROOT, 'english10.db')
DB = os.environ.get('DB_PATH', DEFAULT_DB)
if DB != DEFAULT_DB:
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    if not os.path.exists(DB) and os.path.exists(DEFAULT_DB):
        shutil.copy2(DEFAULT_DB, DB)
HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', '8090'))
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@lingo10.vn').strip().lower()


def db():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    return c


def hash_pw(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 210000)
    return salt.hex() + ':' + digest.hex()


def check_pw(password, stored):
    try:
        salt_hex, expected = stored.split(':', 1)
        salt = bytes.fromhex(salt_hex)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 210000).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def seed_curriculum(c):
    units = [
        ('u1', 'Unit 1: Family life', 'Family life'),
        ('u2', 'Unit 2: Humans and the environment', 'Humans and the environment'),
        ('u3', 'Unit 3: Music', 'Music'),
        ('u4', 'Unit 4: For a better community', 'For a better community'),
        ('u5', 'Unit 5: Inventions', 'Inventions'),
        ('u6', 'Unit 6: Gender equality', 'Gender equality'),
        ('u7', 'Unit 7: Viet Nam and international organisations', 'Viet Nam and international organisations'),
        ('u8', 'Unit 8: New ways to learn', 'New ways to learn'),
        ('u9', 'Unit 9: Protecting the environment', 'Protecting the environment'),
        ('u10', 'Unit 10: Ecotourism', 'Ecotourism'),
    ]
    activities = {
        'u1': ('household chores', 'Who usually does the cooking in your family?', 'I help my family with household chores.'),
        'u2': ('green lifestyle', 'What can students do to protect the environment?', 'We should reduce plastic waste and save energy.'),
        'u3': ('music', 'What kind of music do you enjoy?', 'Music helps me relax and connect with other people.'),
        'u4': ('volunteering', 'Why do people volunteer?', 'Volunteers help people in need and improve their community.'),
        'u5': ('smartphone', 'How does a smartphone help students learn?', 'It gives students quick access to useful information.'),
        'u6': ('equal opportunity', 'What does gender equality mean?', 'Everyone should have equal opportunities at school and work.'),
        'u7': ('international cooperation', 'What does Viet Nam contribute to international cooperation?', 'Viet Nam works with other countries to build peace and development.'),
        'u8': ('online learning', 'What is one advantage of online learning?', 'Learners can study flexibly and review lessons at their own pace.'),
        'u9': ('biodiversity', 'Why should we protect biodiversity?', 'Biodiversity keeps ecosystems healthy and supports human life.'),
        'u10': ('responsible tourism', 'How can tourists protect a destination?', 'Tourists should respect local people, wildlife and the environment.'),
    }
    module_specs = [('Vocabulary', 'vocabulary'), ('Reading', 'reading'), ('Listening', 'listening'), ('Speaking', 'speaking'), ('Writing', 'writing')]
    for ui, (uid, title, topic) in enumerate(units, 1):
        c.execute('INSERT OR IGNORE INTO lessons(id,title,unit,content_json) VALUES(?,?,?,?)',
                  (uid, title, f'Unit {ui}', json.dumps({'source': 'KNTT Global Success 10', 'status': 'adapted_practice', 'topic': topic}, ensure_ascii=False)))
        key, question, model = activities[uid]
        for mi, (skill, kind) in enumerate(module_specs, 1):
            mid = f'{uid}-m{mi}'
            c.execute('INSERT OR IGNORE INTO modules(id,lesson_id,title,skill,minutes,sort_order) VALUES(?,?,?,?,?,?)',
                      (mid, uid, skill, kind, 5, mi))
            prompts = [f'Choose the best meaning of “{key}”.', question, f'Complete a short {skill.lower()} task about {key}.']
            answers = [key, topic, model]
            for ii in range(3):
                iid = f'{mid}-i{ii+1}'
                typ = 'mcq' if ii == 0 else ('audio' if kind == 'listening' else ('recording' if kind == 'speaking' else ('text' if kind == 'writing' else 'short_answer')))
                opts = [key, 'an unrelated idea', 'a difficult problem', 'a school subject'] if ii == 0 else []
                rubric = {'accuracy': 40, 'vocabulary': 20, 'grammar': 20, 'communication': 20} if kind in ('speaking', 'writing') else {}
                c.execute('INSERT OR IGNORE INTO items(id,module_id,item_type,prompt,answer,options_json,media_url,rubric_json,sort_order) VALUES(?,?,?,?,?,?,?,?,?)',
                          (iid, mid, typ, prompts[ii], answers[ii], json.dumps(opts, ensure_ascii=False), None, json.dumps(rubric, ensure_ascii=False), ii + 1))


def init():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      password_hash TEXT,
      role TEXT NOT NULL DEFAULT 'student',
      google_sub TEXT UNIQUE,
      verified INTEGER NOT NULL DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS reset_tokens(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires INTEGER NOT NULL,used INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),lesson_id TEXT NOT NULL,module_id TEXT,score REAL NOT NULL,duration INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY,title TEXT NOT NULL,unit TEXT NOT NULL,content_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS modules(id TEXT PRIMARY KEY,lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,title TEXT NOT NULL,skill TEXT NOT NULL,minutes INTEGER DEFAULT 5,sort_order INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,item_type TEXT NOT NULL,prompt TEXT NOT NULL,answer TEXT,options_json TEXT,media_url TEXT,rubric_json TEXT,sort_order INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS progress(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,completed INTEGER DEFAULT 0,best_score REAL DEFAULT 0,seconds INTEGER DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,lesson_id));
    CREATE TABLE IF NOT EXISTS module_progress(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,completed INTEGER DEFAULT 0,best_score REAL DEFAULT 0,seconds INTEGER DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,module_id));
    CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,rating INTEGER NOT NULL,comment TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')
    # Safe in-place migration for databases created by earlier G-Study builds.
    user_columns = {row['name'] for row in c.execute('PRAGMA table_info(users)')}
    if 'is_active' not in user_columns:
        c.execute('ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
    attempt_columns = {row['name'] for row in c.execute('PRAGMA table_info(attempts)')}
    if 'module_id' not in attempt_columns:
        c.execute('ALTER TABLE attempts ADD COLUMN module_id TEXT')
    c.execute('CREATE INDEX IF NOT EXISTS idx_attempts_module_id ON attempts(module_id)')
    defaults = {
        'app_name': 'G-Study',
        'contact_phone': '0888074418',
        'registration_open': '1',
        'weekly_goal_minutes': '20',
    }
    for key, value in defaults.items():
        c.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)', (key, value))

    admin = c.execute('SELECT id FROM users WHERE email=?', (ADMIN_EMAIL,)).fetchone()
    if not admin:
        bootstrap = os.environ.get('ADMIN_PASSWORD')
        if not bootstrap:
            bootstrap = secrets.token_urlsafe(18)
            print(f'[G-STUDY] New admin created: {ADMIN_EMAIL} / {bootstrap}', flush=True)
        c.execute('INSERT INTO users(email,name,password_hash,role,verified,is_active) VALUES(?,?,?,?,1,1)',
                  (ADMIN_EMAIL, 'Quản trị viên', hash_pw(bootstrap), 'admin'))
    elif os.environ.get('RESET_ADMIN_PASSWORD') == '1' and os.environ.get('ADMIN_PASSWORD'):
        c.execute('UPDATE users SET password_hash=?,is_active=1 WHERE email=? AND role="admin"',
                  (hash_pw(os.environ['ADMIN_PASSWORD']), ADMIN_EMAIL))
        c.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)', (ADMIN_EMAIL,))
        print('[G-STUDY] Admin password rotated from environment configuration.', flush=True)

    seed_curriculum(c)
    c.commit()
    c.close()


def request_body(handler):
    try:
        length = min(int(handler.headers.get('Content-Length', '0')), 1_000_000)
        raw = handler.rfile.read(length) if length else b'{}'
        data = json.loads(raw or b'{}')
        return data if isinstance(data, dict) else {}
    except (ValueError, json.JSONDecodeError):
        return {}


def send(handler, status, data, headers=None):
    raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(raw)))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(raw)


def safe_user(row):
    if not row:
        return None
    return {key: row[key] for key in row.keys() if key not in ('password_hash', 'google_sub')}


def session_token(handler):
    cookie = SimpleCookie()
    try:
        cookie.load(handler.headers.get('Cookie', ''))
        morsel = cookie.get('session')
        return morsel.value if morsel else None
    except Exception:
        return None


def current_user(handler):
    token = session_token(handler)
    if not token:
        return None
    c = db()
    row = c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',
                    (token, int(time.time()))).fetchone()
    c.close()
    return row


def cookie_header(handler, token, max_age=1209600):
    secure = '; Secure' if (handler.headers.get('X-Forwarded-Proto', '').lower() == 'https' or getattr(handler, 'is_https', False)) else ''
    return f'session={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax{secure}'


def require_admin(handler):
    u = current_user(handler)
    return u if u and u['role'] == 'admin' and u['is_active'] else None


def get_settings(c):
    return {row['key']: row['value'] for row in c.execute('SELECT key,value FROM app_settings')}


class App(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        if path == '/api/me':
            u = current_user(self)
            if u and not u['is_active']:
                return send(self, 403, {'error': 'Tài khoản đã tạm khóa. Vui lòng liên hệ quản trị viên.'})
            return send(self, 200, {'user': safe_user(u)})

        if path == '/api/public-settings':
            c = db()
            settings = get_settings(c)
            c.close()
            return send(self, 200, {'settings': {key: settings.get(key) for key in ('app_name', 'contact_phone', 'weekly_goal_minutes', 'registration_open')}})

        if path == '/api/lessons':
            u = current_user(self)
            if not u or not u['is_active']:
                return send(self, 401, {'error': 'unauthorized'})
            c = db()
            rows = [dict(x) for x in c.execute('''
              SELECT l.id,l.title,l.unit,COUNT(DISTINCT m.id) module_count,
                     COUNT(i.id) item_count
              FROM lessons l LEFT JOIN modules m ON m.lesson_id=l.id
              LEFT JOIN items i ON i.module_id=m.id GROUP BY l.id ORDER BY l.rowid
            ''')]
            for lesson_row in rows:
                lesson_row['modules'] = [dict(module) for module in c.execute(
                    'SELECT id,title,skill,minutes,sort_order FROM modules WHERE lesson_id=? ORDER BY sort_order',
                    (lesson_row['id'],))]
            c.close()
            return send(self, 200, {'lessons': rows})

        if path.startswith('/api/lesson/'):
            u = current_user(self)
            if not u or not u['is_active']:
                return send(self, 401, {'error': 'unauthorized'})
            lesson_id = path.rsplit('/', 1)[-1]
            c = db()
            lesson = c.execute('SELECT id,title,unit,content_json FROM lessons WHERE id=?', (lesson_id,)).fetchone()
            if not lesson:
                c.close()
                return send(self, 404, {'error': 'Không tìm thấy bài học.'})
            modules = [dict(x) for x in c.execute('SELECT id,lesson_id,title,skill,minutes,sort_order FROM modules WHERE lesson_id=? ORDER BY sort_order', (lesson_id,))]
            for module in modules:
                module['items'] = [dict(x) for x in c.execute('SELECT id,item_type,prompt,answer,options_json,media_url,rubric_json,sort_order FROM items WHERE module_id=? ORDER BY sort_order', (module['id'],))]
            c.close()
            return send(self, 200, {'lesson': dict(lesson), 'modules': modules})

        if path == '/api/progress':
            u = current_user(self)
            if not u or not u['is_active']:
                return send(self, 401, {'error': 'unauthorized'})
            c = db()
            progress_rows = [dict(x) for x in c.execute('''
              SELECT p.*,l.title,l.unit FROM progress p JOIN lessons l ON l.id=p.lesson_id
              WHERE p.user_id=? ORDER BY p.updated_at DESC
            ''', (u['id'],))]
            aggregate = c.execute('''SELECT COUNT(*) attempts,COALESCE(AVG(score),0) average,
              COALESCE(SUM(duration),0) seconds FROM attempts WHERE user_id=?''', (u['id'],)).fetchone()
            today = c.execute('''SELECT COUNT(*) attempts,COALESCE(AVG(score),0) average,
              COALESCE(SUM(duration),0) seconds FROM attempts WHERE user_id=? AND date(created_at)=date('now','localtime')''', (u['id'],)).fetchone()
            week = c.execute('''SELECT COALESCE(SUM(duration),0) seconds FROM attempts
              WHERE user_id=? AND created_at >= datetime('now','-7 day')''', (u['id'],)).fetchone()
            configured_settings = get_settings(c)
            weekly_goal_seconds = max(10, int(configured_settings.get('weekly_goal_minutes', '20'))) * 60
            module_progress_rows = [dict(x) for x in c.execute('''SELECT mp.module_id,mp.completed,mp.best_score,mp.seconds,mp.updated_at,
              m.title module_title,m.skill,l.id lesson_id,l.title lesson_title,l.unit
              FROM module_progress mp JOIN modules m ON m.id=mp.module_id JOIN lessons l ON l.id=m.lesson_id
              WHERE mp.user_id=? ORDER BY mp.updated_at DESC''', (u['id'],))]
            recent = [dict(x) for x in c.execute('''SELECT a.id,a.lesson_id,a.module_id,
              COALESCE(m.title,l.title,a.lesson_id) title,l.unit,a.score,a.duration,a.created_at
              FROM attempts a LEFT JOIN lessons l ON l.id=a.lesson_id LEFT JOIN modules m ON m.id=a.module_id
              WHERE a.user_id=? ORDER BY a.created_at DESC,a.id DESC LIMIT 8''', (u['id'],))]
            recent_feedback = c.execute('SELECT rating,comment,created_at FROM feedback WHERE user_id=? ORDER BY id DESC LIMIT 1', (u['id'],)).fetchone()
            out = {
                'progress': progress_rows,
                'module_progress': module_progress_rows,
                'recent': recent,
                'latest_feedback': dict(recent_feedback) if recent_feedback else None,
                'summary': {
                    'attempts': aggregate['attempts'], 'average': round(aggregate['average'], 1),
                    'seconds': aggregate['seconds'], 'completed': sum(1 for x in progress_rows if x['completed']),
                    'today_attempts': today['attempts'], 'today_average': round(today['average'], 1),
                    'today_seconds': today['seconds'], 'today_xp': round(today['average'] * today['attempts'] / 5),
                    'week_seconds': week['seconds'], 'week_goal_seconds': weekly_goal_seconds,
                }
            }
            c.close()
            return send(self, 200, out)

        if path.startswith('/api/admin/'):
            u = require_admin(self)
            if not u:
                return send(self, 403, {'error': 'Bạn không có quyền truy cập khu vực quản trị.'})
            c = db()
            if path == '/api/admin/stats':
                stats = {
                    'students': c.execute("SELECT COUNT(*) n FROM users WHERE role='student'").fetchone()['n'],
                    'active_students': c.execute("SELECT COUNT(*) n FROM users WHERE role='student' AND is_active=1").fetchone()['n'],
                    'attempts': c.execute('SELECT COUNT(*) n FROM attempts').fetchone()['n'],
                    'average': round(c.execute('SELECT COALESCE(AVG(score),0) n FROM attempts').fetchone()['n'], 1),
                    'active_7d': c.execute("SELECT COUNT(DISTINCT user_id) n FROM attempts WHERE created_at >= datetime('now','-7 day')").fetchone()['n'],
                    'lessons': c.execute('SELECT COUNT(*) n FROM lessons').fetchone()['n'],
                    'feedback': c.execute('SELECT COUNT(*) n FROM feedback').fetchone()['n'],
                }
                c.close()
                return send(self, 200, stats)
            if path == '/api/admin/lessons':
                lessons = [dict(x) for x in c.execute('''SELECT l.id,l.title,l.unit,l.content_json,
                  COUNT(DISTINCT m.id) module_count,COUNT(i.id) item_count FROM lessons l
                  LEFT JOIN modules m ON m.lesson_id=l.id LEFT JOIN items i ON i.module_id=m.id
                  GROUP BY l.id ORDER BY l.rowid''')]
                c.close()
                return send(self, 200, {'lessons': lessons})
            if path == '/api/admin/students':
                students = [dict(x) for x in c.execute('''SELECT u.id,u.email,u.name,u.created_at,u.is_active,
                  COUNT(a.id) attempts,COALESCE(AVG(a.score),0) average,COALESCE(SUM(a.duration),0) seconds
                  FROM users u LEFT JOIN attempts a ON a.user_id=u.id WHERE u.role='student'
                  GROUP BY u.id ORDER BY u.created_at DESC''')]
                c.close()
                return send(self, 200, {'students': students})
            if path == '/api/admin/attempts':
                attempts = [dict(x) for x in c.execute('''SELECT a.id,u.email,u.name,a.lesson_id,
                  COALESCE(m.title,l.title,a.lesson_id) title,a.score,a.duration,a.created_at FROM attempts a
                  JOIN users u ON u.id=a.user_id LEFT JOIN lessons l ON l.id=a.lesson_id
                  LEFT JOIN modules m ON m.id=a.module_id
                  ORDER BY a.created_at DESC,a.id DESC LIMIT 300''')]
                c.close()
                return send(self, 200, {'attempts': attempts})
            if path == '/api/admin/feedback':
                rows = [dict(x) for x in c.execute('''SELECT f.id,u.name,u.email,f.rating,f.comment,f.created_at
                  FROM feedback f JOIN users u ON u.id=f.user_id ORDER BY f.created_at DESC,f.id DESC LIMIT 300''')]
                c.close()
                return send(self, 200, {'feedback': rows})
            if path == '/api/admin/settings':
                settings = get_settings(c)
                c.close()
                return send(self, 200, {'settings': settings})
            c.close()
            return send(self, 404, {'error': 'not_found'})

        if path in ('/', '/index.html', '/admin'):
            try:
                data = open(os.path.join(ROOT, 'index.html'), 'rb').read()
            except FileNotFoundError:
                return send(self, 404, {'error': 'missing index'})
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)
            return
        return send(self, 404, {'error': 'not_found'})

    def do_POST(self):
        path = urlparse(self.path).path
        data = request_body(self)
        c = db()
        try:
            if path == '/api/register':
                settings = get_settings(c)
                if settings.get('registration_open', '1') != '1':
                    return send(self, 403, {'error': 'Tạm thời đã đóng đăng ký tài khoản mới.'})
                email = str(data.get('email', '')).strip().lower()
                name = str(data.get('name', '')).strip() or email.split('@')[0]
                password = str(data.get('password', ''))
                if '@' not in email or len(password) < 8:
                    return send(self, 400, {'error': 'Email hợp lệ và mật khẩu ít nhất 8 ký tự.'})
                c.execute('INSERT INTO users(email,name,password_hash,role,verified,is_active) VALUES(?,?,?,"student",1,1)',
                          (email, name[:80], hash_pw(password)))
                c.commit()
                return self.login(c, email, password)

            if path == '/api/login':
                email = str(data.get('email', '')).strip().lower()
                password = str(data.get('password', ''))
                row = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
                if not row or not row['password_hash'] or not check_pw(password, row['password_hash']):
                    return send(self, 401, {'error': 'Email hoặc mật khẩu không đúng.'})
                if not row['is_active']:
                    return send(self, 403, {'error': 'Tài khoản đang bị tạm khóa. Vui lòng liên hệ quản trị viên.'})
                return self.login(c, email, password)

            if path == '/api/logout':
                token = session_token(self)
                if token:
                    c.execute('DELETE FROM sessions WHERE token=?', (token,))
                    c.commit()
                return send(self, 200, {'ok': True}, {'Set-Cookie': cookie_header(self, '', 0)})

            if path == '/api/change-password':
                u = current_user(self)
                if not u or not u['is_active']:
                    return send(self, 401, {'error': 'unauthorized'})
                current = str(data.get('current_password', ''))
                new = str(data.get('new_password', ''))
                if len(new) < 8:
                    return send(self, 400, {'error': 'Mật khẩu mới cần ít nhất 8 ký tự.'})
                if not u['password_hash'] or not check_pw(current, u['password_hash']):
                    return send(self, 400, {'error': 'Mật khẩu hiện tại chưa chính xác.'})
                c.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_pw(new), u['id']))
                c.execute('DELETE FROM sessions WHERE user_id=?', (u['id'],))
                c.commit()
                return send(self, 200, {'ok': True, 'message': 'Đổi mật khẩu thành công. Hãy đăng nhập lại.'},
                            {'Set-Cookie': cookie_header(self, '', 0)})

            if path == '/api/feedback':
                u = current_user(self)
                if not u or not u['is_active']:
                    return send(self, 401, {'error': 'unauthorized'})
                try:
                    rating = int(data.get('rating', 0))
                except (TypeError, ValueError):
                    rating = 0
                comment = str(data.get('comment', '')).strip()[:1200]
                if rating < 1 or rating > 5:
                    return send(self, 400, {'error': 'Vui lòng chọn số sao từ 1 đến 5.'})
                c.execute('INSERT INTO feedback(user_id,rating,comment) VALUES(?,?,?)', (u['id'], rating, comment))
                c.commit()
                return send(self, 201, {'ok': True, 'message': 'Cảm ơn bạn đã gửi đánh giá!'})

            if path.startswith('/api/admin/'):
                u = require_admin(self)
                if not u:
                    return send(self, 403, {'error': 'Bạn không có quyền quản trị.'})

                if path == '/api/admin/settings':
                    allowed = {'app_name', 'contact_phone', 'registration_open', 'weekly_goal_minutes'}
                    for key, value in data.items():
                        if key in allowed:
                            v = str(value).strip()
                            if key == 'registration_open':
                                v = '1' if v in ('1', 'true', 'True', 'on') else '0'
                            elif key == 'weekly_goal_minutes':
                                try:
                                    v = str(max(10, min(1000, int(v))))
                                except ValueError:
                                    return send(self, 400, {'error': 'Mục tiêu tuần không hợp lệ.'})
                            elif key == 'contact_phone':
                                v = re.sub(r'[^0-9+ ()-]', '', v)[:30]
                            else:
                                v = v[:80]
                            c.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, v))
                    c.commit()
                    return send(self, 200, {'ok': True, 'settings': get_settings(c)})

                if path == '/api/admin/students/toggle':
                    student_id = int(data.get('id', 0))
                    active = 1 if data.get('is_active') else 0
                    cur = c.execute("UPDATE users SET is_active=? WHERE id=? AND role='student'", (active, student_id))
                    c.commit()
                    if not cur.rowcount:
                        return send(self, 404, {'error': 'Không tìm thấy tài khoản học sinh.'})
                    if not active:
                        c.execute('DELETE FROM sessions WHERE user_id=?', (student_id,))
                        c.commit()
                    return send(self, 200, {'ok': True})

                if path == '/api/admin/students/password':
                    student_id = int(data.get('id', 0))
                    password = str(data.get('password', ''))
                    if len(password) < 8:
                        return send(self, 400, {'error': 'Mật khẩu tạm cần ít nhất 8 ký tự.'})
                    cur = c.execute("UPDATE users SET password_hash=? WHERE id=? AND role='student'", (hash_pw(password), student_id))
                    c.commit()
                    if not cur.rowcount:
                        return send(self, 404, {'error': 'Không tìm thấy tài khoản học sinh.'})
                    c.execute('DELETE FROM sessions WHERE user_id=?', (student_id,))
                    c.commit()
                    return send(self, 200, {'ok': True})

                if path in ('/api/admin/lessons/create', '/api/admin/lessons/update', '/api/admin/lessons/delete'):
                    lesson_id = str(data.get('id', '')).strip()
                    if not re.fullmatch(r'[A-Za-z0-9_-]{2,60}', lesson_id):
                        return send(self, 400, {'error': 'Mã bài học chỉ gồm chữ, số, gạch ngang hoặc gạch dưới.'})
                    if path.endswith('/create'):
                        title, unit = str(data.get('title', '')).strip(), str(data.get('unit', '')).strip()
                        if not title or not unit:
                            return send(self, 400, {'error': 'Cần nhập tên bài học và Unit.'})
                        content = data.get('content_json') or json.dumps({'questions': []}, ensure_ascii=False)
                        c.execute('INSERT INTO lessons(id,title,unit,content_json) VALUES(?,?,?,?)', (lesson_id, title[:160], unit[:80], content))
                        c.commit()
                        return send(self, 201, {'ok': True})
                    if path.endswith('/delete'):
                        c.execute('DELETE FROM lessons WHERE id=?', (lesson_id,))
                        c.commit()
                        return send(self, 200, {'ok': True})
                    c.execute('UPDATE lessons SET title=?,unit=?,content_json=? WHERE id=?',
                              (str(data.get('title', '')).strip()[:160], str(data.get('unit', '')).strip()[:80],
                               data.get('content_json', '{"questions":[]}'), lesson_id))
                    c.commit()
                    return send(self, 200, {'ok': True})

                if path in ('/api/admin/modules/create', '/api/admin/modules/update', '/api/admin/modules/delete'):
                    module_id = str(data.get('id', '')).strip()
                    if path.endswith('/create'):
                        module_id = module_id or 'm_' + secrets.token_hex(5)
                        if not re.fullmatch(r'[A-Za-z0-9_-]{2,60}', module_id):
                            return send(self, 400, {'error': 'Mã kỹ năng không hợp lệ.'})
                        sort_order = int(data.get('sort_order', 0))
                        if sort_order <= 0:
                            sort_order = c.execute('SELECT COALESCE(MAX(sort_order),0)+1 n FROM modules WHERE lesson_id=?',
                                                   (data['lesson_id'],)).fetchone()['n']
                        c.execute('INSERT INTO modules(id,lesson_id,title,skill,minutes,sort_order) VALUES(?,?,?,?,?,?)',
                                  (module_id, data['lesson_id'], str(data['title'])[:100], str(data.get('skill', 'general'))[:50],
                                   max(1, min(180, int(data.get('minutes', 5)))), sort_order))
                        c.commit()
                        return send(self, 201, {'ok': True, 'id': module_id})
                    if path.endswith('/delete'):
                        c.execute('DELETE FROM modules WHERE id=?', (module_id,))
                        c.commit()
                        return send(self, 200, {'ok': True})
                    c.execute('UPDATE modules SET title=?,skill=?,minutes=?,sort_order=? WHERE id=?',
                              (str(data.get('title', ''))[:100], str(data.get('skill', 'general'))[:50],
                               max(1, min(180, int(data.get('minutes', 5)))), int(data.get('sort_order', 0)), module_id))
                    c.commit()
                    return send(self, 200, {'ok': True})

                if path in ('/api/admin/items/create', '/api/admin/items/update', '/api/admin/items/delete'):
                    item_id = str(data.get('id', '')).strip()
                    if path.endswith('/create'):
                        item_id = item_id or 'q_' + secrets.token_hex(5)
                        if not re.fullmatch(r'[A-Za-z0-9_-]{2,60}', item_id):
                            return send(self, 400, {'error': 'Mã câu hỏi không hợp lệ.'})
                        options = data.get('options') if isinstance(data.get('options'), list) else []
                        sort_order = int(data.get('sort_order', 0))
                        if sort_order <= 0:
                            sort_order = c.execute('SELECT COALESCE(MAX(sort_order),0)+1 n FROM items WHERE module_id=?',
                                                   (data['module_id'],)).fetchone()['n']
                        c.execute('''INSERT INTO items(id,module_id,item_type,prompt,answer,options_json,media_url,rubric_json,sort_order)
                          VALUES(?,?,?,?,?,?,?,?,?)''',
                          (item_id, data['module_id'], str(data.get('item_type', 'short_answer'))[:30],
                           str(data.get('prompt', '')).strip()[:1200], str(data.get('answer', ''))[:1200],
                           json.dumps(options[:20], ensure_ascii=False), data.get('media_url'),
                           json.dumps(data.get('rubric', {}), ensure_ascii=False), sort_order))
                        c.commit()
                        return send(self, 201, {'ok': True, 'id': item_id})
                    if path.endswith('/delete'):
                        c.execute('DELETE FROM items WHERE id=?', (item_id,))
                        c.commit()
                        return send(self, 200, {'ok': True})
                    options = data.get('options') if isinstance(data.get('options'), list) else []
                    c.execute('''UPDATE items SET item_type=?,prompt=?,answer=?,options_json=?,media_url=?,rubric_json=?,sort_order=? WHERE id=?''',
                              (str(data.get('item_type', 'short_answer'))[:30], str(data.get('prompt', '')).strip()[:1200],
                               str(data.get('answer', ''))[:1200], json.dumps(options[:20], ensure_ascii=False),
                               data.get('media_url'), json.dumps(data.get('rubric', {}), ensure_ascii=False),
                               int(data.get('sort_order', 0)), item_id))
                    c.commit()
                    return send(self, 200, {'ok': True})

                return send(self, 404, {'error': 'not_found'})

            if path == '/api/attempt':
                u = current_user(self)
                if not u or not u['is_active']:
                    return send(self, 401, {'error': 'unauthorized'})
                lesson_id = str(data.get('lesson_id', '')).strip()
                if not c.execute('SELECT 1 FROM lessons WHERE id=?', (lesson_id,)).fetchone():
                    return send(self, 400, {'error': 'Bài học không tồn tại.'})
                try:
                    score = max(0, min(100, float(data.get('score', 0))))
                    seconds = max(0, min(86400, int(data.get('duration', 0))))
                except (ValueError, TypeError):
                    return send(self, 400, {'error': 'Kết quả học tập không hợp lệ.'})
                completed = 1 if data.get('completed', 1) else 0
                module_id = str(data.get('module_id', '')).strip() or None
                if module_id and not c.execute('SELECT 1 FROM modules WHERE id=? AND lesson_id=?', (module_id, lesson_id)).fetchone():
                    return send(self, 400, {'error': 'Kỹ năng học không thuộc Unit này.'})
                c.execute('INSERT INTO attempts(user_id,lesson_id,module_id,score,duration) VALUES(?,?,?,?,?)',
                          (u['id'], lesson_id, module_id, score, seconds))
                if module_id:
                    c.execute('''INSERT INTO module_progress(user_id,module_id,completed,best_score,seconds)
                      VALUES(?,?,1,?,?) ON CONFLICT(user_id,module_id) DO UPDATE SET
                      completed=1,best_score=MAX(module_progress.best_score,excluded.best_score),
                      seconds=module_progress.seconds+excluded.seconds,updated_at=CURRENT_TIMESTAMP''',
                      (u['id'], module_id, score, seconds))
                    module_total = c.execute('SELECT COUNT(*) n FROM modules WHERE lesson_id=?', (lesson_id,)).fetchone()['n']
                    module_done = c.execute('''SELECT COUNT(*) n FROM module_progress mp JOIN modules m ON m.id=mp.module_id
                      WHERE mp.user_id=? AND m.lesson_id=? AND mp.completed=1''', (u['id'], lesson_id)).fetchone()['n']
                    legacy_progress = c.execute('SELECT completed FROM progress WHERE user_id=? AND lesson_id=?',
                                                (u['id'], lesson_id)).fetchone()
                    unit_completed = 1 if module_total > 0 and module_done >= module_total else (legacy_progress['completed'] if legacy_progress else 0)
                else:
                    unit_completed = completed
                c.execute('''INSERT INTO progress(user_id,lesson_id,completed,best_score,seconds)
                  VALUES(?,?,?,?,?) ON CONFLICT(user_id,lesson_id) DO UPDATE SET
                  completed=MAX(progress.completed,excluded.completed),
                  best_score=MAX(progress.best_score,excluded.best_score),
                  seconds=progress.seconds+excluded.seconds,updated_at=CURRENT_TIMESTAMP''',
                  (u['id'], lesson_id, unit_completed, score, seconds))
                c.commit()
                return send(self, 200, {'ok': True})

            return send(self, 404, {'error': 'not_found'})
        except sqlite3.IntegrityError as exc:
            msg = 'Dữ liệu đã tồn tại hoặc đang được sử dụng.'
            if path == '/api/register':
                msg = 'Email này đã được đăng ký.'
            return send(self, 409, {'error': msg})
        except (KeyError, ValueError, TypeError) as exc:
            return send(self, 400, {'error': 'Dữ liệu gửi lên chưa hợp lệ.'})
        finally:
            c.close()

    def login(self, connection, email, password):
        row = connection.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if not row or not row['is_active'] or not row['password_hash'] or not check_pw(password, row['password_hash']):
            return send(self, 401, {'error': 'Email hoặc mật khẩu không đúng.'})
        token = secrets.token_urlsafe(36)
        connection.execute('INSERT INTO sessions(token,user_id,expires) VALUES(?,?,?)',
                           (token, row['id'], int(time.time()) + 86400 * 14))
        connection.commit()
        return send(self, 200, {'user': safe_user(row)}, {'Set-Cookie': cookie_header(self, token)})


if __name__ == '__main__':
    init()
    print(f'G-Study server is running on http://127.0.0.1:{PORT}', flush=True)
    ThreadingHTTPServer((HOST, PORT), App).serve_forever()
