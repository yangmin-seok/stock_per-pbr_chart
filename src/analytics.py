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

def get_nice_multiples(series, num_bands=4):
    """
    Extract perfectly spaced rounded multiples based on historical distributions.
    Removes extreme outliers by using 5th and 95th percentiles.
    """
    if series.empty or series.dropna().empty:
        return []
    
    q_min = series.quantile(0.05)
    q_max = series.quantile(0.95)
    
    if q_min == q_max:
        return [round(q_min, 2)]
        
    step = (q_max - q_min) / (num_bands - 1)
    multiples = [q_min + i * step for i in range(num_bands)]
    
    if q_max > 10:
        # For PER, round to 1 decimal place
        rounded = [round(m, 1) for m in multiples]
    else:
        # For PBR, round to 2 decimal places
        rounded = [round(m, 2) for m in multiples]
        
    # Ensure uniqueness
    return sorted(list(set(rounded)))

def calculate_bands(df: pd.DataFrame, window_years=5):
    """
    고평가, 저평가 판단을 위한 PER/PBR 통계적 고정 밴드 산출.
    동적 Trailing 방식 대신 전체 기간의 분위수(Quantiles)를 활용해 부드럽고 가독성 높은 차트를 그림.
    """
    if df.empty:
        return df

    # PBR 밴드 산출
    if 'PBR' in df.columns and 'BPS' in df.columns:
        pbr_multiples = get_nice_multiples(df['PBR'], num_bands=4)
        for m in pbr_multiples:
            df[f'Price_PBR_{m}'] = df['BPS'] * m
            
    # PER 밴드 산출
    if 'PER' in df.columns and 'EPS' in df.columns:
        per_multiples = get_nice_multiples(df['PER'], num_bands=4)
        for m in per_multiples:
            df[f'Price_PER_{m}'] = df['EPS'] * m

    return df
