import json
import os
from flask import Flask, render_template, request, redirect, url_for
import yfinance as yf
import requests

app = Flask(__name__)
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)

def get_price(symbol, asset_type):
    try:
        if asset_type == "stock":
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
        elif asset_type == "crypto":
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd"
            response = requests.get(url)
            data = response.json()
            return data.get(symbol, {}).get("usd", None)
    except Exception as e:
        print(f"Ошибка при загрузке {symbol}: {e}")
    return None

@app.route("/", methods=["GET", "POST"])
def index():
    portfolio = load_portfolio()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            symbol = request.form.get("symbol").strip().lower()
            asset_type = request.form.get("type")
            amount = float(request.form.get("amount", 0))
            if symbol and amount > 0:
                portfolio.append({
                    "symbol": symbol,
                    "type": asset_type,
                    "amount": amount
                })
                save_portfolio(portfolio)
        elif action == "remove":
            index_to_remove = int(request.form.get("index"))
            if 0 <= index_to_remove < len(portfolio):
                portfolio.pop(index_to_remove)
                save_portfolio(portfolio)
        return redirect(url_for("index"))

    total_value = 0
    enriched_portfolio = []
    for item in portfolio:
        price = get_price(item["symbol"], item["type"])
        value = price * item["amount"] if price else 0
        total_value += value
        enriched_portfolio.append({
            "symbol": item["symbol"],
            "type": item["type"],
            "amount": item["amount"],
            "price": round(price, 4) if price else None,
            "value": round(value, 2)
        })

    return render_template("index.html", portfolio=enriched_portfolio, total_value=round(total_value, 2))

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
