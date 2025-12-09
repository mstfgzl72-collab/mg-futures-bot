from flask import Flask, request
import ccxt
import json
import requests
import os

app = Flask(__name__)

# ==========================
#  ORTAM DEĞİŞKENLERİ (ENV)
# ==========================
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LEVERAGE = int(os.getenv("LEVERAGE", 20))
ORDER_USDT = float(os.getenv("ORDER_USDT", 20))

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
    positions = exchange.fapiPrivate_get_positionRisk()


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
        return None

    close_side = "sell" if direction == "BUY" else "buy"

    order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=close_side,
        amount=amount
    )

    balance = exchange.fetch_balance()["total"]["USDT"]
    price = order["average"] or order["price"]

    send_telegram(
        f"📉 POZİSYON KAPATILDI\n"
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
        f"🚀 YENİ POZİSYON AÇILDI\n"
        f"Parite: {symbol}\n"
        f"Yön: {side}\n"
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

    if action == "CLOSE":
        close_position(symbol)
        return {"success": True}, 200

    if action == "BUY":
        if current_pos == "SELL":
            close_position(symbol)
        open_position(symbol, "BUY")
        return {"success": True}, 200

    if action == "SELL":
        if current_pos == "BUY":
            close_position(symbol)
        open_position(symbol, "SELL")
        return {"success": True}, 200

    return {"error": "Invalid action"}, 400


# ==========================
#  ÇALIŞTIRMA
# ==========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
