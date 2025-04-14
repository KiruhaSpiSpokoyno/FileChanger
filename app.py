"""
FileChanger - веб-приложение для обмена файлами и ссылками в локальной сети.
Подробная документация доступна в README.md
"""

from flask import Flask, request, render_template, send_file, redirect, url_for, jsonify, session
import os
from werkzeug.utils import secure_filename
import socket
import time
from datetime import datetime
import json
import qrcode
from user_agents import parse

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Максимальный размер файла 16MB
app.secret_key = 'your-secret-key-here'  # Замените на реальный секретный ключ
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp3', 'mp4', 'zip'}

# Создаем необходимые директории
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('Base', exist_ok=True)

# Словарь для хранения информации о подключенных устройствах
connected_devices = {}

# Пути к файлам с информацией
FILE_OWNERS_PATH = os.path.join('Base', 'file_owners.json')
LINK_OWNERS_PATH = os.path.join('Base', 'link_owners.json')
LINKS_PATH = os.path.join('Base', 'links.json')
USERS_PATH = os.path.join('Base', 'users.json')
OWNER_PATH = os.path.join('Base', 'owner.txt')
DEVICES_PATH = os.path.join('Base', 'devices.json')

def get_owner():
    if os.path.exists(OWNER_PATH):
        with open(OWNER_PATH, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def set_owner(username):
    os.makedirs(os.path.dirname(OWNER_PATH), exist_ok=True)
    with open(OWNER_PATH, 'w', encoding='utf-8') as f:
        f.write(username)

def load_json(path, default_value):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default_value

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_users():
    return load_json(USERS_PATH, {})

def save_users(users):
    save_json(USERS_PATH, users)

def load_file_owners():
    return load_json(FILE_OWNERS_PATH, {})

def save_file_owners(owners):
    save_json(FILE_OWNERS_PATH, owners)

def load_link_owners():
    return load_json(LINK_OWNERS_PATH, {})

def save_link_owners(owners):
    save_json(LINK_OWNERS_PATH, owners)

def load_links():
    return load_json(LINKS_PATH, [])

def save_links(links):
    save_json(LINKS_PATH, links)

def get_local_ip():
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        return ip_address
    except:
        return "localhost"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def can_delete_file(filename):
    if 'user_id' not in session:
        return False
    
    owners = load_file_owners()
    if filename not in owners:
        return False
    
    return owners[filename]['owner'] == session['user_id'] or owners[filename]['uploader'] == session['user_id']

def can_delete_link(link):
    if 'user_id' not in session:
        return False
    
    owners = load_link_owners()
    if link not in owners:
        return False
    
    return owners[link]['owner'] == session['user_id'] or owners[link]['uploader'] == session['user_id']

def is_owner():
    return 'username' in session and session['username'] == get_owner()

@app.before_request
def check_login():
    if request.endpoint != 'login' and 'username' not in session and request.endpoint != 'set_username':
        return redirect(url_for('login'))

@app.before_request
def track_visitor():
    if request.remote_addr != '127.0.0.1' and 'username' in session:  # Исключаем локальные запросы
        current_time = datetime.now().strftime("%H:%M:%S")
        user_agent = request.headers.get('User-Agent', 'Unknown')
        device_type = 'Мобильное устройство' if 'Mobile' in user_agent else 'Компьютер'
        connected_devices[request.remote_addr] = {
            'last_seen': current_time,
            'device_type': device_type,
            'user_agent': user_agent,
            'username': session['username']
        }
    
    # Создаем уникальный идентификатор для пользователя, если его нет
    if 'user_id' not in session and 'username' in session:
        session['user_id'] = str(time.time()) + request.remote_addr

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    update_device_info()
    username = session['username']
    is_owner = username == get_owner()
    
    # Получаем список файлов в директории загрузок
    files = []
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
                files.append(filename)
    
    # Загружаем остальные данные
    links = load_links()
    link_owners = load_link_owners()
    devices = load_json(DEVICES_PATH, {})
    file_owners = load_file_owners()
    
    # Определяем, какие файлы и ссылки может удалить текущий пользователь
    deletable_files = {file: can_delete_file(file) for file in files}
    deletable_links = {link: can_delete_link(link) for link in links}
    
    return render_template('index.html',
                         username=username,
                         is_owner=is_owner,
                         files=files,
                         links=links,
                         deletable_files=deletable_files,
                         deletable_links=deletable_links,
                         local_ip=get_local_ip(),
                         connected_devices=devices)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # Сохраняем информацию о владельце файла
        owners = load_file_owners()
        owners[filename] = {
            'owner': session['user_id'],
            'uploader': session['user_id'],
            'upload_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_file_owners(owners)
    
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

@app.route('/delete_file/<filename>', methods=['POST'])
def delete_file(filename):
    if not can_delete_file(filename):
        return jsonify({'success': False, 'error': 'Недостаточно прав для удаления файла'})
    
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            
            # Удаляем информацию о владельце
            owners = load_file_owners()
            if filename in owners:
                del owners[filename]
                save_file_owners(owners)
            
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/save_link', methods=['POST'])
def save_link():
    link = request.form.get('link')
    if link:
        links = load_links()
        if link not in links:
            links.append(link)
            save_links(links)
            
            # Сохраняем информацию о владельце ссылки
            owners = load_link_owners()
            owners[link] = {
                'owner': session['user_id'],
                'uploader': session['user_id'],
                'upload_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_link_owners(owners)
            
    return redirect(url_for('index'))

@app.route('/delete_link', methods=['POST'])
def delete_link():
    link = request.form.get('link')
    if not link:
        return jsonify({'success': False, 'error': 'Ссылка не указана'})
    
    if not can_delete_link(link):
        return jsonify({'success': False, 'error': 'Недостаточно прав для удаления ссылки'})
    
    try:
        links = load_links()
        if link in links:
            links.remove(link)
            save_links(links)
            
            # Удаляем информацию о владельце
            owners = load_link_owners()
            if link in owners:
                del owners[link]
                save_link_owners(owners)
            
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_connected_devices')
def get_connected_devices():
    devices = load_json(DEVICES_PATH, {})
    # Очищаем устаревшие устройства (старше 5 минут)
    current_time = datetime.now()
    devices = {
        ip: device for ip, device in devices.items()
        if (current_time - datetime.strptime(device['last_seen'], "%d.%m.%Y %H:%M:%S")).total_seconds() < 300
    }
    save_json(DEVICES_PATH, devices)
    return jsonify(devices)

def update_device_info():
    if request.remote_addr != '127.0.0.1' and 'username' in session:
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        user_agent_string = request.headers.get('User-Agent', 'Unknown')
        user_agent = parse(user_agent_string)
        device_type = "Мобильное устройство" if user_agent.is_mobile else "Компьютер"
        
        devices = load_json(DEVICES_PATH, {})
        devices[request.remote_addr] = {
            'username': session['username'],
            'device_type': device_type,
            'user_agent': user_agent_string,
            'last_seen': current_time
        }
        save_json(DEVICES_PATH, devices)

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/set_username', methods=['POST'])
def set_username():
    lastname = request.form.get('lastname', '').strip()
    firstname = request.form.get('firstname', '').strip()
    patronymic = request.form.get('patronymic', '').strip()
    
    if not lastname or not firstname:
        return redirect(url_for('login'))
    
    # Формируем полное имя
    full_name = f"{lastname} {firstname}"
    if patronymic:
        full_name += f" {patronymic}"
    
    users = load_users()
    
    # Если это первый пользователь, делаем его владельцем
    if not get_owner():
        set_owner(full_name)
    
    # Сохраняем информацию о пользователе
    users[full_name] = {
        'lastname': lastname,
        'firstname': firstname,
        'patronymic': patronymic,
        'last_login': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'ip': request.remote_addr
    }
    save_users(users)
    
    session['username'] = full_name
    session['user_fullname'] = {
        'lastname': lastname,
        'firstname': firstname,
        'patronymic': patronymic
    }
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 