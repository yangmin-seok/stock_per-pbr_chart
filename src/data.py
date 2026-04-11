import pandas as pd
from datetime import datetime, timedelta
import time
import requests
import re
from io import StringIO
from pykrx import stock
from .auth import install_pykrx_session_wrappers
from .storage import load_wisereport_financials, save_wisereport_financials
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

def fetch_sector_classifications(date_str: str, market="KOSPI"):
    """특정 일자, 시장의 종목별 섹터(업종) 정보 리턴"""
    df = stock.get_market_sector_classifications(date_str, market)
    time.sleep(0.5)
    return df

def fetch_ytd_returns(target_date: str, market="KOSPI"):
    """연초(1월 첫 거래일 느낌) 부터 target_date까지의 등락률 리턴"""
    # pykrx의 get_market_price_change_by_ticker는 시작일과 종료일 필요
    start_year = target_date[:4]
    start_date = f"{start_year}0102" # 1월 2일 또는 첫 거래일 기준. pykrx가 알아서 가까운 영업일로 처리하기도 함.
    df = stock.get_market_price_change_by_ticker(start_date, target_date, market=market)
    time.sleep(0.5)
    return df


# KRX 공통 영업일 프록시 (지수 API 대체)
_KRX_CALENDAR_TICKER = "005930"


def get_krx_trading_day_pair_for_daily_return(target_date: str):
    """전일 대비(1거래일) 수익률용: (직전 영업일, 마지막 영업일) YYYYMMDD.

    마지막 영업일은 **삼성전자 OHLCV 기준** target_date 이하 중 가장 늦은 장 세션이다.
    장 데이터가 target_date보다 늦게 반영되면 last < target가 되며, 이때도 구간을
    (직전날→last)로 두어 pykrx 등락률이 여러 거래일로 누적되지 않게 한다.
    """
    try:
        dt_end = pd.Timestamp(datetime.strptime(target_date, "%Y%m%d"))
    except (TypeError, ValueError):
        return None, None
    start = (dt_end - pd.Timedelta(days=21)).strftime("%Y%m%d")
    try:
        cal = stock.get_market_ohlcv_by_date(start, target_date, _KRX_CALENDAR_TICKER)
    except Exception:
        return None, None
    time.sleep(0.5)
    if cal is None or cal.empty:
        return None, None
    idx = pd.DatetimeIndex(pd.to_datetime(cal.index)).tz_localize(None).normalize()
    end_norm = dt_end.normalize()
    valid = idx[idx <= end_norm]
    if len(valid) < 2:
        return None, None
    prev_day = valid[-2].strftime("%Y%m%d")
    last_day = valid[-1].strftime("%Y%m%d")
    return prev_day, last_day


SECTOR_HEATMAP_RETURN_COLUMNS = ("RET_1D", "RET_1M", "RET_3M", "YTD(%)")


def fetch_multi_horizon_returns(target_date: str, market: str = "KOSPI") -> pd.DataFrame:
    """티커 인덱스. 컬럼: RET_1D, RET_1M, RET_3M, YTD(%) (등락률 %, 부분 실패 시 NaN)."""
    series_parts = []
    dt = pd.Timestamp(datetime.strptime(target_date, "%Y%m%d"))

    # 전일 대비: 기간 조회(get_market_price_change_by_ticker) 등락률은 구간 누적에 가깝게 나올 수 있어,
    # 해당 영업일 스냅샷의 등락률(get_market_ohlcv_by_ticker)을 사용한다.
    _, last_td = get_krx_trading_day_pair_for_daily_return(target_date)
    if last_td:
        try:
            d = stock.get_market_ohlcv_by_ticker(last_td, market=market, alternative=False)
            time.sleep(0.5)
            if not d.empty and "등락률" in d.columns:
                r1d = pd.to_numeric(d["등락률"], errors="coerce").rename("RET_1D")
                series_parts.append(r1d)
        except Exception:
            pass

    for col_name, months in (("RET_1M", 1), ("RET_3M", 3)):
        start = (dt - pd.DateOffset(months=months)).strftime("%Y%m%d")
        try:
            d = stock.get_market_price_change_by_ticker(start, target_date, market=market)
            time.sleep(0.5)
            if not d.empty and "등락률" in d.columns:
                series_parts.append(d["등락률"].rename(col_name))
        except Exception:
            pass

    try:
        d = stock.get_market_price_change_by_ticker(
            f"{target_date[:4]}0102", target_date, market=market
        )
        time.sleep(0.5)
        if not d.empty and "등락률" in d.columns:
            series_parts.append(d["등락률"].rename("YTD(%)"))
    except Exception:
        pass

    if not series_parts:
        return pd.DataFrame(columns=list(SECTOR_HEATMAP_RETURN_COLUMNS))

    out = pd.concat(series_parts, axis=1)
    for c in SECTOR_HEATMAP_RETURN_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA
    return out[list(SECTOR_HEATMAP_RETURN_COLUMNS)]

def fetch_detailed_financials(ticker: str) -> pd.DataFrame:
    """FnGuide Ajax 엔드포인트를 우회하여 상세 재무제표 테이블을 가져옵니다."""
    url = f'https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={ticker}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        # 1. 초기 로드 페이지에서 encparam 파라미터 추출
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        
        match = re.search(r"encparam:\s*'(.+?)'", res.text)
        if not match:
            return pd.DataFrame()
            
        encparam = match.group(1)
        
        # 2. Ajax 통신으로 실제 데이터 요청
        ajax_url = f"https://navercomp.wisereport.co.kr/v2/company/ajax/cF1001.aspx?cmp_cd={ticker}&fin_typ=0&freq_typ=Y&encparam={encparam}&id="
        headers['Referer'] = url
        ajax_res = requests.get(ajax_url, headers=headers)
        ajax_res.raise_for_status()
        
        # 3. 데이터프레임 파싱
        dfs = pd.read_html(StringIO(ajax_res.text))
        if len(dfs) < 2:
            return pd.DataFrame()
            
        df = dfs[1]
        
        # 컬럼 전처리: MultiIndex의 경우 Level 1 (날짜/구분) 값만 추출
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = [c[1] if len(c) > 1 else c[0] for c in df.columns]
        
        # 첫 번째 열을 인덱스로 설정 ('매출액', '영업이익' 등)
        df.set_index(df.columns[0], inplace=True)
        df.index.name = '항목'
        
        # 중복 인덱스가 있을 수 있으므로 첫 번째 것만 유지
        df = df[~df.index.duplicated(keep='first')]
        
        # 처음에 요청하셨던 19가지 핵심 지표만 필터링
        target_indices = [
            '매출액', '영업이익', '당기순이익', '영업활동현금흐름', 'CAPEX', 'FCF', 
            '영업이익률', '순이익률', 'ROE(%)', 'ROA(%)', '부채비율', '자본유보율', 
            'EPS(원)', 'PER(배)', 'BPS(원)', 'PBR(배)', '현금DPS(원)', '현금배당수익률', '현금배당성향(%)'
        ]
        
        # DataFrame에 존재하는 인덱스만 교집합으로 순서 맞춰 가져오기
        available_indices = [idx for idx in target_indices if idx in df.index]
        df_filtered = df.loc[available_indices]
        
        return df_filtered
        
    except Exception as e:
        import logging
        logging.error(f"Financial fetch error for {ticker}: {e}")
        return pd.DataFrame()


def get_detailed_financials(ticker: str) -> pd.DataFrame:
    """DB에 캐시된 WiseReport 실적이 있으면 사용하고, 없으면 네트워크에서 받아 저장 후 반환합니다."""
    df = load_wisereport_financials(ticker)
    if not df.empty:
        return df
    df = fetch_detailed_financials(ticker)
    if not df.empty:
        save_wisereport_financials(ticker, df)
    return df
