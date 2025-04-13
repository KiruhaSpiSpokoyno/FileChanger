from flask import Flask, request, render_template, send_file, redirect, url_for, jsonify
import os
from werkzeug.utils import secure_filename
import socket
import time
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp3', 'mp4', 'zip'}

# Словарь для хранения информации о подключенных устройствах
connected_devices = {}

def get_local_ip():
    try:
        # Получаем имя хоста
        hostname = socket.gethostname()
        # Получаем IP-адрес
        ip_address = socket.gethostbyname(hostname)
        return ip_address
    except:
        return "localhost"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def track_visitor():
    if request.remote_addr != '127.0.0.1':  # Исключаем локальные запросы
        current_time = datetime.now().strftime("%H:%M:%S")
        user_agent = request.headers.get('User-Agent', 'Unknown')
        device_type = 'Мобильное устройство' if 'Mobile' in user_agent else 'Компьютер'
        connected_devices[request.remote_addr] = {
            'last_seen': current_time,
            'device_type': device_type,
            'user_agent': user_agent
        }

# Создаем папку для загрузок, если она не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    local_ip = get_local_ip()
    # Очищаем список устройств от тех, кто не был активен более 5 минут
    current_time = time.time()
    return render_template('index.html', 
                         files=files, 
                         local_ip=local_ip, 
                         connected_devices=connected_devices)

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
    
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename))

@app.route('/save_link', methods=['POST'])
def save_link():
    link = request.form.get('link')
    if link:
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'links.txt'), 'a', encoding='utf-8') as f:
            f.write(link + '\n')
    return redirect(url_for('index'))

@app.route('/get_connected_devices')
def get_connected_devices():
    return jsonify(connected_devices)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 