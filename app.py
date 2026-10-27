
import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="NSE Paper Trader",
    page_icon="📈",
    layout="wide"
)

CAPITAL = 1_000_000
FILE = "paper_account.json"

# Verify current NSE lot sizes before relying on calculations.
LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30
}

INDEX_SYMBOLS = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK"
}


def new_account():
    return {
        "cash": CAPITAL,
        "positions": [],
        "history": []
    }


def load_account():
    try:
        with open(FILE, "r") as f:
            data = json.load(f)
        data.setdefault("cash", CAPITAL)
        data.setdefault("positions", [])
        data.setdefault("history", [])
        return data
    except (OSError, ValueError, TypeError):
        return new_account()


if "account" not in st.session_state:
    st.session_state.account = load_account()

account = st.session_state.account


def save_account():
    try:
        with open(FILE, "w") as f:
            json.dump(account, f, indent=2)
    except OSError:
        st.warning(
            "Account could not be saved permanently. "
            "Cloud storage may reset after a restart."
        )


def rupees(value):
    return f"₹{value:,.2f}"


def index_price(symbol):
    try:
        data = yf.Ticker(symbol).history(
            period="5d",
            interval="15m"
        )
        if data.empty:
            data = yf.Ticker(symbol).history(period="1mo")

        data = data.dropna(subset=["Close"])
        if data.empty:
            return None

        return float(data["Close"].iloc[-1])
    except Exception:
        return None


def get_option_data(underlying, option_type):
    """
    Attempts to get an option contract from Yahoo Finance.
    Yahoo Finance may not provide NSE index option chains.
    """
    symbol = INDEX_SYMBOLS[underlying]
    spot = index_price(symbol)

    if spot is None:
        return None, "Index price is unavailable."

    try:
        ticker = yf.Ticker(symbol)
        expiries = ticker.options

        if not expiries:
            return None, (
                "Yahoo Finance does not provide an option chain "
                "for this index right now. No order was placed."
            )

        expiry = expiries[0]
        chain = ticker.option_chain(expiry)
        options = chain.calls if option_type == "CE" else chain.puts

        if options.empty or "strike" not in options.columns:
            return None, "No option contracts were returned."

        options = options.copy()
        options["distance"] = (options["strike"] - spot).abs()
        contract = options.sort_values("distance").iloc[0]

        bid = float(contract.get("bid", 0) or 0)
        ask = float(contract.get("ask", 0) or 0)
        last = float(contract.get("lastPrice", 0) or 0)

        if bid > 0 and ask > 0 and ask >= bid:
            premium = (bid + ask) / 2
        elif last > 0:
            premium = last
        else:
            return None, "No usable option premium was returned."

        return {
            "underlying": underlying,
            "type": option_type,
            "strike": float(contract["strike"]),
            "expiry": str(expiry),
            "premium": premium,
            "spot": spot,
            "contract_symbol": str(
                contract.get("contractSymbol", "")
            )
        }, None

    except Exception as exc:
        return None, (
            "Could not retrieve option data from Yahoo Finance: "
            + str(exc)
        )


def update_position_price(position):
    """
    Refreshes a position only when Yahoo returns the same strike
    and expiry. Does not substitute an index price for a premium.
    """
    try:
        data, error = get_option_data(
            position["underlying"],
            position["type"]
        )

        if data and not error:
            if (
                data["strike"] == position["strike"]
                and data["expiry"] == position["expiry"]
            ):
                position["last"] = data["premium"]
                position["last_updated"] = datetime.now().isoformat(
                    timespec="seconds"
                )
    except Exception:
        pass


st_autorefresh(interval=60_000, key="market_refresh")

st.title("NSE Paper Trading Dashboard")
st.caption("Educational simulator only — no real orders.")
st.info("Starting Virtual Capital: ₹10,00,000")

page = st.selectbox(
    "Select Section",
    [
        "Dashboard",
        "Place Paper Order",
        "Open Positions",
        "Trade History"
    ]
)


if page == "Dashboard":
    st.subheader("Index Market Watch")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### NIFTY 50")
        nifty = index_price("^NSEI")
        st.metric(
            "Latest available index price",
            rupees(nifty) if nifty is not None else "Unavailable"
        )

    with col2:
        st.markdown("### BANKNIFTY")
        banknifty = index_price("^NSEBANK")
        st.metric(
            "Latest available index price",
            rupees(banknifty)
            if banknifty is not None else "Unavailable"
        )

    for position in account["positions"]:
        update_position_price(position)

    market_value = sum(
        p["last"] * p["lots"] * p["lot_size"]
        for p in account["positions"]
    )

    unrealised = sum(
        (p["last"] - p["entry"])
        * p["lots"]
        * p["lot_size"]
        for p in account["positions"]
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Available Cash", rupees(account["cash"]))
    col2.metric("Open Positions", len(account["positions"]))
    col3.metric("Unrealised P&L", rupees(unrealised))

    st.caption(
        "Yahoo Finance prices can be delayed or unavailable. "
        "Automatic refresh does not guarantee real-time quotes."
    )

    save_account()


elif page == "Place Paper Order":
    st.subheader("Place a Simulated Options Order")

    with st.form("paper_order"):
        order_type = st.selectbox(
            "Order Type",
            [
                "BUY NIFTY CE",
                "BUY NIFTY PE",
                "BUY BANKNIFTY CE",
                "BUY BANKNIFTY PE"
            ]
        )

        quantity = st.number_input(
            "Quantity (number of lots)",
            min_value=1,
            max_value=100,
            value=1,
            step=1
        )

        stop_loss_pct = st.number_input(
            "Stop-loss (%)",
            min_value=1.0,
            max_value=95.0,
            value=25.0,
            step=1.0
        )

        submitted = st.form_submit_button(
            "Fetch Price and Place Paper Order",
            type="primary"
        )

    if submitted:
        parts = order_type.split()
        underlying = parts[1]
        option_type = parts[2]

        with st.spinner("Fetching data from Yahoo Finance..."):
            data, error = get_option_data(
                underlying,
                option_type
            )

        if error:
            st.error(error)
            st.warning(
                "No order was placed because a usable option price "
                "was not available."
            )

        else:
            lot_size = LOT_SIZES[underlying]
            premium = data["premium"]
            lots = int(quantity)
            total_cost = premium * lot_size * lots
            stop_price = premium * (1 - stop_loss_pct / 100)

            st.write("Index price:", rupees(data["spot"]))
            st.write("Expiry:", data["expiry"])
            st.write("Strike:", data["strike"])
            st.write("Option premium:", rupees(premium))
            st.write("Configured lot size:", lot_size)
            st.write("Total simulated cost:", rupees(total_cost))
            st.write("Stop-loss premium:", rupees(stop_price))

            if total_cost > account["cash"]:
                st.error("Insufficient virtual cash.")

            else:
                position = {
                    "id": datetime.now().strftime(
                        "%Y%m%d%H%M%S%f"
                    ),
                    "underlying": underlying,
                    "type": option_type,
                    "strike": data["strike"],
                    "expiry": data["expiry"],
                    "contract_symbol": data["contract_symbol"],
                    "entry": premium,
                    "last": premium,
                    "lot_size": lot_size,
                    "lots": lots,
                    "stop": stop_price,
                    "stop_loss_pct": float(stop_loss_pct),
                    "entry_time": datetime.now().isoformat(
                        timespec="seconds"
                    )
                }

                account["cash"] -= total_cost
                account["positions"].append(position)
                account["history"].append({
                    **position,
                    "status": "OPEN"
                })

                save_account()
                st.success(
                    "Paper order recorded. No real order was placed."
                )


elif page == "Open Positions":
    st.subheader("Open Positions")

    if not account["positions"]:
        st.info("No open positions.")

    for position in list(account["positions"]):
        update_position_price(position)

        quantity = position["lots"] * position["lot_size"]
        pnl = (
            position["last"] - position["entry"]
        ) * quantity

        with st.container(border=True):
            st.markdown(
                f"### {position['underlying']} "
                f"{position['strike']} {position['type']}"
            )

            st.write("Expiry:", position["expiry"])
            st.write("Entry premium:", rupees(position["entry"]))
            st.write(
                "Latest available premium:",
                rupees(position["last"])
            )
            st.write("Stop-loss premium:", rupees(position["stop"]))
            st.write("Unrealised P&L:", rupees(pnl))

            if position["last"] <= position["stop"]:
                st.warning(
                    "Stop-loss threshold reached. This version alerts "
                    "you but does not automatically close the position."
                )

            with st.form("close_" + position["id"]):
                close = st.form_submit_button(
                    "Close at Latest Available Mark"
                )

            if close:
                exit_price = position["last"]
                realised = (
                    exit_price - position["entry"]
                ) * quantity

                account["cash"] += exit_price * quantity

                account["history"].append({
                    **position,
                    "exit": exit_price,
                    "realised_pnl": realised,
                    "exit_time": datetime.now().isoformat(
                        timespec="seconds"
                    ),
                    "status": "CLOSED"
                })

                account["positions"] = [
                    p for p in account["positions"]
                    if p["id"] != position["id"]
                ]

                save_account()
                st.success(
                    "Position closed in simulation. Realised P&L: "
                    + rupees(realised)
                )
                st.rerun()

    save_account()


elif page == "Trade History":
    st.subheader("Trade History")

    if account["history"]:
        history_df = pd.DataFrame(account["history"])

        st.dataframe(
            history_df,
            use_container_width=True
        )

        st.download_button(
            "Download History CSV",
            history_df.to_csv(index=False),
            "trade_history.csv",
            "text/csv"
        )
    else:
        st.info("No trades recorded yet.")


st.divider()
st.caption(
    "Paper trading only. Yahoo Finance may not support these NSE "
    "option chains. Configured lot sizes must be checked against current "
    "NSE specifications. Stop-loss alerts do not guarantee execution."
)
