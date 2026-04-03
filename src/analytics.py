import pandas as pd

def process_ticker_data(ohlcv_df: pd.DataFrame, fund_df: pd.DataFrame) -> pd.DataFrame:
    """
    일별 종가와 재무 데이터를 결합하여 분석용 데이터프레임 생성.
    """
    # 내부 조인 (같은 날짜의 데이터만 유지)
    df = pd.merge(ohlcv_df, fund_df, left_index=True, right_index=True)
    
    # 누락된 데이터 정리 (필요에 따라 forward fill 고려 가능)
    df = df.dropna(subset=['PER', 'PBR'])
    
    # PER, PBR이 0이거나 음수인 경우(순이익 적자 등) 제외
    df = df[df['PER'] > 0]
    df = df[df['PBR'] > 0]
    
    return df

def calculate_bands(df: pd.DataFrame, window_years=5):
    """
    주어진 데이터 프레임에서 고평가, 저평가 판단을 위한 PER/PBR 통계적 밴드(최저, 평균, 최고) 산출.
    """
    if df.empty:
        return df

    # 일별 BPS와 EPS가 존재함
    # 종가 / PER = EPS, 종가 / PBR = BPS (이론상). pykrx에서 바로 제공해줌.
    
    # 5년치 롤링(Rolling) 밴드를 구하거나 10년 전체 평균 밴드를 구함.
    # 여기서는 "과거 5년치 데이터를 분석하여 PER/PBR의 최저, 평균, 최고 배수를 산출" 조건 적용
    window_days = 252 * window_years # 주식시장 1년 개장일 대략 252일
    
    df['PER_High'] = df['PER'].rolling(window=window_days, min_periods=window_days//2).max()
    df['PER_Mid'] = df['PER'].rolling(window=window_days, min_periods=window_days//2).mean()
    df['PER_Low'] = df['PER'].rolling(window=window_days, min_periods=window_days//2).min()
    
    df['PBR_High'] = df['PBR'].rolling(window=window_days, min_periods=window_days//2).max()
    df['PBR_Mid'] = df['PBR'].rolling(window=window_days, min_periods=window_days//2).mean()
    df['PBR_Low'] = df['PBR'].rolling(window=window_days, min_periods=window_days//2).min()

    # 상단/하단 가격 밴드 산출
    # 고평가 주가 = BPS * 최고 PBR 배수
    # 저평가 주가 = BPS * 최저 PBR 배수
    if 'BPS' in df.columns:
        df['Price_PBR_High'] = df['BPS'] * df['PBR_High']
        df['Price_PBR_Mid'] = df['BPS'] * df['PBR_Mid']
        df['Price_PBR_Low'] = df['BPS'] * df['PBR_Low']
        
    if 'EPS' in df.columns:
        df['Price_PER_High'] = df['EPS'] * df['PER_High']
        df['Price_PER_Mid'] = df['EPS'] * df['PER_Mid']
        df['Price_PER_Low'] = df['EPS'] * df['PER_Low']

    return df
