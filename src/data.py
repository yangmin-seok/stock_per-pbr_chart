import pandas as pd
from datetime import datetime, timedelta
from pykrx import stock
from .auth import install_pykrx_session_wrappers
import time

# 적용
install_pykrx_session_wrappers()

def get_target_date_range(years=10):
    """최근 'years' 년간의 시작일과 종료일 문자열 반환 (YYYYMMDD 형식)"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    return start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")

def fetch_tickers(date_str: str, market="KOSPI"):
    """특정 일자, 시장의 티커 목록 반환"""
    return stock.get_market_ticker_list(date_str, market=market)

def get_ticker_name(ticker: str):
    return stock.get_market_ticker_name(ticker)

def fetch_ohlcv(ticker: str, start_date: str, end_date: str):
    """OHLCV 리턴 (Date index)"""
    df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
    time.sleep(0.5) # 과부하 방지
    return df

def fetch_fundamentals(ticker: str, start_date: str, end_date: str):
    """펀더멘탈 (BPS, PER, PBR, EPS, DIV, DPS) 리턴 (Date index)"""
    df = stock.get_market_fundamental_by_date(start_date, end_date, ticker)
    time.sleep(0.5) # 과부하 방지
    return df

def fetch_market_cap(date_str: str, market="KOSPI"):
    """일자별 해당 마켓의 전 종목 시가총액/PER 등 리턴"""
    # 당일 KOSPI 전체 종목 펀더멘털 한 번에 당겨오기 위함
    return stock.get_market_fundamental_by_ticker(date_str, market=market)
