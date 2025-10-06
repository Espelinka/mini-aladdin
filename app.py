# app.py
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
import yfinance as yf
import requests

app = Flask(__name__)
DB_PATH = "portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            asset_type TEXT NOT NULL CHECK(asset_type IN ('stock', 'crypto')),
            amount REAL NOT NULL,
            buy_date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Инициализируем БД при запуске
init_db()

def get_price(symbol, asset_type):
    try:
        if asset_type == "stock":
            ticker = yf.Ticker(symbol.upper())
            hist = ticker.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
        elif asset_type == "crypto":
            # symbol должен быть ID из CoinGecko: bitcoin, ethereum и т.д.
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd"
            response = requests.get(url, timeout=5)
            data = response.json()
            return data.get(symbol, {}).get("usd")
    except Exception as e:
        print(f"Ошибка цены {symbol}: {e}")
    return None

def get_all_assets():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets ORDER BY buy_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            symbol = request.form.get("symbol", "").strip().lower()
            asset_type = request.form.get("type", "")
            amount_str = request.form.get("amount", "").strip()

            if symbol and asset_type and amount_str:
                try:
                    amount = float(amount_str)
                    if amount > 0:
                        buy_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO assets (symbol, asset_type, amount, buy_date) VALUES (?, ?, ?, ?)",
                            (symbol, asset_type, amount, buy_date)
                        )
                        conn.commit()
                        conn.close()
                except ValueError:
                    pass
        elif action == "remove":
            try:
                asset_id = int(request.form.get("id"))
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
                conn.commit()
                conn.close()
            except (ValueError, TypeError):
                pass
        return redirect(url_for("index"))

    assets = get_all_assets()
    total_value = 0
    enriched = []

    for asset in assets:
        price = get_price(asset["symbol"], asset["asset_type"])
        value = price * asset["amount"] if price else 0
        total_value += value
        enriched.append({
            "id": asset["id"],
            "symbol": asset["symbol"],
            "type": asset["asset_type"],
            "amount": asset["amount"],
            "buy_date": asset["buy_date"],
            "price": round(price, 4) if price else None,
            "value": round(value, 2)
        })

    return render_template("index.html", portfolio=enriched, total_value=round(total_value, 2))

@app.route("/chart/<asset_type>/<symbol>")
def chart_data(asset_type, symbol):
    try:
        if asset_type == "stock":
            ticker = yf.Ticker(symbol.upper())
            hist = ticker.history(period="30d")
            if hist.empty:
                return jsonify({"error": "No data"})
            data = [
                {"date": str(date.date()), "price": round(row['Close'], 2)}
                for date, row in hist.iterrows()
            ]
        elif asset_type == "crypto":
            # Получаем данные за 30 дней из CoinGecko
            url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
            params = {"vs_currency": "usd", "days": "30", "interval": "daily"}
            response = requests.get(url, params=params, timeout=5)
            result = response.json()
            prices = result.get("prices", [])
            data = [
                {"date": datetime.utcfromtimestamp(p[0]/1000).strftime("%Y-%m-%d"), "price": round(p[1], 2)}
                for p in prices
            ]
        else:
            return jsonify({"error": "Invalid type"})
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
