import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st

MACRO_SYMBOLS = {
    "USD/KRW 환율": "KRW=X",
    "국제 금": "GC=F",
    "국제 은": "SI=F",
    "WTI 유가": "CL=F",
    "미국 10년물 국채": "^TNX"
}

US_INDEX_SYMBOLS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC"
}

@st.cache_data(ttl=3600*12)
def fetch_macro_data(symbol: str, years: int = 10) -> pd.DataFrame:
    """
    yfinance를 사용해 매크로 지표 데이터를 가져옵니다.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
    
    if not df.empty:
        # yfinance returns timezone-aware index sometimes depending on the ticker.
        # Make it naive for consistency or just keep date
        df.index = df.index.tz_localize(None)
    
    return df
