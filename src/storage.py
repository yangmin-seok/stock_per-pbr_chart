import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pytz import timezone

DB_PATH = "stock_data.sqlite"

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def get_latest_market_date():
    """한국장 마감 시간(오후 3시 30분) 기준으로 최신 영업일(추정)을 반환.
    정확히는 휴일 처리 로직이 더 필요할 수 있으나 단순화를 위해 오늘/어제 반환."""
    kst = timezone('Asia/Seoul')
    now = datetime.now(kst)
    
    # 15:30분 이후면 오늘, 아니면 어제로 간주
    if now.hour > 15 or (now.hour == 15 and now.minute >= 30):
        target_date = now
    else:
        target_date = now - timedelta(days=1)
        
    # 주말 처리 (토요일은 금요일로, 일요일은 금요일로)
    if target_date.weekday() == 5: # 토
        target_date -= timedelta(days=1)
    elif target_date.weekday() == 6: # 일
        target_date -= timedelta(days=2)
        
    return target_date.strftime("%Y%m%d")

def is_update_needed(ticker: str) -> bool:
    """해당 티커의 데이터가 최신 상태인지 확인 (1일 1회 업데이트 로직)"""
    if not os.path.exists(DB_PATH):
        return True
        
    target_date = get_latest_market_date()
    
    with get_db_connection() as conn:
        try:
            # 해당 종목의 가장 최신 날짜 조회
            query = f"SELECT MAX(날짜) as max_date FROM ticker_{ticker}"
            df = pd.read_sql(query, conn)
            max_date = df['max_date'].iloc[0]
            
            if pd.isna(max_date):
                return True
                
            # 날짜 형식을 맞춰서 비교 (DB에 %Y-%m-%d 등 형태로 저장되었다면 변환)
            max_date_str = pd.to_datetime(max_date).strftime("%Y%m%d")
            
            if max_date_str < target_date:
                return True
            return False
            
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            # 테이블이 존재하지 않거나 오류시 업데이트 필요
            return True

def save_ticker_data(ticker: str, df: pd.DataFrame):
    """
    티커 데이터를 SQLite에 저장/갱신합니다.
    """
    with get_db_connection() as conn:
        df.to_sql(f"ticker_{ticker}", conn, if_exists='replace', index=True, index_label='날짜')

def load_ticker_data(ticker: str) -> pd.DataFrame:
    """
    SQLite에서 티커 데이터를 불러옵니다.
    """
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
        
    with get_db_connection() as conn:
        try:
            df = pd.read_sql(f"SELECT * FROM ticker_{ticker}", conn, index_col='날짜', parse_dates=['날짜'])
            return df
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            return pd.DataFrame()


def _ensure_wisereport_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wisereport_fin_meta (
            ticker TEXT PRIMARY KEY,
            refreshed_at TEXT NOT NULL
        )
        """
    )


def is_wisereport_financials_stale(ticker: str, max_age_days: int = 7) -> bool:
    """WiseReport 기업실적 캐시가 없거나 max_age_days보다 오래됐으면 True."""
    if not os.path.exists(DB_PATH):
        return True
    with get_db_connection() as conn:
        try:
            _ensure_wisereport_meta_table(conn)
            cur = conn.execute(
                "SELECT refreshed_at FROM wisereport_fin_meta WHERE ticker = ?",
                (ticker,),
            )
            row = cur.fetchone()
            if row is None:
                return True
            refreshed = datetime.fromisoformat(row[0])
            if datetime.now() - refreshed > timedelta(days=max_age_days):
                return True
            return False
        except (sqlite3.OperationalError, ValueError, TypeError, Exception):
            return True


def save_wisereport_financials(ticker: str, df: pd.DataFrame) -> None:
    """WiseReport 연간 실적 표(항목×기간)를 SQLite에 저장하고 메타 갱신 시각을 기록합니다."""
    if df.empty:
        return
    with get_db_connection() as conn:
        _ensure_wisereport_meta_table(conn)
        out = df.reset_index()
        out.to_sql(f"fin_wisereport_{ticker}", conn, if_exists="replace", index=False)
        conn.execute(
            "INSERT OR REPLACE INTO wisereport_fin_meta (ticker, refreshed_at) VALUES (?, ?)",
            (ticker, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


def load_wisereport_financials(ticker: str) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with get_db_connection() as conn:
        try:
            return pd.read_sql(
                f"SELECT * FROM fin_wisereport_{ticker}",
                conn,
                index_col="항목",
            )
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            return pd.DataFrame()

def save_market_list(df: pd.DataFrame, market="KOSPI"):
    with get_db_connection() as conn:
        df.to_sql(f"market_list_{market}", conn, if_exists='replace', index=True, index_label='티커')

def load_market_list(market="KOSPI") -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with get_db_connection() as conn:
        try:
            return pd.read_sql(f"SELECT * FROM market_list_{market}", conn, index_col='티커')
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            return pd.DataFrame()

# --- Global Market / Macro Storage ---

def save_market_scatter_data(market: str, df: pd.DataFrame, target_date: str):
    with get_db_connection() as conn:
        df['target_date'] = target_date
        df.to_sql(f"market_scatter_{market}", conn, if_exists='replace', index=True, index_label='티커')

def load_market_scatter_data(market: str, target_date: str) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with get_db_connection() as conn:
        try:
            df = pd.read_sql(f"SELECT * FROM market_scatter_{market} WHERE target_date='{target_date}'", conn, index_col='티커')
            if not df.empty:
                df.drop(columns=['target_date'], inplace=True)
            return df
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            return pd.DataFrame()

def save_sector_ytd_data(market: str, df: pd.DataFrame, target_date: str):
    with get_db_connection() as conn:
        df['target_date'] = target_date
        df.to_sql(f"sector_ytd_{market}", conn, if_exists='replace', index=True, index_label='티커')

def load_sector_ytd_data(market: str, target_date: str) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with get_db_connection() as conn:
        try:
            df = pd.read_sql(f"SELECT * FROM sector_ytd_{market} WHERE target_date='{target_date}'", conn, index_col='티커')
            if not df.empty:
                df.drop(columns=['target_date'], inplace=True)
            return df
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            return pd.DataFrame()

def save_macro_data(symbol: str, df: pd.DataFrame, max_date: str):
    with get_db_connection() as conn:
        table_name = f"macro_{symbol.replace('^', '').replace('=', '_').replace('/', '_')}"
        df.to_sql(table_name, conn, if_exists='replace', index=True, index_label='Date')

def load_macro_data(symbol: str) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with get_db_connection() as conn:
        table_name = f"macro_{symbol.replace('^', '').replace('=', '_').replace('/', '_')}"
        try:
            df = pd.read_sql(f"SELECT * FROM {table_name}", conn, index_col='Date', parse_dates=['Date'])
            return df
        except (sqlite3.OperationalError, pd.errors.DatabaseError, Exception):
            return pd.DataFrame()

