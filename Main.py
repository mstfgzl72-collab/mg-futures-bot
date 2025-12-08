from flask import Flask, request
import ccxt
import json
import requests

app = Flask(__name__)

# ==========================
#  AYARLAR
# ==========================
API_KEY = "z2QEQ6a3jPCdOhAjfGmn2HR4GbPpruDoVubKoZfJYtw94rw0GpVZAkL5Uvhe37RX"
API_SECRET = "2Orsd03tgpUKTZRmdmbCZBXyQS0QnN15dpXRuZErFdJKuLicrOlT3BcywaMYlcVb"

TELEGRAM_TOKEN = "8142272590:AAHIDqXDABVz01DkqGhCns7NSN8axWNfFAQ"
TELEGRAM_CHAT_ID = "7259012643"

LEVERAGE = 5          # Kaldıraç
ORDER_USDT = 10       # İşlem büyüklüğü (USDT)

# Binance Futures bağlantısı
exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})


# ==========================
#  TELEGRAM MESAJI
# ==========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass


# ==========================
#  KALDIRAÇ AYARLAMA
# ==========================
def set_leverage(symbol):
    try:
        exchange.fapiPrivate_post_leverage({
            "symbol": symbol.replace("/", ""),
            "leverage": LEVERAGE
        })
    except Exception as e:
        print("Leverage Error:", e)


# ==========================
#  USDT → ADET ÇEVİRME
# ==========================
def usdt_to_qty(symbol, usdt):
    price = exchange.fetch_ticker(symbol)["last"]
    qty = usdt / price
    return round(qty, 3)


# ==========================
#  AÇIK POZİSYON VAR MI?
# ==========================
def get_open_position(symbol):
    symbol_f = symbol.replace("/", "")
    positions = exchange.fapiPrivate_get_positionrisk()

    for pos in positions:
        if pos["symbol"] == symbol_f:
            amt = float(pos["positionAmt"])
            if amt > 0:
                return "BUY", amt
            elif amt < 0:
                return "SELL", abs(amt)
    return None, 0


# ==========================
#  POZİSYON KAPATMA
# ==========================
def close_position(symbol):
    direction, amount = get_open_position(symbol)
    if direction is None or amount == 0:
        return None  # Kapalı zaten

    close_side = "sell" if direction == "BUY" else "buy"

    order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=close_side,
        amount=amount
    )

    price = order["average"] or order["price"]
    balance = exchange.fetch_balance()["total"]["USDT"]

    send_telegram(
        f"📉 *Pozisyon Kapatıldı*\n"
        f"Parite: {symbol}\n"
        f"Kapanış Fiyatı: {price}\n"
        f"Kalan Bakiye: {balance} USDT"
    )

    return order


# ==========================
#  POZİSYON AÇMA
# ==========================
def open_position(symbol, side):
    set_leverage(symbol.replace("/", ""))

    qty = usdt_to_qty(symbol, ORDER_USDT)

    order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=side.lower(),
        amount=qty
    )

    price = order["average"] or order["price"]

    send_telegram(
        f"🚀 *Yeni Pozisyon Açıldı*\n"
        f"Parite: {symbol}\n"
        f"Yön: {side.upper()}\n"
        f"Kaldıraç: {LEVERAGE}x\n"
        f"USDT: {ORDER_USDT}\n"
        f"Adet: {qty}\n"
        f"Açılış Fiyatı: {price}"
    )

    return order


# ==========================
#  WEBHOOK – SİNYAL KONTROL
# ==========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = json.loads(request.data)

    action = data.get("action")
    symbol = data.get("symbol", "BTCUSDT").replace("USDT", "/USDT")

    current_pos, _ = get_open_position(symbol)

    # ========== 1) CLOSE işlemi ==========
    if action == "CLOSE":
        close_position(symbol)
        return {"success": True}, 200

    # ========== 2) BUY sinyali ==========
    if action == "BUY":
        if current_pos == "SELL":
            close_position(symbol)
        open_position(symbol, "buy")
        return {"success": True}, 200

    # ========== 3) SELL sinyali ==========
    if action == "SELL":
        if current_pos == "BUY":
            close_position(symbol)
        open_position(symbol, "sell")
        return {"success": True}, 200

    return {"error": "Geçersiz action"}, 400


# ==========================
#  ÇALIŞTIRMA
# ==========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
