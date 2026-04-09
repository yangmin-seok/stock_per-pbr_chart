import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    import yfinance as yf
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

def main():
    print("데이터를 수집하는 중입니다 (1996-01-01 ~ 2026-12-31)...")
    kospi = yf.download('^KS11', start='1996-01-01', end='2026-12-31')['Close']
    wti   = yf.download('CL=F',  start='1996-01-01', end='2026-12-31')['Close']

    if isinstance(kospi, pd.DataFrame): kospi = kospi.squeeze()
    if isinstance(wti,   pd.DataFrame): wti   = wti.squeeze()

    df = pd.DataFrame({'KOSPI': kospi, 'WTI': wti})
    df = df.ffill().dropna()
    df_monthly = df.resample('ME').last()

    df_pct = df_monthly.pct_change().dropna()

    corr_price  = df_monthly['KOSPI'].corr(df_monthly['WTI'])
    corr_return = df_pct['KOSPI'].corr(df_pct['WTI'])

    print("\n" + "="*50)
    print("전체 기간 (1996~현재) 상관관계 및 R-squared")
    print(f"  [가격 기준]   상관계수: {corr_price:.4f},  R²: {corr_price**2:.4f}")
    print(f"  [수익률 기준] 상관계수: {corr_return:.4f}, R²: {corr_return**2:.4f}")
    print("="*50)

    rolling_3m    = df_pct['KOSPI'].rolling(3).corr(df_pct['WTI'])
    rolling_12m   = df_pct['KOSPI'].rolling(12).corr(df_pct['WTI'])
    rolling_5y_r2 = df_pct['KOSPI'].rolling(60).corr(df_pct['WTI']) ** 2

    print("\n3개월 롤링 상관계수 요약")
    print(rolling_3m.describe())
    print("\n1년 롤링 상관계수 요약")
    print(rolling_12m.describe())
    print("\n5년 롤링 R-squared 요약")
    print(rolling_5y_r2.describe())

    df_norm = df_monthly / df_monthly.iloc[0]

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.07,
        subplot_titles=(
            "코스피 vs WTI 누적 추이 (시작점=1)",
            "3개월 순환 상관계수 (3개월)",          # ← 신규
            "1년간 월별 순환 상관계수 (12개월)",
            "5년간 월간 순환 R-squared (60개월)",
        ),
        row_heights=[0.25, 0.25, 0.25, 0.25],
    )

    # 패널 1 ─ 누적 가격 추이
    fig.add_trace(go.Scatter(
        x=df_norm.index, y=df_norm['KOSPI'],
        name='KOSPI', line=dict(color='blue', width=1.5)
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df_norm.index, y=df_norm['WTI'],
        name='WTI (유가)', line=dict(color='orange', width=1.5)
    ), row=1, col=1)

    # 패널 2 ─ 3개월 롤링 상관계수 (신규)
    fig.add_trace(go.Scatter(
        x=rolling_3m.index, y=rolling_3m,
        name='3m Corr', line=dict(color='tomato', width=1.2)
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="gray", row=2, col=1)

    # 패널 3 ─ 12개월 롤링 상관계수
    fig.add_trace(go.Scatter(
        x=rolling_12m.index, y=rolling_12m,
        name='1y Corr', line=dict(color='green', width=1.5)
    ), row=3, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="gray", row=3, col=1)

    # 패널 4 ─ 5년 R-squared
    fig.add_trace(go.Scatter(
        x=rolling_5y_r2.index, y=rolling_5y_r2,
        name='5y R²',
        line=dict(color='red', width=1),
        fill='tozeroy', fillcolor='rgba(255,80,80,0.2)',
    ), row=4, col=1)

    fig.update_layout(
        height=1100,
        title_text="KOSPI 및 WTI 상관관계 분석 (1996~2026)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(range=[-1.1, 1.1], row=2, col=1)
    fig.update_yaxes(range=[-1.1, 1.1], row=3, col=1)
    fig.update_yaxes(range=[0, 0.35],   row=4, col=1)

    print("\n차트를 웹 브라우저에 띄웁니다...")
    fig.show()

if __name__ == "__main__":
    main()