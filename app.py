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
SETTINGS_PATH = os.path.join('Base', 'settings.json')

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
    
    # Владелец системы может удалять любые файлы
    if is_owner():
        return True
    
    owners = load_file_owners()
    if filename not in owners:
        return False
    
    return owners[filename]['owner'] == session['user_id'] or owners[filename]['uploader'] == session['user_id']

def can_delete_link(link):
    if 'user_id' not in session:
        return False
    
    # Владелец системы может удалять любые ссылки
    if is_owner():
        return True
    
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

def format_name_with_initials(lastname, firstname, patronymic=None):
    """Форматирует ФИО в формат: Фамилия И.О."""
    if not lastname or not firstname:
        return "Неизвестно"
    
    initials = f"{firstname[0]}." if firstname else ""
    if patronymic and len(patronymic) > 0:
        initials += f"{patronymic[0]}."
    return f"{lastname} {initials}"

def get_extended_device_info(ip):
    """Получает расширенную информацию об устройстве"""
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except:
        hostname = "Неизвестно"
    
    try:
        fqdn = socket.getfqdn(ip)
    except:
        fqdn = "Неизвестно"
    
    return {
        "hostname": hostname,
        "fqdn": fqdn,
        "ip": ip
    }

@app.route('/get_device_info/<ip>')
def get_device_info(ip):
    devices = load_json(DEVICES_PATH, {})
    if ip in devices:
        device_info = devices[ip].copy()
        extended_info = get_extended_device_info(ip)
        device_info.update(extended_info)
        
        # Форматируем имя пользователя
        if 'username' in device_info:
            user_data = load_users().get(device_info['username'], {})
            if user_data:
                device_info['formatted_name'] = format_name_with_initials(
                    user_data.get('lastname', ''),
                    user_data.get('firstname', ''),
                    user_data.get('patronymic', '')
                )
        
        return jsonify(device_info)
    return jsonify({'error': 'Устройство не найдено'})

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
    users = load_users()
    
    # Форматируем информацию о файлах и их владельцах
    files_info = {}
    for file in files:
        owner_info = file_owners.get(file, {})
        owner_id = owner_info.get('uploader')
        formatted_name = "Неизвестно"
        
        # Ищем пользователя по ID
        for username, user_data in users.items():
            if owner_id and owner_id == session.get('user_id'):
                formatted_name = format_name_with_initials(
                    user_data.get('lastname', ''),
                    user_data.get('firstname', ''),
                    user_data.get('patronymic', '')
                )
                break
        
        files_info[file] = {
            'name': file,
            'uploader': formatted_name,
            'upload_time': owner_info.get('upload_time', 'Неизвестно'),
            'can_delete': can_delete_file(file)
        }
    
    # Форматируем информацию о ссылках и их владельцах
    links_info = {}
    for link in links:
        owner_info = link_owners.get(link, {})
        owner_id = owner_info.get('uploader')
        formatted_name = "Неизвестно"
        
        # Ищем пользователя по ID
        for username, user_data in users.items():
            if owner_id and owner_id == session.get('user_id'):
                formatted_name = format_name_with_initials(
                    user_data.get('lastname', ''),
                    user_data.get('firstname', ''),
                    user_data.get('patronymic', '')
                )
                break
        
        links_info[link] = {
            'url': link,
            'uploader': formatted_name,
            'upload_time': owner_info.get('upload_time', 'Неизвестно'),
            'can_delete': can_delete_link(link)
        }
    
    # Форматируем имя текущего пользователя
    user_data = users.get(username, {})
    formatted_username = format_name_with_initials(
        user_data.get('lastname', ''),
        user_data.get('firstname', ''),
        user_data.get('patronymic', '')
    )
    
    # Форматируем информацию об устройствах
    formatted_devices = {}
    for ip, device in devices.items():
        device_info = device.copy()
        if 'username' in device_info:
            user_data = users.get(device_info['username'], {})
            device_info['formatted_name'] = format_name_with_initials(
                user_data.get('lastname', ''),
                user_data.get('firstname', ''),
                user_data.get('patronymic', '')
            )
        formatted_devices[ip] = device_info
    
    return render_template('index.html',
                         username=formatted_username,
                         is_owner=is_owner,
                         files=files_info,
                         links=links_info,
                         local_ip=get_local_ip(),
                         connected_devices=formatted_devices)

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
    if not link:
        return jsonify({'success': False, 'error': 'Ссылка не указана'})
    
    try:
        links = load_links()
        if link not in links:
            links.append(link)
            save_links(links)
            
            # Сохраняем информацию о владельце ссылки
            owners = load_link_owners()
            owners[link] = {
                'owner': session.get('user_id'),
                'uploader': session.get('user_id'),
                'upload_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_link_owners(owners)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Эта ссылка уже сохранена'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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

def load_settings():
    return load_json(SETTINGS_PATH, {
        'password': None,
        'secret_key': None,
        'max_file_size': 16,
        'file_size_unit': 'MB'
    })

def save_settings(settings):
    save_json(SETTINGS_PATH, settings)

@app.route('/save_settings', methods=['POST'])
def save_repository_settings():
    if not is_owner():
        return jsonify({'success': False, 'error': 'Недостаточно прав'})
    
    try:
        data = request.get_json()
        max_file_size = int(data.get('max_file_size', 16))
        file_size_unit = data.get('file_size_unit', 'MB')

        # Проверка значений
        if max_file_size < 1:
            return jsonify({'success': False, 'error': 'Размер файла должен быть больше 0'})

        # Проверяем максимальные значения для разных единиц
        max_limits = {
            'KB': 1024 * 1024,  # 1 ГБ в КБ
            'MB': 1024,         # 1 ГБ в МБ
            'GB': 1             # 1 ГБ
        }

        if max_file_size > max_limits.get(file_size_unit, 16):
            return jsonify({'success': False, 'error': f'Максимальный размер для {file_size_unit}: {max_limits[file_size_unit]}'})

        # Конвертируем в байты для сохранения
        size_multipliers = {
            'KB': 1024,
            'MB': 1024 * 1024,
            'GB': 1024 * 1024 * 1024
        }
        size_in_bytes = max_file_size * size_multipliers.get(file_size_unit, 1024 * 1024)

        settings = {
            'password': data.get('password'),
            'secret_key': data.get('secret_key'),
            'max_file_size': max_file_size,
            'file_size_unit': file_size_unit
        }
        
        # Сохраняем настройки
        save_settings(settings)
        
        # Обновляем конфигурацию приложения
        app.config['MAX_CONTENT_LENGTH'] = size_in_bytes
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 