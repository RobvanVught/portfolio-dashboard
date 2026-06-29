import streamlit as st
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")

st.title("📈 Mijn Portfolio Dashboard")

# --- Load data ---
@st.cache_data
def load_transactions():
    return pd.read_excel("Transactions.xlsx")

df = load_transactions()

df["Datum"] = pd.to_datetime(df["Datum"], dayfirst=True)
df.sort_values("Datum", inplace=True)

# --- Ticker mapping ---
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

# --- Build daily positions ---
start_date = df["Datum"].min()
end_date = pd.Timestamp.today().normalize()
all_days = pd.date_range(start=start_date, end=end_date, freq="D")

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

# --- Load prices ---
@st.cache_data
def load_price(ticker):
    data = yf.download(ticker, period="5y", progress=False)
    if "Close" in data.columns:
        return data["Close"].ffill()
    elif "Adj Close" in data.columns:
        return data["Adj Close"].ffill()
    else:
        return data.select_dtypes(include=["number"]).iloc[:, 0].ffill()

price_data = {product: load_price(ticker) for product, ticker in TICKER_MAP.items()}

# --- Currency ---
eurusd = yf.download("EURUSD=X", period="5y", progress=False)["Close"].ffill()
gbpeur = yf.download("GBPEUR=X", period="5y", progress=False)["Close"].ffill()

def convert_to_eur(value, ticker):
    if ticker.endswith(".AS") or ticker.endswith(".DE"):
        return float(value)
    elif ticker.endswith(".L"):
        return float(value) * float(gbpeur.iloc[-1])
    else:
        return float(value) / float(eurusd.iloc[-1])

# --- Portfolio value ---
portfolio_values = []

for date in all_days:
    total = 0
    for product in pivot.columns:
        amount = pivot.loc[date, product]
        if amount == 0:
            continue

        series = price_data[product]
        valid = series[series.index <= date]
        if valid.empty:
            continue

        raw = valid.iloc[-1]
        ticker = TICKER_MAP[product]
        price_eur = convert_to_eur(raw, ticker)
        total += amount * price_eur

    portfolio_values.append({"date": date, "value": total})

portfolio_df = pd.DataFrame(portfolio_values)

# --- Dashboard layout ---
tab1, tab2, tab3 = st.tabs(["📈 Totale waarde", "📊 Posities", "📉 Koersgrafieken"])

with tab1:
    st.subheader("Totale waarde over tijd")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(portfolio_df["date"], portfolio_df["value"])
    ax.set_title("Portfolio waarde")
    ax.grid(True)
    st.pyplot(fig)

with tab2:
    st.subheader("Positie-overzicht")
    rows = []
    for product in pivot.columns:
        amount = pivot.iloc[-1][product]
        if amount == 0:
            continue

        ticker = TICKER_MAP[product]
        series = price_data[product]
        raw = series.iloc[-1]
        price_eur = convert_to_eur(raw, ticker)
        value = amount * price_eur

        rows.append([product, amount, price_eur, value])

    pos_df = pd.DataFrame(rows, columns=["Product", "Aantal", "Koers (EUR)", "Waarde (EUR)"])
    st.dataframe(pos_df)

with tab3:
    st.subheader("Koersgrafieken per product")
    product = st.selectbox("Kies een product", list(TICKER_MAP.keys()))
    ticker = TICKER_MAP[product]
    series = price_data[product]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(series.index, series.values)
    ax.set_title(f"{product} ({ticker})")
    ax.grid(True)
    st.pyplot(fig)
