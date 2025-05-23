# app.py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, jsonify
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import io
import base64

app = Flask(__name__)


def compare_mutual_funds(fund1_symbol, fund2_symbol, duration="3mo"):
    try:
        # Fetch data using the duration parameter directly
        fund1 = yf.download(fund1_symbol, period=duration, progress=False)
        fund2 = yf.download(fund2_symbol, period=duration, progress=False)

        error_symbols = []
        if fund1.empty:
            error_symbols.append(fund1_symbol)
        if fund2.empty:
            error_symbols.append(fund2_symbol)
        if error_symbols:
            raise ValueError(f"Unable to fetch data for: {', '.join(error_symbols)}")
        if fund1.empty or fund2.empty:
            raise ValueError("Unable to fetch data for one or both fund symbols")

        # Handle column structure
        if hasattr(fund1.columns, "levels") and len(fund1.columns.levels) > 1:
            fund1.columns = [
                col[0] if isinstance(col, tuple) else col for col in fund1.columns
            ]
        if hasattr(fund2.columns, "levels") and len(fund2.columns.levels) > 1:
            fund2.columns = [
                col[0] if isinstance(col, tuple) else col for col in fund2.columns
            ]

        # Get prices
        price_columns = ["Close"]
        fund1_prices = None
        fund2_prices = None

        for col in price_columns:
            if col in fund1.columns:
                fund1_prices = fund1[col]
                break
        for col in price_columns:
            if col in fund2.columns:
                fund2_prices = fund2[col]
                break

        # Calculate performance
        fund1_normalized = ((fund1_prices / fund1_prices.iloc[0]) - 1) * 100
        fund2_normalized = ((fund2_prices / fund2_prices.iloc[0]) - 1) * 100

        # Generate chart
        plt.figure(figsize=(12, 8))
        plt.plot(
            fund1_normalized.index,
            fund1_normalized.values,
            linewidth=3,
            label=fund1_symbol,
            color="#2E86AB",
        )
        plt.plot(
            fund2_normalized.index,
            fund2_normalized.values,
            linewidth=3,
            label=fund2_symbol,
            color="#A23B72",
        )

        plt.title(
            f"Fund Performance Comparison ({duration.upper()})", fontsize=16, pad=20
        )
        plt.xlabel("Date", fontsize=12)
        plt.ylabel("Performance (%)", fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Convert to base64
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format="png", dpi=300, bbox_inches="tight")
        img_buffer.seek(0)
        chart_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        plt.close()

        return {
            "fund1_symbol": fund1_symbol,
            "fund2_symbol": fund2_symbol,
            "fund1_return": fund1_normalized.iloc[-1],
            "fund2_return": fund2_normalized.iloc[-1],
            "winner": (
                fund1_symbol
                if fund1_normalized.iloc[-1] > fund2_normalized.iloc[-1]
                else fund2_symbol
            ),
            "chart_data": f"data:image/png;base64,{chart_base64}",
        }

    except Exception as e:
        return {"error": str(e)}


@app.route("/")
def index():
    return render_template("index.html")  # Your HTML file


@app.route("/compare", methods=["POST"])
def compare():
    data = request.json
    result = compare_mutual_funds(data["fund1"], data["fund2"], data["duration"])
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5003)
