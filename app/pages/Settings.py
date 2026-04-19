from __future__ import annotations

import os

import streamlit as st

from app.ui import apply_page_config, sidebar_footer
from backend.config import get_settings
from backend.watchlist import get_app_setting, set_app_setting


apply_page_config("Settings | Indian Stock AI Agent")

st.sidebar.title("Indian Stock AI Agent")
st.sidebar.page_link("main.py", label="Dashboard")
st.sidebar.page_link("pages/Scanner.py", label="Scanner")
st.sidebar.page_link("pages/Watchlist.py", label="Watchlist")
st.sidebar.page_link("pages/Settings.py", label="Settings")
sidebar_footer()

settings = get_settings()

st.title("Settings")
st.caption("Local preferences are saved in SQLite. Secrets should also be kept in `.env` or Streamlit Cloud secrets.")

with st.form("settings_form"):
    openai_key = st.text_input(
        "OpenAI API key",
        value=get_app_setting("OPENAI_API_KEY", settings.openai_api_key),
        type="password",
        help="Used only in this local app session unless you also update .env.",
    )
    default_watchlist = st.text_input(
        "Default watchlist",
        value=get_app_setting("DEFAULT_WATCHLIST", settings.default_watchlist),
        help="Comma-separated NSE symbols.",
    )
    refresh_interval = st.number_input(
        "Refresh interval",
        min_value=30,
        max_value=3600,
        value=int(get_app_setting("REFRESH_INTERVAL_SECONDS", str(settings.refresh_interval_seconds))),
        step=30,
        help="Seconds between manual refresh cycles or future scheduled jobs.",
    )
    telegram_token = st.text_input("Telegram bot token", value=get_app_setting("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token), type="password")
    telegram_chat = st.text_input("Telegram chat ID", value=get_app_setting("TELEGRAM_CHAT_ID", settings.telegram_chat_id))
    twelve_data_key = st.text_input(
        "Twelve Data API key",
        value=get_app_setting("TWELVE_DATA_API_KEY", settings.twelve_data_api_key),
        type="password",
        help="Optional fallback market-data provider for NSE symbols.",
    )
    alpha_vantage_key = st.text_input(
        "Alpha Vantage API key",
        value=get_app_setting("ALPHA_VANTAGE_API_KEY", settings.alpha_vantage_api_key),
        type="password",
        help="Optional fallback market-data provider, usually through BSE symbols.",
    )
    submitted = st.form_submit_button("Save Settings", type="primary")

if submitted:
    set_app_setting("OPENAI_API_KEY", openai_key)
    set_app_setting("DEFAULT_WATCHLIST", default_watchlist)
    set_app_setting("REFRESH_INTERVAL_SECONDS", str(refresh_interval))
    set_app_setting("TELEGRAM_BOT_TOKEN", telegram_token)
    set_app_setting("TELEGRAM_CHAT_ID", telegram_chat)
    set_app_setting("TWELVE_DATA_API_KEY", twelve_data_key)
    set_app_setting("ALPHA_VANTAGE_API_KEY", alpha_vantage_key)
    os.environ["OPENAI_API_KEY"] = openai_key
    os.environ["TWELVE_DATA_API_KEY"] = twelve_data_key
    os.environ["ALPHA_VANTAGE_API_KEY"] = alpha_vantage_key
    st.success("Settings saved.")

st.markdown("### Deployment notes")
st.write("- Streamlit Cloud: add these values in app secrets or environment variables.")
st.write("- Render: set the same variables in the service Environment tab.")
st.write("- Keep API keys out of commits. The included `.env` is for local placeholders only.")
