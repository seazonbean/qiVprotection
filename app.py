import os
import sqlite3
import string
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

app = Flask(__name__, static_folder='static')
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'shortener.db')
app.config['SITE_DOMAIN'] = os.getenv('SITE_DOMAIN', 'localhost:5000')

# 数据库连接管理
def get_db():
    db = sqlite3.connect(
        app.config['DATABASE'],
        detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row
    return db

# 确保数据库表存在
def ensure_tables_exist():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_url TEXT NOT NULL,
        short_code TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        visit_count INTEGER NOT NULL DEFAULT 0
    )
    ''')
    db.commit()

# 生成随机短码
def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# 静态文件路由
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# 首页路由
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

# 创建短链接API
@app.route('/api/shorten', methods=['POST'])
def shorten_url():
    data = request.json
    original_url = data.get('url')
    custom_code = data.get('custom')
    expires_in = data.get('expires', '30d')  # 默认30天

    # 验证URL
    if not original_url:
        return jsonify({'error': 'URL is required'}), 400

    # 处理过期时间
    days = int(expires_in.replace('d', '')) if expires_in != 'never' else None
    expires_at = datetime.now() + timedelta(days=days) if days else None

    db = get_db()
    cursor = db.cursor()

    try:
        # 处理自定义短码
        if custom_code:
            # 检查自定义短码是否已存在
            cursor.execute('SELECT id FROM links WHERE short_code = ?', (custom_code,))
            if cursor.fetchone():
                return jsonify({'error': 'Custom code already exists'}), 409
            short_code = custom_code
        else:
            # 生成唯一短码
            while True:
                short_code = generate_short_code()
                cursor.execute('SELECT id FROM links WHERE short_code = ?', (short_code,))
                if not cursor.fetchone():
                    break

        # 插入数据库
        cursor.execute(
            'INSERT INTO links (original_url, short_code, expires_at) VALUES (?, ?, ?)',
            (original_url, short_code, expires_at.isoformat() if expires_at else None)
        )
        db.commit()

        # 生成短链接
        short_url = f"https://{app.config['SITE_DOMAIN']}/{short_code}"
        return jsonify({
            'short_url': short_url,
            'short_code': short_code,
            'expires_at': expires_at.isoformat() if expires_at else None
        })

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# 短链接跳转
@app.route('/<short_code>')
def redirect_to_original(short_code):
    db = get_db()
    cursor = db.cursor()
    
    try:
        # 查询链接
        cursor.execute(
            'SELECT original_url, expires_at, visit_count FROM links WHERE short_code = ?',
            (short_code,)
        )
        link = cursor.fetchone()

        if not link:
            return jsonify({'error': 'Short code not found'}), 404

        # 检查是否过期
        if link['expires_at'] and datetime.fromisoformat(link['expires_at']) < datetime.now():
            return jsonify({'error': 'Link has expired'}), 410

        # 更新访问计数
        cursor.execute(
            'UPDATE links SET visit_count = ? WHERE short_code = ?',
            (link['visit_count'] + 1, short_code)
        )
        db.commit()

        # 重定向
        return jsonify({'redirect': link['original_url']}), 302

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# 获取链接统计
@app.route('/api/stats/<short_code>')
def get_stats(short_code):
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute(
            'SELECT original_url, created_at, expires_at, visit_count FROM links WHERE short_code = ?',
            (short_code,)
        )
        link = cursor.fetchone()

        if not link:
            return jsonify({'error': 'Short code not found'}), 404

        return jsonify({
            'original_url': link['original_url'],
            'created_at': link['created_at'],
            'expires_at': link['expires_at'],
            'visit_count': link['visit_count']
        })
    finally:
        db.close()

# 初始化数据库
with app.app_context():
    ensure_tables_exist()

# 启动应用
if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('FLASK_ENV') == 'development'
    )
    
