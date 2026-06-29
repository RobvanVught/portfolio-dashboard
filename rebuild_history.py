import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import os

INPUT_FILE = "Transactions.xlsx"
OUTPUT_FILE = "historical_portfolio.csv"
GRAPH_FILE = "portfolio_value.png"

# === 1. Ticker mapping ===
TICKER_MAP = {
    "PACCAR INC": "PCAR",
    "ALPHABET INC CLASS A": "GOOGL",
    "TYLER TECHNOLOGIES INC": "TYL",
    "PALO ALTO NETWORKS INC": "PANW",
    "NEWMONT CORPORATION": "NEM",

    "ASR NEDERLAND NV": "ASRNL.AS",
    "ING GROEP NV": "INGA.AS",
    "ASML HOLDING NV": "ASML.AS",
    "SHELL PLC": "SHELL.AS",
    "SBM OFFSHORE NV": "SBMO.AS",

    "VANECK GLOBAL REAL ESTATE UCITS ETF": "TRET.DE",
    "VANECK DEFENSE UCITS ETF": "DFNS.L",
    "VANGUARD FTSE ALL-WORLD UCITS - (USD) ACCUMULATING ETF": "VWCE.DE",
}

# === 2. Lees transacties ===
df = pd.read_excel(INPUT_FILE)
df["Datum"] = pd.to_datetime(df["Datum"], dayfirst=True)
df.sort_values("Datum", inplace=True)

# === 3. Dagelijkse tijdreeks ===
start_date = df["Datum"].min()
end_date = pd.Timestamp.today().normalize()
all_days = pd.date_range(start=start_date, end=end_date, freq="D")

# === 4. Posities per dag ===
positions = (
    df.groupby(["Datum", "Product"])["Aantal"]
    .sum()
    .groupby("Product")
    .cumsum()
    .reset_index()
)

pivot = positions.pivot(index="Datum", columns="Product", values="Aantal").fillna(0)
pivot = pivot.reindex(all_days).ffill().fillna(0)
pivot.index.name = "date"

# === 5. Koersen ophalen ===
missing_tickers = []

def get_price_series(ticker, product):
    try:
        data = yf.download(ticker, period="5y", progress=False)
        if data.empty:
            missing_tickers.append(product)
            return pd.Series(dtype=float)

        # DataFrame → pak Close of Adj Close
        if isinstance(data, pd.DataFrame):
            if "Close" in data.columns:
                return data["Close"].ffill()
            elif "Adj Close" in data.columns:
                return data["Adj Close"].ffill()
            else:
                numeric_cols = data.select_dtypes(include=["number"])
                return numeric_cols.iloc[:, 0].ffill()

        # Series
        return data.ffill()

    except Exception:
        missing_tickers.append(product)
        return pd.Series(dtype=float)

price_data = {product: get_price_series(ticker, product) for product, ticker in TICKER_MAP.items()}

# === 6. Valuta-conversie ===
eurusd = yf.download("EURUSD=X", period="5y", progress=False)["Close"].ffill()
gbpeur = yf.download("GBPEUR=X", period="5y", progress=False)["Close"].ffill()

def convert_to_eur(value, ticker, date):
    if ticker.endswith(".AS") or ticker.endswith(".DE"):
        return float(value)
    elif ticker.endswith(".L"):
        rate_series = gbpeur[gbpeur.index <= date]
        rate = rate_series.values[-1].item() if not rate_series.empty else 1.17
        return float(value) * rate
    else:
        rate_series = eurusd[eurusd.index <= date]
        rate = rate_series.values[-1].item() if not rate_series.empty else 0.93
        return float(value) / rate

# === 7. Robuuste koers-extractie ===
def extract_last_value(series, product):
    if isinstance(series, pd.DataFrame):
        if "Close" in series.columns:
            return float(series["Close"].iloc[-1])
        elif "Adj Close" in series.columns:
            return float(series["Adj Close"].iloc[-1])
        else:
            numeric_cols = series.select_dtypes(include=["number"])
            if not numeric_cols.empty:
                return float(numeric_cols.iloc[-1].squeeze())
            print(f"⚠️ Geen numerieke kolommen voor {product}, waarde = 0")
            return 0.0
    else:
        return float(series.iloc[-1])

# === 8. Waarde per dag ===
portfolio_values = []

for date in all_days:
    total_value = 0.0
    for product in pivot.columns:
        amount = float(pivot.loc[date, product])
        if amount == 0:
            continue

        series = price_data.get(product)
        if series is None or series.empty:
            continue

        valid = series[series.index <= date]
        if valid.empty:
            continue

        raw_value = extract_last_value(valid, product)
        ticker = TICKER_MAP[product]
        price_eur = convert_to_eur(raw_value, ticker, date)
        total_value += amount * price_eur

    portfolio_values.append({"date": date, "total_value": total_value})

portfolio_df = pd.DataFrame(portfolio_values)
portfolio_df["total_value"] = pd.to_numeric(portfolio_df["total_value"], errors="coerce").fillna(0.0)
portfolio_df["daily_return"] = portfolio_df["total_value"].pct_change().fillna(0.0)

portfolio_df.to_csv(OUTPUT_FILE, index=False)
print(f"CSV opgeslagen als {OUTPUT_FILE}")

# === 9. Controle-overzicht ===
df["Inleg"] = df["Totaal EUR"].apply(lambda x: x if x < 0 else 0).abs()
df["Uitkering"] = df["Totaal EUR"].apply(lambda x: x if x > 0 else 0)

total_inleg = float(df["Inleg"].sum())
total_uitkering = float(df["Uitkering"].sum())
current_value = float(portfolio_df["total_value"].iloc[-1])
netto_resultaat = current_value + total_uitkering - total_inleg

print("\n=== Controle-overzicht ===")
print(f"Totale inleg:        € {total_inleg:,.2f}")
print(f"Totale uitkeringen:  € {total_uitkering:,.2f}")
print(f"Huidige waarde:      € {current_value:,.2f}")
print(f"Netto resultaat:     € {netto_resultaat:,.2f}")

# === 10. Positie-overzicht ===
print("\n=== Positie-overzicht ===")
for product in pivot.columns:
    amount = float(pivot.iloc[-1][product])
    if amount == 0:
        continue

    ticker = TICKER_MAP[product]
    series = price_data.get(product)
    if series is None or series.empty:
        continue

    raw_value = extract_last_value(series, product)
    price_eur = convert_to_eur(raw_value, ticker, all_days[-1])
    waarde = amount * price_eur

    print(f"{product:35} | {amount:6.2f} stuks | koers € {price_eur:8.2f} | waarde € {waarde:10.2f}")

# === 11. Grafiek totale waarde ===
plt.figure(figsize=(12, 6))
plt.plot(portfolio_df["date"], portfolio_df["total_value"], label="Portfolio waarde (EUR)")
plt.title("Portfolio waarde over tijd")
plt.xlabel("Datum")
plt.ylabel("Waarde (€)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(GRAPH_FILE)
print(f"Grafiek opgeslagen als {GRAPH_FILE}")

# === 12. Waarde-checker ===
print("\n=== Waarde-checker (script vs live) ===")

def get_live_price_eur(ticker):
    try:
        data = yf.download(ticker, period="1d", progress=False)
        if data.empty:
            data = yf.download(ticker, period="5d", progress=False)
            if data.empty:
                return None

        if "Close" in data.columns:
            price = data["Close"].iloc[-1]
        elif "Adj Close" in data.columns:
            price = data["Adj Close"].iloc[-1]
        else:
            price = data.select_dtypes(include=["number"]).iloc[-1].squeeze()

        if ticker.endswith(".AS") or ticker.endswith(".DE"):
            return float(price)
        elif ticker.endswith(".L"):
            return float(price) * float(gbpeur.iloc[-1])
        else:
            return float(price) / float(eurusd.iloc[-1])
    except:
        return None

checker_results = []

for product in pivot.columns:
    amount = float(pivot.iloc[-1][product])
    if amount == 0:
        continue

    ticker = TICKER_MAP[product]
    series = price_data.get(product)
    if series is None or series.empty:
        continue

    raw_value = extract_last_value(series, product)
    script_price_eur = convert_to_eur(raw_value, ticker, all_days[-1])
    script_value = amount * script_price_eur

    live_price_eur = get_live_price_eur(ticker)
    if live_price_eur is None:
        print(f"{product:35} | Geen live koers")
        continue

    live_value = amount * live_price_eur
    diff = live_value - script_value
    pct = (diff / live_value) * 100 if live_value != 0 else 0
    status = "OK" if abs(pct) <= 2 else "AFWIJKING"

    checker_results.append((product, script_value, live_value, diff, pct, status))

for product, script_value, live_value, diff, pct, status in checker_results:
    print(f"\n{product}")
    print(f"  Scriptwaarde: € {script_value:,.2f}")
    print(f"  Live waarde:  € {live_value:,.2f}")
    print(f"  Verschil:     € {diff:,.2f} ({pct:+.2f}%) → {status}")

# === 13. Vergelijkingsgrafieken per ticker ===
os.makedirs("charts", exist_ok=True)
print("\n=== Vergelijkingsgrafieken per ticker ===")

for product, ticker in TICKER_MAP.items():

    yahoo_series = price_data.get(product)
    if yahoo_series is None or yahoo_series.empty:
        print(f"Geen Yahoo-data voor {product}")
        continue

    if isinstance(yahoo_series, pd.DataFrame):
        if "Close" in yahoo_series.columns:
            base_series = yahoo_series["Close"]
        elif "Adj Close" in yahoo_series.columns:
            base_series = yahoo_series["Adj Close"]
        else:
            base_series = yahoo_series.select_dtypes(include=["number"]).iloc[:, 0]
    else:
        base_series = yahoo_series

    script_prices = base_series.map(lambda v: convert_to_eur(v, ticker, all_days[-1]))

    plt.figure(figsize=(10, 5))
    plt.plot(base_series.index, base_series, label="Yahoo koers (marktprijs)", color="blue")
    plt.plot(script_prices.index, script_prices, label="Script-koers (EUR)", color="orange")
    plt.title(f"{product} ({ticker}) — koersvergelijking over tijd")
    plt.xlabel("Datum")
    plt.ylabel("Koers (€)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    filename = f"charts/{product.replace(' ', '_')}_comparison.png"
    plt.savefig(filename)
    plt.close()

    print(f"Grafiek opgeslagen als {filename}")