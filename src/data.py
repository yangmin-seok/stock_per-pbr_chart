import pandas as pd
from datetime import datetime, timedelta
import time
import requests
import re
from io import StringIO
from pykrx import stock
from .auth import install_pykrx_session_wrappers
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
