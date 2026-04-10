import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
from src.storage import load_macro_data, save_macro_data, get_latest_market_date


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

@st.cache_data(ttl=3600)
def fetch_macro_data(symbol: str, years: int = 10) -> pd.DataFrame:
    """
    yfinance를 사용해 매크로 지표 데이터를 가져옵니다 (SQLite 캐싱 포함).
    """
    target_date = get_latest_market_date()
    df = load_macro_data(symbol)
    
    # DB에 데이터가 없거나 가장 최신인 데이터가 백그라운드 수집 타겟 일자보다 오래된 경우에만 API 호출
    if df.empty or df.index.max().strftime('%Y%m%d') < target_date:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)
        
        ticker = yf.Ticker(symbol)
        fetched_df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
        
        if not fetched_df.empty:
            # yfinance returns timezone-aware index sometimes depending on the ticker.
            fetched_df.index = fetched_df.index.tz_localize(None)
            save_macro_data(symbol, fetched_df, target_date)
            return fetched_df
            
    return df

