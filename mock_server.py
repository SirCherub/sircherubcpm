# mock_server.py
from flask import Flask, request, jsonify

app = Flask(__name__)

# Kullanıcı bilgisi (her zaman unlimited)
FAKE_USER = {
    "is_unlimited": True,
    "coins": 999999,
    "telegram_id": "mock_telegram"
}

# Servis maliyetleri örnek (istersen değiştirebilirsin)
SERVICE_COSTS = {
    "king_rank": 10,
    "change_email": 5,
    "change_password": 5,
    "set_money": 15,
    "unlock_wheels": 3,
    "unlock_male": 3,
    "unlock_female": 3,
    "unlock_brakes": 3,
    "unlock_calipers": 3,
    "unlock_paints": 3,
    "unlock_all_flags": 3,
    "unlock_apartments": 8,
    "complete_missions": 8,
    "unlock_all_cars_siren": 4,
    "unlock_police_bodykits": 6,
    "unlock_slots": 6,
    "unlock_bodykits": 6,
    "copy_cpm1_car_to_cpm2": 12,
    "clone_cars_cpm2_to_cpm2": 12,
    "add_car": 2
}

@app.route("/KrishDev/api/menu.php", methods=["POST"])
def menu():
    menu_code = request.form.get("menu")
    token = request.form.get("token")

    # Token kontrolü: sadece "emre123" kabul ediliyor
    if token and token != "emre123":
        return jsonify({"ok": False, "message": "Invalid token"}), 403

    if menu_code == "get_user_status":
        return jsonify({"ok": True, **FAKE_USER})

    if menu_code == "get_service_costs":
        return jsonify({"ok": True, "costs": SERVICE_COSTS})

    # Diğer işlemler hep başarılı dönsün
    return jsonify({"ok": True, "message": f"Mock OK: menu={menu_code}, token={token}"})


@app.route("/KrishDev/api/save_device.php", methods=["POST"])
def save_device():
    return jsonify({"ok": True, "message": "device saved (mock)"}), 200


if __name__ == "__main__":
    print("🚀 Mock server çalışıyor: http://127.0.0.1:5000/KrishDev/api")
    app.run(host="127.0.0.1", port=5000, debug=True)
