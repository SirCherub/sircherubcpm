#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import platform
import subprocess
from itertools import cycle
from threading import Thread, Event

# ---- Google Sheets ----
import gspread
from google.oauth2.service_account import Credentials

# =========================
#  AYARLAR / ORTAM DEĞİŞKENLERİ
# =========================
# SHEET_ID: export SHEET_ID="1A3pD1gOKa7Lgkiu8yy1LtYCUwwGqFep97VsND-33XO8"
SHEET_ID = os.getenv("SHEET_ID", "").strip()
USERS_SHEET_NAME = "users"
COSTS_SHEET_NAME = "costs"

# Artık dış API yok. BASE_URL sadece kalıntı kodları bozmasın diye dummy.
BASE_URL = os.getenv("BASE_URL", "http://localhost/mockapi")

# =========================
#  UI / YARDIMCI
# =========================
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def spinner_animation(stop_event):
    spinner = cycle(['|', '/', '-', '\\'])
    while not stop_event.is_set():
        sys.stdout.write(f'\r[-] Yükleniyor... {next(spinner)} ')
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r')
    sys.stdout.flush()

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
            print(f"           Subscription: UNLIMITED ✅")
        else:
            print(f"           Subscription: LIMITED ❌")
            if current_coins is not None:
                print(f"           Balance: {current_coins} coins")

# =========================
#  GOOGLE SHEETS ERİŞİMİ
# =========================
def _open_sheet():
    """
    credentials.json dosyan bu klasörde olmalı.
    Sheet’i servis hesabının e-postasıyla en az Viewer olarak paylaş.
    """
    if not SHEET_ID:
        raise RuntimeError("SHEET_ID çevre değişkeni set edilmemiş (export SHEET_ID=\"...\").")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def load_users_from_sheet():
    """
    users sayfası şeması:
    access_key | email | token | unlimited | coins | telegram_id
    unlimited -> TRUE/FALSE / 1/0 / yes/no kabul edilir
    coins -> integer
    """
    sh = _open_sheet()
    ws = sh.worksheet(USERS_SHEET_NAME)
    rows = ws.get_all_records()
    users = {}
    for r in rows:
        key = str(r.get("access_key", "")).strip()
        if not key:
            continue
        unlimited_raw = str(r.get("unlimited", "")).strip().lower()
        unlimited = unlimited_raw in ("1", "true", "yes", "y", "evet")
        coins = r.get("coins", 0)
        try:
            coins = int(coins)
        except Exception:
            coins = 0
        users[key] = {
            "email": str(r.get("email", "")).strip(),
            "token": str(r.get("token", "")).strip(),
            "is_unlimited": unlimited,
            "coins": coins,
            "telegram_id": str(r.get("telegram_id", "")).strip() or "N/A",
        }
    return users

def load_costs_from_sheet():
    """
    costs sayfası şeması (key, value):
    king_rank | 100
    change_email | 30
    ...
    """
    sh = _open_sheet()
    ws = sh.worksheet(COSTS_SHEET_NAME)
    rows = ws.get_all_records()
    costs = {}
    for r in rows:
        k = str(r.get("key", "")).strip()
        v = r.get("value", "")
        if not k:
            continue
        try:
            v = int(v)
        except Exception:
            # metin/boş ise olduğu gibi bırak
            pass
        costs[k] = v
    return costs

# =========================
#  MOCK’LANAN (ARTIK KULLANMAYAN) DIŞ ÇAĞRILAR
# =========================
def call_php_service(*args, **kwargs):
    # Dış HTTP artıktan yok. Her zaman başarılı gibi dönelim.
    return {"ok": True, "message": "Sheets modunda işlem başarılı (mock)."}

def call_php_service_with_spinner(*args, **kwargs):
    stop_spinner = Event()
    t = Thread(target=spinner_animation, args=(stop_spinner,))
    t.daemon = True
    t.start()
    time.sleep(0.6)  # küçük bekleme
    stop_spinner.set()
    t.join()
    return {"ok": True, "message": "Sheets modunda işlem başarılı (mock)."}

def send_device_os(*args, **kwargs):
    # Eski sistem logluyordu. Artık no-op.
    return True

# =========================
#  UYGULAMA AKIŞI (GOOGLE SHEETS İLE)
# =========================
def main():
    # İnternet testi (Sheets'e erişim için)
    try:
        import requests
        requests.get("https://www.google.com", timeout=3)
    except Exception:
        print("❌ İnternet yok. Lütfen bağlantıyı kontrol et.")
        sys.exit(1)

    # Başlangıç: costs’ları yükle (Sheets’ten)
    try:
        service_costs = load_costs_from_sheet()
    except Exception as e:
        print(f"⚠️ Uyarı: Sheets’ten service costs alınamadı: {e}")
        service_costs = {}

    unlimited_status_for_display = None
    current_coins_for_display = None
    is_unlimited_user = False
    telegram_id_for_display = "N/A"

    email = ""
    token = None
    label_to_use = "N/A"
    main_menu = None

    while True:
        clear_screen()
        show_banner(unlimited_status=unlimited_status_for_display,
                    current_coins=current_coins_for_display,
                    telegram_id=telegram_id_for_display)

        access_key = input("🔑 Access key gir: ").strip()

        # Sheets’ten kullanıcıları oku ve access_key doğrula
        try:
            users = load_users_from_sheet()
        except Exception as e:
            print(f"❌ Sheets hatası: {e}")
            time.sleep(1)
            continue

        if access_key not in users:
            print("❌ Geçersiz access key veya Sheets’te bulunamadı.")
            unlimited_status_for_display = None
            current_coins_for_display = None
            is_unlimited_user = False
            telegram_id_for_display = "N/A"
            time.sleep(0.6)
            continue

        user = users[access_key]
        is_unlimited_user = user["is_unlimited"]
        current_coins_for_display = user["coins"]
        telegram_id_for_display = user["telegram_id"]
        email = user["email"]
        token = user["token"]

        print("✅ Key kabul edildi.")
        print(f"Telegram ID: {telegram_id_for_display or 'N/A'}")
        try:
            os.system("termux-open-url 'https://t.me/bonkscpmtermuxchannel'")
            print("Telegram grubunu açıyorum...")
            time.sleep(0.5)
        except Exception as e:
            print(f"Telegram URL açılamadı: {e}")

        if not is_unlimited_user:
            print("\nAboneliğin LIMITED. Menüye girebilirsin ama servisler coin düşürür.")
        else:
            print("UNLIMITED aboneliktesin. Servisler ücretsiz.")
        time.sleep(0.6)

        # Oyun seçimi
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
                # CPM1 login (Sheets modunda token zaten var)
                label_to_use = "CPM1"
            elif main_menu == "2":
                label_to_use = "CPM2"
            else:
                print("❌ Geçersiz seçim. 0, 1 veya 2 gir.")
                time.sleep(0.5)
                continue

            print(f"\n--- {label_to_use} ---")
            # Sheets modunda email/password almıyoruz; token zaten user satırında mevcut.
            print(f"✅ Hesap: {email or 'N/A'} (token: {'var' if token else 'yok'})")
            time.sleep(0.5)

            # Cihaz bilgisi logu (mock)
            send_device_os(access_key, email, "********", label_to_use, telegram_id_for_display)
            time.sleep(0.5)

            while True:
                clear_screen()
                show_banner(unlimited_status=is_unlimited_user,
                            current_coins=current_coins_for_display,
                            telegram_id=telegram_id_for_display)
                print(f"Hesap: {email or 'N/A'} ({label_to_use})")
                # CPM1 ortak menü
                print(f"01. 👑 KING RANK (Cost: {service_costs.get('king_rank', 'N/A')} coins)")
                print(f"02. 📧 CHANGE EMAIL (Cost: {service_costs.get('change_email', 'N/A')} coins)")
                print(f"03. 🔐 CHANGE PASSWORD (Cost: {service_costs.get('change_password', 'N/A')} coins)")

                if main_menu == "2":
                    # CPM2 ek menüler
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
                    print(f"20. ➕ ADD CAR (Cost: {service_costs.get('add_car', 'N/A')} coins)")
                print("0.  🔙 GERİ")
                choice = input("Seçim: ").strip()

                if choice == "0":
                    break

                # Her servis mock
                def _ok(msg="İşlem başarılı."):
                    return {"ok": True, "message": msg}

                action_result = {"ok": False, "message": "Geçersiz seçim."}
                if main_menu == "1":
                    if choice == "1":
                        action_result = _ok("KING RANK uygulandı (mock).")
                    elif choice == "2":
                        new_email = input("📨 Yeni Email: ").strip()
                        email = new_email or email
                        action_result = _ok("E-posta güncellendi (mock).")
                    elif choice == "3":
                        _ = input("🔑 Yeni Şifre: ").strip()
                        action_result = _ok("Şifre güncellendi (mock).")
                elif main_menu == "2":
                    if choice == "1":
                        action_result = _ok("KING RANK (CPM2) uygulandı (mock).")
                    elif choice == "2":
                        new_email = input("📨 Yeni Email: ").strip()
                        email = new_email or email
                        action_result = _ok("E-posta güncellendi (mock).")
                    elif choice == "3":
                        _ = input("🔑 Yeni Şifre: ").strip()
                        action_result = _ok("Şifre güncellendi (mock).")
                    elif choice == "4":
                        amount = input("💵 Amount: ").strip()
                        action_result = _ok(f"Para {amount} olarak set edildi (mock).")
                    elif choice == "5":
                        action_result = _ok("Wheels açıldı (mock).")
                    elif choice == "6":
                        action_result = _ok("Male açıldı (mock).")
                    elif choice == "7":
                        action_result = _ok("Female açıldı (mock).")
                    elif choice == "8":
                        action_result = _ok("Brakes açıldı (mock).")
                    elif choice == "9":
                        action_result = _ok("Calipers açıldı (mock).")
                    elif choice == "10":
                        action_result = _ok("Paints açıldı (mock).")
                    elif choice == "11":
                        action_result = _ok("Tüm bayraklar açıldı (mock).")
                    elif choice == "12":
                        action_result = _ok("Apartmanlar açıldı (mock).")
                    elif choice == "13":
                        action_result = _ok("Missions %100 (mock).")
                    elif choice == "14":
                        action_result = _ok("Siren & Airsus açıldı (mock).")
                    elif choice == "15":
                        action_result = _ok("Police bodykits açıldı (mock).")
                    elif choice == "16":
                        action_result = _ok("Slots açıldı (mock).")
                    elif choice == "17":
                        action_result = _ok("Bodykits açıldı (mock).")
                    elif choice == "18":
                        _ = input("📧 CPM1 Email: ").strip()
                        _ = input("🔐 CPM1 Password: ").strip()
                        action_result = _ok("CPM1 -> CPM2 kopyalama yapıldı (mock).")
                    elif choice == "19":
                        _ = input("📧 Hedef CPM2 Email: ").strip()
                        _ = input("🔐 Hedef CPM2 Password: ").strip()
                        action_result = _ok("CPM2 -> CPM2 klonlama yapıldı (mock).")
                    elif choice == "20":
                        car_id = input("🚗 Car ID: ").strip()
                        copies = input("🔢 Kaç kopya (1-20): ").strip()
                        action_result = _ok(f"Car {car_id} x{copies} eklendi (mock).")

                if action_result.get("ok"):
                    print(f"✅ {action_result.get('message', 'Başarılı')}")
                else:
                    print(f"❌ {action_result.get('message', 'Başarısız')}")
                time.sleep(0.9)

                # (Opsiyonel) Sheets’ten güncel değerleri tekrar çek
                try:
                    users = load_users_from_sheet()
                    if access_key in users:
                        user = users[access_key]
                        is_unlimited_user = user["is_unlimited"]
                        current_coins_for_display = user["coins"]
                        telegram_id_for_display = user["telegram_id"]
                except Exception:
                    pass

if __name__ == "__main__":
    main()
