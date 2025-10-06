# app.py
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
import yfinance as yf
import requests
from openpyxl import Workbook
from io import BytesIO

app = Flask(__name__)
DB_PATH = "portfolio.db"
APP_PASSWORD = os.environ.get("APP_PASSWORD", "1234")  # По умолчанию 1234

# Маппинг тикеров крипты → CoinGecko ID
CRYPTO_TICKER_TO_ID = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'DOGE': 'dogecoin',
    'XRP': 'ripple',
    'ADA': 'cardano',
    'DOT': 'polkadot',
    'LINK': 'chainlink',
    'AVAX': 'avalanche',
    'MATIC': 'polygon',
    'SHIB': 'shiba-inu',
    'LTC': 'litecoin',
    'BCH': 'bitcoin-cash',
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            asset_type TEXT NOT NULL CHECK(asset_type IN ('stock', 'crypto')),
            operation TEXT NOT NULL CHECK(operation IN ('buy', 'sell')),
            amount REAL NOT NULL,
            price_at_operation REAL,
            date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_price(symbol, asset_type):
    try:
        if asset_type == "stock":
            ticker = yf.Ticker(symbol.upper())
            hist = ticker.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
        elif asset_type == "crypto":
            # Преобразуем тикер в ID
            coingecko_id = CRYPTO_TICKER_TO_ID.get(symbol.upper())
            if not coingecko_id:
                return None
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=usd"
            response = requests.get(url, timeout=5)
            data = response.json()
            return data.get(coingecko_id, {}).get("usd")
    except Exception as e:
        print(f"Ошибка цены {symbol}: {e}")
    return None

def get_all_transactions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions ORDER BY date DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def calculate_portfolio():
    """Возвращает текущий портфель (только купленные, не проданные)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT symbol, asset_type, SUM(
            CASE WHEN operation = 'buy' THEN amount
                 WHEN operation = 'sell' THEN -amount
            END
        ) as net_amount
        FROM transactions
        GROUP BY symbol, asset_type
        HAVING net_amount > 0
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password")
        if pwd == APP_PASSWORD:
            resp = redirect(url_for("index"))
            resp.set_cookie("auth", "1")
            return resp
        else:
            return render_template("login.html", error="Неверный пароль")
    return render_template("login.html")

def is_authenticated():
    return request.cookies.get("auth") == "1"

@app.route("/logout")
def logout():
    resp = redirect(url_for("login"))
    resp.set_cookie("auth", "", expires=0)
    return resp

@app.route("/", methods=["GET", "POST"])
def index():
    if not is_authenticated():
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")
        symbol = request.form.get("symbol", "").strip().upper()
        asset_type = request.form.get("type", "")
        amount_str = request.form.get("amount", "").strip()

        if not symbol or not asset_type or not amount_str:
            return redirect(url_for("index"))

        try:
            amount = float(amount_str)
            if amount <= 0:
                return redirect(url_for("index"))
        except ValueError:
            return redirect(url_for("index"))

        # Получаем текущую цену
        price = get_price(symbol, asset_type)
        if price is None:
            return redirect(url_for("index"))

        date_now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (symbol, asset_type, operation, amount, price_at_operation, date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, asset_type, action, amount, price, date_now))
        conn.commit()
        conn.close()

        return redirect(url_for("index"))

    # Расчёт текущего портфеля и общей стоимости
    portfolio_rows = calculate_portfolio()
    total_value = 0
    enriched_portfolio = []

    for symbol, asset_type, net_amount in portfolio_rows:
        price = get_price(symbol, asset_type)
        value = price * net_amount if price else 0
        total_value += value
        enriched_portfolio.append({
            "symbol": symbol,
            "type": asset_type,
            "amount": round(net_amount, 6),
            "price": round(price, 4) if price else None,
            "value": round(value, 2)
        })

    transactions = get_all_transactions()
    return render_template(
        "index.html",
        portfolio=enriched_portfolio,
        total_value=round(total_value, 2),
        transactions=transactions,
        crypto_tickers=list(CRYPTO_TICKER_TO_ID.keys())
    )

@app.route("/export")
def export_excel():
    if not is_authenticated():
        return "Access denied", 403

    wb = Workbook()
    ws = wb.active
    ws.title = "Операции"

    # Заголовки
    ws.append(["ID", "Тикер", "Тип", "Операция", "Количество", "Цена", "Дата"])

    for t in get_all_transactions():
        ws.append([
            t["id"],
            t["symbol"],
            t["asset_type"],
            t["operation"],
            t["amount"],
            t["price_at_operation"],
            t["date"]
        ])

    # Сохраняем в памяти
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="portfolio.xlsx"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
