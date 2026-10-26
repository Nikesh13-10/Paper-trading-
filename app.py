
import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import date, datetime

st.set_page_config(
    page_title="NSE Paper Trader",
    page_icon="📈",
    layout="wide"
)

CAPITAL = 1000000
FILE = "paper_account.json"

def new_account():
    return {
        "cash": CAPITAL,
        "positions": [],
        "history": []
    }

def load_account():
    try:
        with open(FILE, "r") as f:
            return json.load(f)
    except Exception:
        return new_account()

if "account" not in st.session_state:
    st.session_state.account = load_account()

account = st.session_state.account

def save_account():
    with open(FILE, "w") as f:
        json.dump(account, f, indent=2)

def rupees(value):
    return f"₹{value:,.2f}"

def index_price(symbol):
    try:
        data = yf.Ticker(symbol).history(period="5d", interval="15m")
        if data.empty:
            data = yf.Ticker(symbol).history(period="1mo")
        if data.empty:
            return None
        return float(data["Close"].dropna().iloc[-1])
    except Exception:
        return None

st.title("NSE Paper Trading Dashboard")
st.caption("Practice trading only — no real orders")

st.info("Starting Virtual Capital: ₹10,00,000")

page = st.selectbox(
    "Select Section",
    [
        "Dashboard",
        "Options Paper Trade",
        "Open Positions",
        "Trade History"
    ]
)

if page == "Dashboard":
    st.subheader("Index Market Watch")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### NIFTY 50")
        price = index_price("^NSEI")
        st.metric(
            "Last available index price",
            f"{price:,.2f}" if price is not None else "Unavailable"
        )

    with c2:
        st.markdown("### BANKNIFTY")
        price = index_price("^NSEBANK")
        st.metric(
            "Last available index price",
            f"{price:,.2f}" if price is not None else "Unavailable"
        )

    market_value = sum(
        p["last"] * p["lots"] * p["lot_size"]
        for p in account["positions"]
    )

    pnl = sum(
        (p["last"] - p["entry"]) * p["lots"] * p["lot_size"]
        - p["fees"]
        for p in account["positions"]
    )

    equity = account["cash"] + market_value

    st.divider()
    a, b, c = st.columns(3)

    a.metric("Available Cash", rupees(account["cash"]))
    b.metric("Open Positions", len(account["positions"]))
    c.metric("Unrealised P&L", rupees(pnl))

    st.caption(
        "Quotes may be delayed or unavailable. "
        "Index prices are not option premiums."
    )

elif page == "Options Paper Trade":
    st.subheader("Buy Options — Simulation Only")

    with st.form("buy_option"):
        underlying = st.selectbox(
            "Underlying",
            ["NIFTY 50", "BANKNIFTY"]
        )

        option_type = st.radio(
            "Option Type",
            ["CE", "PE"],
            horizontal=True
        )

        strike = st.number_input(
            "Strike Price",
            min_value=1,
            value=25000,
            step=50
        )

        expiry = st.date_input(
            "Expiry Date",
            value=date.today()
        )

        premium = st.number_input(
            "Option Premium per Unit (₹)",
            min_value=0.05,
            value=100.0,
            step=0.05
        )

        lot_size = st.number_input(
            "Lot Size — Verify Current NSE Specification",
            min_value=1,
            value=65 if underlying == "NIFTY 50" else 30
        )

        lots = st.number_input(
            "Number of Lots",
            min_value=1,
            value=1
        )

        fees = st.number_input(
            "Estimated Entry Charges (₹)",
            min_value=0.0,
            value=40.0
        )

        stop_loss = st.number_input(
            "Stop-Loss Premium (0 = None)",
            min_value=0.0,
            value=0.0
        )

        target = st.number_input(
            "Target Premium (0 = None)",
            min_value=0.0,
            value=0.0
        )

        submitted = st.form_submit_button(
            "Place Simulated Buy",
            type="primary"
        )

    if submitted:
        cost = premium * lot_size * lots + fees

        if cost > account["cash"]:
            st.error("Insufficient virtual balance.")

        elif stop_loss and stop_loss >= premium:
            st.error("Stop-loss should be below entry premium.")

        elif target and target <= premium:
            st.error("Target should be above entry premium.")

        else:
            position = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "underlying": underlying,
                "type": option_type,
                "strike": strike,
                "expiry": expiry.isoformat(),
                "entry": premium,
                "last": premium,
                "lot_size": int(lot_size),
                "lots": int(lots),
                "fees": fees,
                "stop": stop_loss,
                "target": target
            }

            account["cash"] -= cost
            account["positions"].append(position)
            account["history"].append({
                **position,
                "status": "OPEN"
            })

            save_account()

            st.success(
                "Paper trade recorded. No real order was placed."
            )

elif page == "Open Positions":
    st.subheader("Your Open Positions")

    if not account["positions"]:
        st.write("No open positions.")

    for p in list(account["positions"]):
        quantity = p["lots"] * p["lot_size"]

        pnl = (
            (p["last"] - p["entry"]) * quantity
            - p["fees"]
        )

        with st.container(border=True):
            st.markdown(
                f"### {p['underlying']} {p['strike']} {p['type']}"
            )

            st.write("Expiry:", p["expiry"])
            st.write("Entry Premium:", rupees(p["entry"]))
            st.write("Current Mark:", rupees(p["last"]))
            st.write("Unrealised P&L:", rupees(pnl))
            st.write("Stop-loss:", p["stop"] or "Not set")
            st.write("Target:", p["target"] or "Not set")

            with st.form("close_" + p["id"]):
                exit_price = st.number_input(
                    "Exit Premium (₹)",
                    min_value=0.0,
                    value=float(p["last"]),
                    key="exit_" + p["id"]
                )

                exit_fees = st.number_input(
                    "Exit Charges (₹)",
                    min_value=0.0,
                    value=40.0,
                    key="fee_" + p["id"]
                )

                close = st.form_submit_button("Close Position")

            if close:
                realised = (
                    (exit_price - p["entry"]) * quantity
                    - p["fees"]
                    - exit_fees
                )

                account["cash"] += (
                    exit_price * quantity - exit_fees
                )

                account["history"].append({
                    **p,
                    "exit": exit_price,
                    "realised_pnl": realised,
                    "status": "CLOSED"
                })

                account["positions"] = [
                    x for x in account["positions"]
                    if x["id"] != p["id"]
                ]

                save_account()

                st.success(
                    "Position closed. Realised P&L: "
                    + rupees(realised)
                )

                st.rerun()

elif page == "Trade History":
    st.subheader("Trade History")

    if account["history"]:
        st.dataframe(
            pd.DataFrame(account["history"]),
            use_container_width=True
        )
    else:
        st.write("No trades recorded yet.")

    st.download_button(
        "Download History CSV",
        pd.DataFrame(account["history"]).to_csv(index=False),
        "trade_history.csv",
        "text/csv"
    )

st.divider()
st.caption(
    "Educational simulator only. Option premiums are entered manually. "
    "Live option-chain data and automatic stop-loss execution are not "
    "included. Verify expiry dates and lot sizes with NSE."
)
