import os
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000/api/v1")
REQUEST_TIMEOUT = 15


def api_call(method, path, *, token=None, json=None, data=None):
    url = f"{API_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.request(
            method, url, headers=headers, json=json, data=data, timeout=REQUEST_TIMEOUT
        )
        return response, None
    except requests.exceptions.RequestException as exc:
        return None, str(exc)


def authed_call(method, path, *, json=None, data=None):
    response, error = api_call(
        method, path, token=st.session_state.get("token"), json=json, data=data
    )
    if error:
        st.error(f"Servizio non raggiungibile: {error}")
        return None
    if response.status_code == 401:
        st.session_state.pop("token", None)
        st.session_state.pop("user_email", None)
        st.warning("Sessione scaduta. Effettua di nuovo il login.")
        st.rerun()
    return response


def poll_task(task_id, timeout=40, interval=1.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = authed_call("GET", f"/market/status/{task_id}")
        if response is None:
            return None
        payload = response.json()
        if payload.get("status") in ("SUCCESS", "FAILURE"):
            return payload
        time.sleep(interval)
    return {"status": "TIMEOUT", "result": None}


def render_auth():
    st.title("FinSight")
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            response, error = api_call(
                "POST", "/auth/login", data={"username": email, "password": password}
            )
            if error:
                st.error(f"Servizio non raggiungibile: {error}")
            elif response.status_code == 200:
                st.session_state["token"] = response.json()["access_token"]
                st.session_state["user_email"] = email
                st.rerun()
            elif response.status_code == 401:
                st.error("Email o password non validi.")
            else:
                st.error(f"Errore login ({response.status_code}).")

    with register_tab:
        with st.form("register_form"):
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password", type="password", key="reg_password")
            submitted = st.form_submit_button("Register")
        if submitted:
            response, error = api_call(
                "POST", "/auth/register", json={"email": email, "password": password}
            )
            if error:
                st.error(f"Servizio non raggiungibile: {error}")
            elif response.status_code == 201:
                st.success("Registrazione completata. Ora effettua il login.")
            elif response.status_code == 400:
                st.error("Email gia' registrata.")
            else:
                st.error(f"Errore registrazione ({response.status_code}).")


def render_sidebar():
    with st.sidebar:
        st.markdown(f"**Utente:** {st.session_state.get('user_email', '')}")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()


def create_portfolio_form():
    with st.expander("Nuovo portafoglio"):
        with st.form("create_portfolio_form"):
            name = st.text_input("Nome")
            description = st.text_area("Descrizione")
            submitted = st.form_submit_button("Crea")
        if submitted:
            if not name.strip():
                st.warning("Il nome e' obbligatorio.")
            else:
                response = authed_call(
                    "POST",
                    "/portfolios/",
                    json={"name": name, "description": description or None},
                )
                if response is not None and response.status_code == 201:
                    st.success("Portafoglio creato.")
                    st.rerun()
                elif response is not None:
                    st.error(f"Errore creazione ({response.status_code}).")


def add_position_form(portfolio_id):
    with st.expander("Aggiungi posizione"):
        with st.form("add_position_form"):
            ticker = st.text_input("Ticker")
            col1, col2 = st.columns(2)
            quantity = col1.number_input("Quantita'", min_value=0.0, step=1.0)
            average_price = col2.number_input("Prezzo medio", min_value=0.0, step=1.0)
            purchase_date = st.date_input("Data acquisto")
            col3, col4 = st.columns(2)
            sector = col3.text_input("Settore (opzionale)")
            market = col4.text_input("Mercato (opzionale)")
            submitted = st.form_submit_button("Aggiungi")
        if submitted:
            if not ticker.strip() or quantity <= 0 or average_price <= 0:
                st.warning("Ticker, quantita' e prezzo medio sono obbligatori.")
            else:
                payload = {
                    "ticker": ticker.upper(),
                    "quantity": quantity,
                    "average_price": average_price,
                    "purchase_date": datetime.combine(
                        purchase_date, datetime.min.time()
                    ).isoformat(),
                    "sector": sector or None,
                    "market": market or None,
                    "portfolio_id": portfolio_id,
                }
                response = authed_call("POST", "/positions/", json=payload)
                if response is not None and response.status_code == 201:
                    st.success("Posizione aggiunta.")
                    st.rerun()
                elif response is not None:
                    st.error(f"Errore ({response.status_code}).")


def fetch_market_data(tickers):
    with st.spinner("Scarico i dati di mercato..."):
        accepted, rate_limited, failed = [], [], []
        for ticker in tickers:
            response = authed_call("POST", f"/market/fetch/{ticker}")
            if response is None:
                return
            if response.status_code == 202:
                accepted.append((ticker, response.json()["task_id"]))
            elif response.status_code == 429:
                rate_limited.append(ticker)
            else:
                failed.append(ticker)
        succeeded = []
        for ticker, task_id in accepted:
            result = poll_task(task_id)
            if result and result.get("status") == "SUCCESS":
                succeeded.append(ticker)
            else:
                failed.append(ticker)
    if succeeded:
        st.success(f"Dati aggiornati: {', '.join(succeeded)}")
    if rate_limited:
        st.warning(
            f"Limite superato (max 5/min) per: {', '.join(rate_limited)}. Riprova tra un minuto."
        )
    if failed:
        st.error(f"Falliti: {', '.join(failed)}")


def generate_report(portfolio_id):
    with st.spinner("Genero il report AI..."):
        response = authed_call("POST", f"/ai/report/{portfolio_id}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite superato (max 3/min) sui report. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.success("Report generato.")
    elif result and result.get("status") == "FAILURE":
        st.error(f"Generazione fallita: {result.get('result')}")
    else:
        st.warning("Il report sta impiegando piu' del previsto; ricarica tra poco.")


def render_positions(portfolio_id):
    response = authed_call("GET", f"/positions/portfolio/{portfolio_id}")
    if response is None:
        return []
    if response.status_code != 200:
        st.error(f"Errore caricamento posizioni ({response.status_code}).")
        return []
    positions = response.json()
    if not positions:
        st.info("Nessuna posizione in questo portafoglio.")
        return []
    df = pd.DataFrame(positions)
    df["quantity"] = df["quantity"].astype(float)
    df["average_price"] = df["average_price"].astype(float)
    df["cost_basis"] = df["quantity"] * df["average_price"]
    st.dataframe(
        df[["ticker", "quantity", "average_price", "cost_basis", "sector", "market"]],
        use_container_width=True,
        hide_index=True,
    )
    fig = px.pie(df, names="ticker", values="cost_basis", title="Allocazione per costo")
    st.plotly_chart(fig, use_container_width=True)
    return positions


def render_reports(portfolio_id):
    with st.expander("Report storici"):
        response = authed_call("GET", f"/ai/reports/{portfolio_id}")
        if response is None:
            return
        if response.status_code != 200:
            st.error(f"Errore caricamento report ({response.status_code}).")
            return
        reports = response.json()
        if not reports:
            st.info("Nessun report generato per questo portafoglio.")
            return
        for report in reports:
            st.caption(f"Generato il {report['generated_at']}")
            st.markdown(report["report_text"])
            st.divider()


def render_portfolio_detail(portfolio):
    st.subheader(portfolio["name"])
    if portfolio.get("description"):
        st.caption(portfolio["description"])

    positions = render_positions(portfolio["id"])
    add_position_form(portfolio["id"])

    col1, col2 = st.columns(2)
    if col1.button("1. Scarica Dati Mercato", disabled=not positions):
        fetch_market_data([p["ticker"] for p in positions])
    if col2.button("2. Genera Report AI"):
        generate_report(portfolio["id"])

    render_reports(portfolio["id"])


def render_dashboard():
    st.title("I tuoi portafogli")
    create_portfolio_form()

    response = authed_call("GET", "/portfolios/")
    if response is None:
        return
    if response.status_code != 200:
        st.error(f"Errore caricamento portafogli ({response.status_code}).")
        return
    portfolios = response.json()
    if not portfolios:
        st.info("Non hai ancora portafogli. Creane uno qui sopra.")
        return

    options = {f"{p['name']} - {p['id'][:8]}": p for p in portfolios}
    choice = st.selectbox(
        "Seleziona un portafoglio", list(options.keys()), key="selected_portfolio"
    )
    st.divider()
    render_portfolio_detail(options[choice])


def main():
    st.set_page_config(page_title="FinSight", layout="wide")
    if "token" not in st.session_state:
        render_auth()
    else:
        render_sidebar()
        render_dashboard()


main()