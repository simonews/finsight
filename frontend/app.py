import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import json

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import plotly.graph_objects as go

API_BASE_URL = os.environ.get("API_BASE_URL", "http://api:8000/api/v1")
REQUEST_TIMEOUT = 30
LOCAL_TZ = ZoneInfo("Europe/Rome")

def _color_pnl(val):
    if val is None or pd.isna(val):
        return ""
    if val > 0:
        return "color: #16a34a"   # verde
    if val < 0:
        return "color: #dc2626"   # rosso
    return ""


def _fmt_qty(val):
    if val is None or pd.isna(val):
        return "—"
    val = float(val)
    return f"{val:,.0f}" if val.is_integer() else f"{val:,.2f}"

def _parse_import_date(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return datetime.combine(datetime.today().date(), datetime.min.time()).isoformat()
    try:
        return datetime.combine(pd.to_datetime(value).date(), datetime.min.time()).isoformat()
    except Exception:
        return datetime.combine(datetime.today().date(), datetime.min.time()).isoformat()
    
def summarize_news(ticker):
    with st.spinner(f"Riassumo le notizie su {ticker}..."):
        response = authed_call("POST", f"/ai/news/{ticker}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite superato (max 3/min) sulle analisi AI. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.session_state[f"ai_news_{ticker}"] = result["result"]["summary"]
    elif result and result.get("status") == "FAILURE":
        st.error(f"Riassunto fallito: {result.get('result')}")
    else:
        st.warning("Il riassunto sta impiegando piu' del previsto; riprova tra poco.")

def fetch_holdings(ticker):
    with st.spinner(f"Recupero la composizione di {ticker}..."):
        response = authed_call("POST", f"/market/holdings/{ticker}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite di richieste superato. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.session_state[f"ai_holdings_{ticker}"] = result["result"]
    elif result and result.get("status") == "FAILURE":
        st.error(f"Recupero fallito: {result.get('result')}")
    else:
        st.warning("Il recupero sta impiegando piu' del previsto; riprova tra poco.")

def fetch_analyst_data(ticker):
    with st.spinner(f"Recupero i target analisti di {ticker}..."):
        response = authed_call("POST", f"/market/analyst/{ticker}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite di richieste superato. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.session_state[f"ai_analyst_{ticker}"] = result["result"]
    elif result and result.get("status") == "FAILURE":
        st.error(f"Recupero fallito: {result.get('result')}")
    else:
        st.warning("Il recupero sta impiegando piu' del previsto; riprova tra poco.")


def import_positions_control(portfolio_id):
    st.markdown("**Importa da file (CSV o JSON)**")
    st.caption("Colonne richieste: ticker, quantity, average_price. Opzionali: purchase_date, sector, market.")
    uploaded = st.file_uploader("File posizioni", type=["csv", "json"], key="import_file")
    if uploaded is None:
        return
    try:
        if uploaded.name.lower().endswith(".json"):
            raw = json.load(uploaded)
            rows = raw if isinstance(raw, list) else raw.get("positions", [])
            df = pd.DataFrame(rows)
        else:
            df = pd.read_csv(uploaded)
    except Exception as exc:
        st.error(f"File non leggibile: {exc}")
        return

    df.columns = [str(c).lower().strip() for c in df.columns]
    required = {"ticker", "quantity", "average_price"}
    if not required.issubset(set(df.columns)):
        st.error("Mancano colonne obbligatorie: ticker, quantity, average_price.")
        return

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)
    if st.button("Importa posizioni", use_container_width=True):
        imported, failed = 0, 0
        for _, row in df.iterrows():
            try:
                payload = {
                    "ticker": str(row["ticker"]).upper().strip(),
                    "quantity": float(row["quantity"]),
                    "average_price": float(row["average_price"]),
                    "purchase_date": _parse_import_date(
                        row["purchase_date"] if "purchase_date" in df.columns else None
                    ),
                    "sector": str(row["sector"]) if "sector" in df.columns and pd.notna(row["sector"]) else None,
                    "market": str(row["market"]) if "market" in df.columns and pd.notna(row["market"]) else None,
                    "portfolio_id": portfolio_id,
                }
                if not payload["ticker"] or payload["quantity"] <= 0 or payload["average_price"] <= 0:
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                failed += 1
                continue
            response = authed_call("POST", "/positions/", json=payload)
            if response is not None and response.status_code == 201:
                imported += 1
            else:
                failed += 1
        st.toast(f"Importate {imported} posizioni", icon="📥")
        if failed:
            st.warning(f"{failed} righe non importate (dati mancanti o non validi).")
        st.rerun()

def _format_timestamp(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")
    except (ValueError, AttributeError):
        return iso_string



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
                    submitted = st.form_submit_button("Register", use_container_width=True)
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
                    "POST", "/portfolios/", json={"name": name, "description": description or None}
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


def get_positions(portfolio_id):
    response = authed_call("GET", f"/positions/portfolio/{portfolio_id}")
    if response is None:
        return []
    if response.status_code != 200:
        st.error(f"Errore caricamento posizioni ({response.status_code}).")
        return []
    return response.json()


def fetch_analytics(portfolio_id):
    response = authed_call("GET", f"/market/prices/{portfolio_id}")
    if response is not None and response.status_code == 200:
        return response.json()
    if response is not None:
        st.warning("Dati di mercato non disponibili al momento.")
    return None


def render_summary(positions, analytics):
    df = pd.DataFrame(positions) if positions else pd.DataFrame()
    cost_total = 0.0
    if not df.empty:
        df["cost_basis"] = df["quantity"].astype(float) * df["average_price"].astype(float)
        cost_total = float(df["cost_basis"].sum())

    c = st.columns(4)
    c[0].metric("Posizioni", len(positions),
                help="Numero di posizioni presenti nel portafoglio.")
    c[1].metric("Ticker", int(df["ticker"].nunique()) if not df.empty else 0,
                help="Numero di titoli distinti detenuti.")
    c[2].metric("Costo totale", f"{cost_total:,.2f}",
                help="Capitale investito: somma di quantita' x prezzo medio di carico.")
    if analytics:
        totals = analytics["totals"]
        c[3].metric("Valore attuale", f"{totals['current_value']:,.2f}",
                    delta=f"{totals['pnl']:,.2f}",
                    help="Valore di mercato corrente; la variazione e' il guadagno/perdita complessivo.")
    else:
        c[3].metric("Valore attuale", "—",
                    help="Disponibile dopo il calcolo dei prezzi di mercato.")


def render_positions_table(positions):
    if not positions:
        st.info("Nessuna posizione. Aggiungine una dalla barra in alto.")
        return
    df = pd.DataFrame(positions)
    df["quantity"] = df["quantity"].astype(float)
    df["average_price"] = df["average_price"].astype(float)
    df["cost_basis"] = df["quantity"] * df["average_price"]
    df = df[["ticker", "quantity", "average_price", "cost_basis", "sector", "market"]]

    styled = df.style.format(
        {"quantity": _fmt_qty, "average_price": "{:,.2f}", "cost_basis": "{:,.2f}"},
        na_rep="—",
    )
    st.dataframe(
        styled,
        use_container_width=True, hide_index=True,
        column_config={
            "ticker": st.column_config.Column("Ticker", help="Simbolo di borsa del titolo."),
            "quantity": st.column_config.Column("Quantita'", help="Numero di azioni/quote possedute."),
            "average_price": st.column_config.Column("Prezzo medio", help="Prezzo medio di carico: quanto hai pagato per unita'."),
            "cost_basis": st.column_config.Column("Costo", help="Costo totale della posizione: quantita' x prezzo medio."),
            "sector": st.column_config.Column("Settore", help="Settore economico del titolo (se inserito)."),
            "market": st.column_config.Column("Mercato", help="Mercato/borsa di quotazione (se inserito)."),
        },
    )


def render_pnl_table(analytics):
    if not analytics or not analytics["positions"]:
        return
    pnl_df = pd.DataFrame(analytics["positions"])
    cols = [
        "ticker", "current_price", "current_value", "cost_basis", "pnl", "pnl_pct",
        "fifty_two_week_high", "fifty_two_week_low", "avg_volume",
    ]
    pnl_df = pnl_df.reindex(columns=cols)

    def _color_pnl(val):
        if val is None or pd.isna(val):
            return ""
        if val > 0:
            return "color: #16a34a"   # verde
        if val < 0:
            return "color: #dc2626"   # rosso
        return ""

    number_formats = {
        "current_price": "{:,.2f}",
        "current_value": "{:,.2f}",
        "cost_basis": "{:,.2f}",
        "pnl": "{:,.2f}",
        "pnl_pct": "{:.2f}%",
        "fifty_two_week_high": "{:,.2f}",
        "fifty_two_week_low": "{:,.2f}",
        "avg_volume": "{:,.0f}",
    }
    styled = (
        pnl_df.style
        .format(number_formats, na_rep="—")
        .map(_color_pnl, subset=["pnl", "pnl_pct"])
    )

    st.dataframe(
        styled,
        use_container_width=True, hide_index=True,
        column_config={
            "ticker": st.column_config.Column("Ticker", help="Simbolo di borsa del titolo."),
            "current_price": st.column_config.Column("Prezzo attuale", help="Ultimo prezzo di mercato del titolo."),
            "current_value": st.column_config.Column("Valore attuale", help="Valore di mercato corrente: quantita' x prezzo attuale."),
            "cost_basis": st.column_config.Column("Costo", help="Capitale investito: quantita' x prezzo medio di carico."),
            "pnl": st.column_config.Column("P/L", help="Guadagno o perdita: valore attuale meno costo."),
            "pnl_pct": st.column_config.Column("P/L %", help="Variazione percentuale rispetto al costo investito."),
            "fifty_two_week_high": st.column_config.Column("Max 1Y", help="Prezzo massimo negli ultimi 12 mesi (massimo a 52 settimane)."),
            "fifty_two_week_low": st.column_config.Column("Min 1Y", help="Prezzo minimo negli ultimi 12 mesi (minimo a 52 settimane)."),
            "avg_volume": st.column_config.Column("Volume medio", help="Numero medio di azioni scambiate al giorno (media sull'ultimo trimestre circa)."),
        },
    )


def render_charts(positions, analytics):
    pie_df = pd.DataFrame(positions)
    pie_df["cost_basis"] = (
        pie_df["quantity"].astype(float) * pie_df["average_price"].astype(float)
    )

    left, right = st.columns([1, 2])
    with left:
        fig_pie = px.pie(pie_df, names="ticker", values="cost_basis", title="Allocazione per costo")
        fig_pie.update_layout(height=320, margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_pie, use_container_width=True)
    with right:
        if analytics and analytics["history"]["dates"]:
            window = st.radio(
                "Finestra grafico", ["1M", "3M", "6M", "1Y"], index=3,
                horizontal=True, key="chart_window", label_visibility="collapsed",
            )
            n_map = {"1M": 21, "3M": 63, "6M": 126, "1Y": None}
            hist = analytics["history"]
            hist_df = pd.DataFrame(hist["series"], index=pd.to_datetime(hist["dates"]))
            hist_df = hist_df.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
            n = n_map[window]
            if n is not None:
                hist_df = hist_df.tail(n)
            if not hist_df.empty and hist_df.shape[1] > 0:
                fig_line = px.line(hist_df, title=f"Andamento prezzi ({window})")
                fig_line.update_layout(height=320, margin=dict(t=40, b=0, l=0, r=0), legend_title_text="")
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Andamento prezzi non disponibile al momento.")
        else:
            st.info("Andamento prezzi non disponibile al momento.")

    metrics = analytics.get("metrics") if analytics else None
    if metrics and metrics["per_ticker"]:
        st.markdown("**Metriche quantitative**")
        m1, m2 = st.columns(2)
        m1.metric("Volatilita' annualizzata", f"{metrics['annualized_volatility'] * 100:.2f}%",
                  help="Oscillazione annualizzata dei rendimenti pesati: piu' alta = piu' rischio.")
        m2.metric("Rendimento 1Y (portafoglio)", f"{metrics['portfolio_return_1y'] * 100:.2f}%",
                  help="Rendimento a 12 mesi, media dei rendimenti pesata per i pesi di mercato.")
        tech_df = pd.DataFrame(metrics["per_ticker"]).reindex(columns=[
            "ticker", "weight_pct",
            "return_1m_pct", "return_3m_pct", "return_6m_pct", "return_1y_pct",
            "pe_ratio", "dividend_yield",
        ])
        ret_cols = ["return_1m_pct", "return_3m_pct", "return_6m_pct", "return_1y_pct"]
        tech_styled = (
            tech_df.style
            .format({
                "weight_pct": "{:.2f}%",
                "return_1m_pct": "{:.2f}%", "return_3m_pct": "{:.2f}%",
                "return_6m_pct": "{:.2f}%", "return_1y_pct": "{:.2f}%",
                "pe_ratio": "{:.2f}", "dividend_yield": "{:.2f}%",
            }, na_rep="—")
            .map(_color_pnl, subset=ret_cols)
        )
        st.dataframe(
            tech_styled, use_container_width=True, hide_index=True,
            column_config={
                "ticker": st.column_config.Column("Ticker", help="Simbolo di borsa del titolo."),
                "weight_pct": st.column_config.Column("Peso", help="Quota del titolo sul valore di mercato totale del portafoglio."),
                "return_1m_pct": st.column_config.Column("Rend. 1M", help="Rendimento sull'ultimo mese (circa 21 sedute di borsa)."),
                "return_3m_pct": st.column_config.Column("Rend. 3M", help="Rendimento sull'ultimo trimestre (circa 63 sedute)."),
                "return_6m_pct": st.column_config.Column("Rend. 6M", help="Rendimento sugli ultimi 6 mesi (circa 126 sedute)."),
                "return_1y_pct": st.column_config.Column("Rend. 1Y", help="Rendimento sugli ultimi 12 mesi."),
                "pe_ratio": st.column_config.Column("P/E", help="Prezzo/utili (trailing). Vuoto se non disponibile o utili negativi."),
                "dividend_yield": st.column_config.Column("Div. Yield", help="Dividendo annuo / prezzo attuale (rapporto a oggi). Lo storico dei pagamenti è nella sezione Dividendi del titolo. Vuoto se il titolo non paga dividendi."),
            },
        )


def add_position_form(portfolio_id):
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
                "purchase_date": datetime.combine(purchase_date, datetime.min.time()).isoformat(),
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


def update_position_form(portfolio_id, positions):
    labels = {f"{p['ticker']} - {p['id'][:8]}": p for p in positions}
    choice = st.selectbox("Posizione da modificare", list(labels.keys()), key="update_select")
    pos = labels[choice]

    try:
        current_date = datetime.fromisoformat(pos["purchase_date"].replace("Z", "+00:00")).date()
    except (ValueError, AttributeError, KeyError):
        current_date = datetime.today().date()

    with st.form("update_position_form"):
        st.text_input("Ticker (non modificabile)", value=pos["ticker"], disabled=True)
        col1, col2 = st.columns(2)
        quantity = col1.number_input("Quantita'", min_value=0.0, step=1.0, value=float(pos["quantity"]))
        average_price = col2.number_input("Prezzo medio", min_value=0.0, step=1.0, value=float(pos["average_price"]))
        purchase_date = st.date_input("Data acquisto", value=current_date)
        col3, col4 = st.columns(2)
        sector = col3.text_input("Settore", value=pos.get("sector") or "")
        market = col4.text_input("Mercato", value=pos.get("market") or "")
        submitted = st.form_submit_button("Salva modifiche", use_container_width=True)
    if submitted:
        if quantity <= 0 or average_price <= 0:
            st.warning("Quantita' e prezzo medio devono essere maggiori di zero.")
        else:
            payload = {
                "quantity": quantity,
                "average_price": average_price,
                "purchase_date": datetime.combine(purchase_date, datetime.min.time()).isoformat(),
                "sector": sector or None,
                "market": market or None,
            }
            response = authed_call("PATCH", f"/positions/{pos['id']}", json=payload)
            if response is not None and response.status_code == 200:
                st.toast("Posizione aggiornata", icon="✏️")
                st.rerun()
            elif response is not None:
                st.error(f"Errore ({response.status_code}).")


def remove_position_control(positions):
    labels = {
        f"{p['ticker']} - qta {float(p['quantity']):g} - {p['id'][:8]}": p["id"]
        for p in positions
    }
    choice = st.selectbox("Posizione da rimuovere", list(labels.keys()), key="remove_position")
    if st.button("Rimuovi", use_container_width=True):
        response = authed_call("DELETE", f"/positions/{labels[choice]}")
        if response is not None and response.status_code == 204:
            st.toast("Posizione rimossa", icon="🗑️")
            st.rerun()
        elif response is not None:
            st.error(f"Errore ({response.status_code}).")




def close_portfolio_control(portfolio):
    st.caption(
        f"Eliminerai definitivamente '{portfolio['name']}' con tutte le sue posizioni e report. Irreversibile."
    )
    confirm = st.checkbox("Confermo l'eliminazione", key="confirm_delete")
    if st.button("Elimina definitivamente", disabled=not confirm, use_container_width=True):
        response = authed_call("DELETE", f"/portfolios/{portfolio['id']}")
        if response is not None and response.status_code == 204:
            st.session_state.pop("selected_portfolio", None)
            st.toast("Portafoglio eliminato", icon="🗑️")
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
        st.warning(f"Limite di richieste superato per: {', '.join(rate_limited)}. Riprova tra un minuto.")
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


def render_reports(portfolio_id):
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
            st.caption(f"Generato il {_format_timestamp(report['generated_at'])}")
            st.markdown(report["report_text"])


def render_portfolio_detail(portfolio):
    st.subheader(portfolio["name"])
    if portfolio.get("description"):
        st.caption(portfolio["description"])

    positions = get_positions(portfolio["id"])
    analytics = fetch_analytics(portfolio["id"]) if positions else None

    render_summary(positions, analytics)

    bar = st.columns(4)
    with bar[0].popover("➕ Aggiungi", use_container_width=True):
        add_position_form(portfolio["id"])
        st.divider()
        import_positions_control(portfolio["id"])
    with bar[1].popover("✏️ Modifica", use_container_width=True, disabled=not positions):
        if positions:
            update_position_form(portfolio["id"], positions)
    with bar[2].popover("🗑️ Rimuovi", use_container_width=True, disabled=not positions):
        if positions:
            remove_position_control(positions)
    with bar[3].popover("⚠️ Chiudi", use_container_width=True):
        close_portfolio_control(portfolio)

    a1, a2 = st.columns(2)
    if a1.button("⬇️ Scarica Dati Mercato", use_container_width=True, disabled=not positions):
        fetch_market_data([p["ticker"] for p in positions])
    if a2.button("🤖 Genera Report AI", use_container_width=True):
        generate_report(portfolio["id"])

    tab_charts, tab_pos, tab_ticker, tab_reports = st.tabs(
        ["Grafici & metriche", "Posizioni & P/L", "Analisi titolo", "Report portfolio"]
    )
    with tab_charts:
        if positions:
            render_charts(positions, analytics)
        else:
            st.info("Aggiungi una posizione per vedere i grafici.")
    with tab_pos:
        render_positions_table(positions)
        if analytics:
            render_pnl_table(analytics)
    with tab_ticker:
        render_ticker_ai(positions)
    with tab_reports:
        render_reports(portfolio["id"])


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

def explain_ticker(ticker):
    with st.spinner(f"Analizzo l'andamento di {ticker}..."):
        response = authed_call("POST", f"/ai/explain/{ticker}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite superato (max 3/min) sulle analisi AI. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.session_state[f"ai_explain_{ticker}"] = result["result"]["analysis"]
    elif result and result.get("status") == "FAILURE":
        st.error(f"Analisi fallita: {result.get('result')}")
    else:
        st.warning("L'analisi sta impiegando piu' del previsto; riprova tra poco.")

def suggest_peers(ticker):
    with st.spinner(f"Cerco titoli simili a {ticker}..."):
        response = authed_call("POST", f"/ai/peers/{ticker}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite superato (max 3/min) sulle analisi AI. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.session_state[f"ai_peers_{ticker}"] = result["result"]
    elif result and result.get("status") == "FAILURE":
        st.error(f"Ricerca fallita: {result.get('result')}")
    else:
        st.warning("La ricerca sta impiegando piu' del previsto; riprova tra poco.")


def render_ticker_ai(positions):
    if not positions:
        st.info("Aggiungi una posizione per analizzare un titolo.")
        return
    tickers = sorted({p["ticker"] for p in positions})
    ticker = st.selectbox("Titolo da analizzare", tickers, key="ai_ticker_select")
    c1, c2, c3, c4 = st.columns(4)
    d1, d2, d3, d4 = st.columns(4)
    if d1.button("💰 Dividendi", use_container_width=True, key="div_btn"):
        fetch_dividends_data(ticker)
    if d2.button("🎯 Target analisti", use_container_width=True, key="analyst_btn"):
        fetch_analyst_data(ticker)
    if c1.button("🔍 Spiega andamento", use_container_width=True, key="explain_btn"):
        explain_ticker(ticker)
    if c2.button("📰 Riassunto notizie", use_container_width=True, key="news_btn"):
        summarize_news(ticker)
    if c3.button("🏷️ Titoli simili", use_container_width=True, key="peers_btn"):
        suggest_peers(ticker)
    if c4.button("🧩 Composizione ETF", use_container_width=True, key="holdings_btn"):
        fetch_holdings(ticker)

    explanation = st.session_state.get(f"ai_explain_{ticker}")
    if explanation:
        st.markdown("**Andamento**")
        with st.container(border=True):
            st.markdown(explanation)

    news = st.session_state.get(f"ai_news_{ticker}")
    if news:
        st.markdown("**Notizie recenti**")
        with st.container(border=True):
            st.markdown(news)

    peers = st.session_state.get(f"ai_peers_{ticker}")
    if peers:
        st.markdown(f"**Titoli simili per settore** ({peers.get('sector') or 'n/d'})")
        if peers.get("message"):
            st.info(peers["message"])
        elif peers.get("peers"):
            peers_df = pd.DataFrame(peers["peers"]).reindex(
                columns=["ticker", "name", "sector", "current_price", "reason"]
            )
            st.dataframe(
                peers_df, use_container_width=True, hide_index=True,
                column_config={
                    "ticker": st.column_config.Column("Ticker"),
                    "name": st.column_config.Column("Nome"),
                    "sector": st.column_config.Column("Settore"),
                    "current_price": st.column_config.NumberColumn("Prezzo attuale"),
                    "reason": st.column_config.Column("Perché simile", help="Motivazione generata dall'AI, indicativa."),
                },
            )
            st.caption("Elenco puramente informativo, non è consulenza finanziaria. "
                       "I ticker proposti dall'AI sono stati verificati su dati di mercato reali.")
        else:
            st.info("Nessun titolo simile valido trovato.")

    holdings = st.session_state.get(f"ai_holdings_{ticker}")
    if holdings:
        title = f"**Composizione — top holding** {holdings.get('name') or ''}".strip()
        st.markdown(title)
        if holdings.get("message"):
            st.info(holdings["message"])
        elif holdings.get("holdings"):
            hold_df = pd.DataFrame(holdings["holdings"]).reindex(columns=["ticker", "name", "weight_pct"])
            hold_styled = hold_df.style.format({"weight_pct": "{:.2f}%"}, na_rep="—")
            st.dataframe(
                hold_styled, use_container_width=True, hide_index=True,
                column_config={
                    "ticker": st.column_config.Column("Ticker", help="Simbolo del titolo dentro il fondo."),
                    "name": st.column_config.Column("Nome"),
                    "weight_pct": st.column_config.Column("Peso", help="Peso sul fondo (solo i principali titoli, non l'intero paniere)."),
                },
            )
            st.caption("Solo i principali titoli esposti dal provider, non l'intero paniere dell'ETF.")
        else:
            st.info("Composizione non disponibile.")
    div = st.session_state.get(f"ai_div_{ticker}")
    if div:
        st.subheader(
            "Dividendi pagati per azione",
            help="Importi effettivamente distribuiti per azione nel tempo. Diverso dal *dividend yield* "
                 "in tabella, che è il rapporto dividendo annuo / prezzo attuale (una percentuale a oggi).",
        )
        if div.get("message"):
            st.info(div["message"])
        elif div.get("dividends"):
            div_df = pd.DataFrame(div["dividends"])
            div_df["date"] = pd.to_datetime(div_df["date"])
            fig_div = px.bar(div_df, x="date", y="amount", title=f"Dividendi {ticker} (per azione)")
            fig_div.update_layout(height=320, margin=dict(t=40, b=0, l=0, r=0),
                                  xaxis_title="", yaxis_title="importo per azione")
            st.plotly_chart(fig_div, use_container_width=True)
        else:
            st.info("Nessuno storico dividendi disponibile.")

    analyst = st.session_state.get(f"ai_analyst_{ticker}")
    if analyst:
        st.subheader(
            "Target di prezzo degli analisti",
            help="Prezzi obiettivo a 12 mesi stimati dagli analisti (minimo, medio, massimo) e consenso di "
                 "raccomandazione. L'upside è la distanza % tra target medio e prezzo attuale. Sono opinioni di "
                 "terzi, non una previsione garantita né una raccomandazione.",
        )
        if analyst.get("message"):
            st.info(analyst["message"])
        elif analyst.get("analyst"):
            a = analyst["analyst"]
            cols = st.columns(4)
            cols[0].metric("Prezzo attuale", f"{a['current_price']:,.2f}" if a["current_price"] is not None else "—")
            cols[1].metric(
                "Target medio", f"{a['target_mean']:,.2f}" if a["target_mean"] is not None else "—",
                delta=f"{a['upside_pct']:+.2f}%" if a["upside_pct"] is not None else None,
                help="Distanza tra target medio e prezzo attuale.",
            )
            cols[2].metric("Consenso", (a["recommendation"] or "—").replace("_", " ").title())
            cols[3].metric("N. analisti", a["num_analysts"] if a["num_analysts"] is not None else "—")

            if a["target_low"] is not None and a["target_high"] is not None and a["current_price"] is not None:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=[a["target_low"], a["target_high"]], y=[0, 0], mode="lines",
                    line=dict(width=8, color="#64748b"), showlegend=False, hoverinfo="skip"))
                fig.add_trace(go.Scatter(
                    x=[a["target_low"], a["target_mean"], a["target_high"]], y=[0, 0, 0],
                    mode="markers+text", text=["Low", "Medio", "High"], textposition="top center",
                    marker=dict(size=11, color="#64748b"), showlegend=False,
                    hovertemplate="%{x:.2f}<extra></extra>"))
                fig.add_trace(go.Scatter(
                    x=[a["current_price"]], y=[0], mode="markers+text", text=["Prezzo attuale"],
                    textposition="bottom center", marker=dict(size=15, symbol="diamond", color="#16a34a"),
                    showlegend=False, hovertemplate="Prezzo attuale: %{x:.2f}<extra></extra>"))
                fig.update_layout(height=180, margin=dict(t=20, b=20, l=0, r=0),
                                  xaxis_title="prezzo", yaxis=dict(visible=False, range=[-1, 1]))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Dati analisti non disponibili.")

def fetch_dividends_data(ticker):
    with st.spinner(f"Recupero i dividendi di {ticker}..."):
        response = authed_call("POST", f"/market/dividends/{ticker}")
        if response is None:
            return
        if response.status_code == 429:
            st.warning("Limite di richieste superato. Riprova tra un minuto.")
            return
        if response.status_code != 202:
            st.error(f"Errore ({response.status_code}).")
            return
        result = poll_task(response.json()["task_id"])
    if result and result.get("status") == "SUCCESS":
        st.session_state[f"ai_div_{ticker}"] = result["result"]
    elif result and result.get("status") == "FAILURE":
        st.error(f"Recupero fallito: {result.get('result')}")
    else:
        st.warning("Il recupero sta impiegando piu' del previsto; riprova tra poco.")


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