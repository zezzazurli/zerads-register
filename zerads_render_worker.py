# zerads_render_worker.py
# Worker per Render: registra account su Zerads 24/7

import requests
import re
import time
import cv2
import numpy as np
import easyocr
import random
import string
import json
import os
from datetime import datetime

# ============================================================
# CONFIGURAZIONE
# ============================================================

BASE_URL = "https://zerads.com"

# File
ACCOUNTS_FILE = "accounts_zerads.json"
REF_FILE = "ref_list.txt"

# Pausa tra account
PAUSA_MIN = 30
PAUSA_MAX = 60

MAX_TENTATIVI = 5

# ============================================================
# CARICA EASYOCR
# ============================================================

print("⏳ Caricamento EasyOCR...")
reader = easyocr.Reader(['en'], gpu=False)
print("✅ EasyOCR pronto")

# ============================================================
# FUNZIONI
# ============================================================

def carica_ref():
    if os.path.exists(REF_FILE):
        try:
            with open(REF_FILE, "r") as f:
                return [line.strip() for line in f if line.strip()]
        except:
            return []
    return []

def salva_ref(refs):
    with open(REF_FILE, "w") as f:
        for r in refs:
            f.write(f"{r}\n")

def carica_account():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def salva_account(accounts):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=2)

def genera_username():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def genera_password():
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(random.choices(chars, k=12))

def genera_email(username):
    domini = ["libero.it", "virgilio.it", "tiscali.it", "alice.it", "tin.it",
              "katamail.com", "supereva.it", "email.it", "fastmail.net",
              "zoho.com", "gmx.com", "yandex.com", "proton.me", "tuta.io"]
    return f"{username}@{random.choice(domini)}"

def pausa_casuale(min_sec=PAUSA_MIN, max_sec=PAUSA_MAX):
    time.sleep(random.uniform(min_sec, max_sec))

def risolvi_captcha(img_bytes):
    try:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return None
        
        img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        if np.mean(thresh) > 127:
            thresh = cv2.bitwise_not(thresh)
        
        thresh = cv2.medianBlur(thresh, 3)
        
        results = reader.readtext(thresh, allowlist='0123456789')
        
        testi = []
        for bbox, text, conf in results:
            if conf > 0.1:
                testi.append(text)
        
        testo = ''.join(testi)
        cifre = ''.join(filter(str.isdigit, testo))
        
        if len(cifre) > 4:
            for lunghezza in [4, 3, 5]:
                if len(cifre) >= lunghezza:
                    primo_gruppo = cifre[:lunghezza]
                    if cifre.startswith(primo_gruppo * (len(cifre) // lunghezza)):
                        cifre = primo_gruppo
                        break
            if len(cifre) > 4:
                cifre = cifre[:4]
        
        if len(cifre) >= 3:
            return cifre
        return None
        
    except Exception:
        return None

def registra_account(ref_username, max_tentativi=MAX_TENTATIVI):
    username = genera_username()
    password = genera_password()
    email = genera_email(username)
    
    for tentativo in range(max_tentativi):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive'
        })
        
        try:
            url = f"{BASE_URL}/index.php?view=join&ref={ref_username}"
            r1 = session.get(url, timeout=30)
            
            if r1.status_code != 200:
                continue
            
            match = re.search(r"name=['\"]rid['\"]\s+value=['\"](\d+)['\"]", r1.text)
            if not match:
                match = re.search(r"router\.php\?rid=(\d+)", r1.text)
            
            if not match:
                continue
            
            rid = match.group(1)
            
            pausa_casuale(2, 4)
            captcha_url = f"{BASE_URL}/router.php?rid={rid}"
            r2 = session.get(captcha_url, timeout=30)
            
            if r2.status_code != 200:
                continue
            
            codice = risolvi_captcha(r2.content)
            
            if not codice:
                continue
            
            pausa_casuale(2, 4)
            
            data = {
                'ref': ref_username,
                'uUsername': username,
                'uPassword': password,
                'uVPassword': password,
                'uEmail': email,
                'rid': rid,
                'routing_code': codice
            }
            
            r3 = session.post(
                f"{BASE_URL}/index.php?view=join&action=join&",
                data=data,
                timeout=30,
                allow_redirects=False
            )
            
            if r3.status_code == 302:
                location = r3.headers.get('Location', '')
                if "login" in location or "uname=" in location:
                    print(f"✅ {username}")
                    return {
                        'username': username,
                        'password': password,
                        'email': email,
                        'ref': ref_username,
                        'registrato_il': datetime.now().isoformat()
                    }
            
            if "Join Error" in r3.text:
                pausa_casuale(3, 6)
                continue
                
        except Exception:
            pausa_casuale(5, 10)
            continue
    
    return None

# ============================================================
# WORKER (loop infinito)
# ============================================================

def worker():
    print("=" * 60)
    print("🚀 ZERADS RENDER WORKER")
    print("=" * 60)
    
    accounts = carica_account()
    refs = carica_ref()
    
    print(f"📊 Account esistenti: {len(accounts)}")
    print(f"🔗 Ref disponibili: {len(refs)}")
    print("=" * 60)
    
    successi = 0
    fallimenti = 0
    
    while True:
        try:
            if not refs:
                print("❌ Nessun ref disponibile. Attendo...")
                time.sleep(300)
                refs = carica_ref()
                continue
            
            ref_scelto = random.choice(refs)
            
            print(f"\n📌 Account {successi + 1} (ref: {ref_scelto})")
            
            account = registra_account(ref_scelto)
            
            if account:
                accounts.append(account)
                refs.append(account['username'])
                successi += 1
                
                salva_account(accounts)
                salva_ref(refs)
                
                print(f"   ✅ Account {successi}: {account['email']}")
                print(f"   📊 Ref totali: {len(refs)}")
            else:
                fallimenti += 1
                print(f"   ❌ Fallito ({fallimenti} totali)")
            
            pausa_casuale(PAUSA_MIN, PAUSA_MAX)
            
        except Exception as e:
            print(f"❌ Errore: {e}")
            time.sleep(60)

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    worker()