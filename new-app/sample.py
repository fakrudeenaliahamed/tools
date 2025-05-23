import yfinance as yf
import pandas as pd

def save_nav_to_csv(symbol, period="3mo", filename=None):
    # Download data
    data = yf.download(symbol, period=period, interval="1d", progress=False)
    if data.empty:
        print(f"No data found for symbol: {symbol}")
        return

    # Use 'Adj Close' if available, else 'Close'
    price_col = "Adj Close" if "Adj Close" in data.columns else "Close"
    nav_df = data[[price_col]].rename(columns={price_col: "NAV"})
    nav_df.index = nav_df.index.date  # Use only date part

    # Set filename if not provided
    if not filename:
        filename = f"{symbol}_nav.csv"

    nav_df.to_csv(filename)
    print(f"NAV data saved to {filename}")

# Example usage
if __name__ == "__main__":
    symbol = "0P0000YWL1.BO"  # Replace with your Yahoo symbol
    save_nav_to_csv(symbol, period="3mo")