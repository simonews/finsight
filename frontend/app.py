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
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown("## 📈 FinSight")
        st.caption("Monitora e analizza i tuoi portafogli")
        with st.container(border=True):
            login_tab, register_tab = st.tabs(["Login", "Register"])

            with login_tab:
                with st.form("login_form"):
                    email = st.text_input("Email")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button("Login", use_container_width=True)
                if submitted:
                    response, error = api_call(
                        "POST",
                        "/auth/login",
                        data={"username": email, "password": password},
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
                    password = st.text_input(
                        "Password", type="password", key="reg_password"
                    )
                    submitted = st.form_submit_button(
                        "Register", use_container_width=True
                    )
                if submitted:
                    response, error = api_call(
                        "POST",
                        "/auth/register",
                        json={"email": email, "password": password},
                    )
                    if error:
                        st.error(f"Servizio non raggiungibile: {error}")
                    elif response.status_code == 201:
                        st.success("Registrazione completata. Ora effettua il login.")
                    elif response.status_code == 400:
                        st.error("Email gia' registrata.")
                    else:
                        st.error(f"Errore registrazione ({response.status_code}).")


def create_portfolio_form():
    with st.expander("Nuovo portafoglio"):
        with st.form("create_portfolio_form"):
            name = st.text_input("Nome")
            description = st.text_area("Descrizione")
            submitted = st.form_submit_button("Crea", use_container_width=True)
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
                    st.toast("Portafoglio creato", icon="✅")
                    st.rerun()
                elif response is not None:
                    st.error(f"Errore creazione ({response.status_code}).")


def render_sidebar():
    with st.sidebar:
        st.markdown("### 📈 FinSight")
        st.markdown(f"Connesso come **{st.session_state.get('user_email', '')}**")
        st.divider()
        create_portfolio_form()
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()


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
            submitted = st.form_submit_button("Aggiungi", use_container_width=True)
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
                    st.toast("Posizione aggiunta", icon="✅")
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
        for _, task_id in accepted:
            result = poll_task(task_id)
            if not (result and result.get("status") == "SUCCESS"):
                failed.append(task_id)
    if accepted and not rate_limited and not failed:
        st.toast("Dati aggiornati con successo", icon="✅")
        return
    if rate_limited:
        st.warning(
            f"Limite superato (max 5/min) per: {', '.join(rate_limited)}. Riprova tra un minuto."
        )
    if failed:
        st.warning("Aggiornamento non riuscito per alcune posizioni.")
    if accepted:
        st.toast("Dati parzialmente aggiornati", icon="✅")


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
        st.toast("Report generato", icon="🤖")
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

    m1, m2, m3 = st.columns(3)
    m1.metric("Posizioni", len(df),
              help="Numero di posizioni (righe) presenti nel portafoglio.")
    m2.metric("Ticker", int(df["ticker"].nunique()),
              help="Numero di titoli distinti detenuti.")
    m3.metric("Costo totale", f"{df['cost_basis'].sum():,.2f}",
              help="Capitale investito: somma di quantita' x prezzo medio di carico.")

    st.dataframe(
        df[["ticker", "quantity", "average_price", "cost_basis", "sector", "market"]],
        use_container_width=True,
        hide_index=True,
    )
    return positions

def render_charts_and_pnl(portfolio_id, positions):
    pie_df = pd.DataFrame(positions)
    pie_df["cost_basis"] = (
        pie_df["quantity"].astype(float) * pie_df["average_price"].astype(float)
    )

    response = authed_call("GET", f"/market/prices/{portfolio_id}")
    analytics = None
    if response is not None and response.status_code == 200:
        analytics = response.json()
    elif response is not None:
        st.warning("Dati di mercato non disponibili al momento (P/L e andamento prezzi).")

    if analytics:
        totals = analytics["totals"]
        c1, c2 = st.columns(2)
        c1.metric(
            "Valore attuale", f"{totals['current_value']:,.2f}",
            help="Valore di mercato corrente: somma di quantita' x prezzo attuale di ogni titolo.",
        )
        c2.metric(
            "Guadagno/Perdita", f"{totals['pnl']:,.2f}",
            delta=f"{totals['pnl_pct']:.2f}%",
            help="Differenza tra valore attuale e costo di carico. La percentuale e' la variazione rispetto al capitale investito.",
        )

    chart_left, chart_right = st.columns([1, 2])
    with chart_left:
        fig_pie = px.pie(
            pie_df, names="ticker", values="cost_basis", title="Allocazione per costo"
        )
        fig_pie.update_layout(height=320, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)
    with chart_right:
        if analytics and analytics["history"]["dates"]:
            hist = analytics["history"]
            hist_df = pd.DataFrame(
                hist["series"], index=pd.to_datetime(hist["dates"])
            )
            fig_line = px.line(hist_df, title="Andamento prezzi (ultimi 12 mesi)")
            fig_line.update_layout(
                height=320, margin=dict(t=40, b=0, l=0, r=0), legend_title_text=""
            )
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("Andamento prezzi non disponibile al momento.")

    if analytics and analytics["positions"]:
        pnl_df = pd.DataFrame(analytics["positions"])
        st.dataframe(
            pnl_df[
                ["ticker", "current_price", "current_value", "cost_basis", "pnl", "pnl_pct"]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "current_price": "Prezzo attuale",
                "current_value": "Valore attuale",
                "cost_basis": "Costo",
                "pnl": "P/L",
                "pnl_pct": "P/L %",
            },
        )
    metrics = analytics.get("metrics") if analytics else None
    if metrics and metrics["per_ticker"]:
        with st.expander("Dettagli tecnici (Quant)"):
            t1, t2 = st.columns(2)
            t1.metric(
                "Volatilita' annualizzata",
                f"{metrics['annualized_volatility'] * 100:.2f}%",
                help="Deviazione standard annualizzata dei rendimenti giornalieri pesati del portafoglio: piu' alta = piu' oscillazioni/rischio.",
            )
            t2.metric(
                "Rendimento 1Y (portafoglio)",
                f"{metrics['portfolio_return_1y'] * 100:.2f}%",
                help="Rendimento dell'ultimo anno, come media dei rendimenti dei titoli pesata per i pesi di mercato.",
            )
            tech_df = pd.DataFrame(metrics["per_ticker"])
            st.dataframe(
                tech_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ticker": "Ticker",
                    "weight_pct": "Peso (mercato) %",
                    "return_1y_pct": "Rendimento 1Y %",
                },
            )


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
            with st.container(border=True):
                st.caption(f"Generato il {report['generated_at']}")
                st.markdown(report["report_text"])

def close_portfolio_control(portfolio):
    with st.expander("⚠️ Chiudi portafoglio"):
        st.caption(
            f"Eliminerai definitivamente '{portfolio['name']}' con tutte le sue posizioni e report. Operazione irreversibile."
        )
        confirm = st.checkbox(
            "Confermo di voler eliminare questo portafoglio", key="confirm_delete"
        )
        if st.button(
            "Elimina definitivamente", disabled=not confirm, use_container_width=True
        ):
            response = authed_call("DELETE", f"/portfolios/{portfolio['id']}")
            if response is not None and response.status_code == 204:
                st.session_state.pop("selected_portfolio", None)
                st.toast("Portafoglio eliminato", icon="🗑️")
                st.rerun()
            elif response is not None:
                st.error(f"Errore ({response.status_code}).")


def render_portfolio_detail(portfolio):
    st.subheader(portfolio["name"])
    if portfolio.get("description"):
        st.caption(portfolio["description"])

    positions = render_positions(portfolio["id"])
    if positions:
        render_charts_and_pnl(portfolio["id"], positions)

    add_position_form(portfolio["id"])
    if positions:
        remove_position_control(positions)

    b1, b2 = st.columns(2)
    if b1.button(
        "⬇️ Scarica Dati Mercato", use_container_width=True, disabled=not positions
    ):
        fetch_market_data([p["ticker"] for p in positions])
    if b2.button("🤖 Genera Report AI", use_container_width=True):
        generate_report(portfolio["id"])

    render_reports(portfolio["id"])
    close_portfolio_control(portfolio)


def render_dashboard():
    st.title("I tuoi portafogli")

    response = authed_call("GET", "/portfolios/")
    if response is None:
        return
    if response.status_code != 200:
        st.error(f"Errore caricamento portafogli ({response.status_code}).")
        return
    portfolios = response.json()
    if not portfolios:
        st.info("Non hai ancora portafogli. Creane uno dalla barra laterale.")
        return

    options = {f"{p['name']} - {p['id'][:8]}": p for p in portfolios}
    choice = st.selectbox(
        "Seleziona un portafoglio", list(options.keys()), key="selected_portfolio"
    )
    st.divider()
    render_portfolio_detail(options[choice])


def remove_position_control(positions):
    with st.expander("Rimuovi posizione"):
        labels = {
            f"{p['ticker']} · qta {float(p['quantity']):g} · {p['id'][:8]}": p["id"]
            for p in positions
        }
        choice = st.selectbox(
            "Posizione da rimuovere", list(labels.keys()), key="remove_position"
        )
        if st.button("Rimuovi", use_container_width=True):
            response = authed_call("DELETE", f"/positions/{labels[choice]}")
            if response is not None and response.status_code == 204:
                st.toast("Posizione rimossa", icon="🗑️")
                st.rerun()
            elif response is not None:
                st.error(f"Errore ({response.status_code}).")


def main():
    st.set_page_config(page_title="FinSight", page_icon="📈", layout="wide")
    st.markdown(
        "<style>.block-container{padding-top:2.5rem;}</style>",
        unsafe_allow_html=True,
    )
    if "token" not in st.session_state:
        render_auth()
    else:
        render_sidebar()
        render_dashboard()


main()