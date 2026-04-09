import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pykrx import stock

from src.data import get_target_date_range, fetch_ohlcv, fetch_fundamentals, fetch_market_cap, get_ticker_name, fetch_sector_classifications, fetch_ytd_returns
from src.analytics import process_ticker_data, calculate_bands
from src.storage import is_update_needed, save_ticker_data, load_ticker_data, save_market_list, load_market_list, get_latest_market_date

st.set_page_config(page_title="Korean Stock Valuation Dashboard", layout="wide")

# --- CSS Styling ---
st.markdown("""
<style>
    /* Dark mode optimized and sleek UI */
    .stApp {
        background-color: #0f1115;
        color: #ffffff;
    }
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        color: #e0e6ed;
    }
</style>
""", unsafe_allow_html=True)

# --- Data Loading Logic ---
@st.cache_data(ttl=3600)
def load_market_tickers(market: str):
    df_list = load_market_list(market)
    
    if df_list.empty:
        with st.spinner(f"Fetching {market} Tickers..."):
            from datetime import timedelta
            now = pd.Timestamp.now('Asia/Seoul')
            for offset in range(10):
                target_date = (now - timedelta(days=offset)).strftime("%Y%m%d")
                tickers = stock.get_market_ticker_list(target_date, market=market)
                if tickers:
                    names = [stock.get_market_ticker_name(t) for t in tickers]
                    df_list = pd.DataFrame({'티커': tickers, '종목명': names}).set_index('티커')
                    save_market_list(df_list, market)
                    break
    return df_list

def load_and_process_stock(ticker: str):
    if is_update_needed(ticker):
        with st.spinner("Downloading 10-year historical data..."):
            start_date, end_date = get_target_date_range(years=10)
            ohlcv = fetch_ohlcv(ticker, start_date, end_date)
            fund = fetch_fundamentals(ticker, start_date, end_date)
            
            df = process_ticker_data(ohlcv, fund)
            df = calculate_bands(df, window_years=5)
            
            save_ticker_data(ticker, df)
            return df
    else:
        return load_ticker_data(ticker)

@st.cache_data(ttl=3600)
def load_market_scatter(market: str):
    target_date = get_latest_market_date()
    with st.spinner(f"Loading latest market fundamental data for {market}..."):
        df = fetch_market_cap(target_date, market=market)
        # Filter realistic values
        df = df[(df['PER'] > 0) & (df['PER'] < 100)]
        df = df[(df['PBR'] > 0) & (df['PBR'] < 10)]
        return df

# --- UI Setup ---
st.title("📈 K-Stock Valuation Platform")
st.markdown("한국 주식 종목의 10년 치 PER / PBR 밴드 차트 및 업종 비교")

# Sidebar
st.sidebar.header("Navigation")
menu_sel = st.sidebar.radio("Menu", ["Stock Valuation", "Market Sectors"])

st.sidebar.header("Filter & Search")
market_sel = st.sidebar.radio("Market", ["KOSPI", "KOSDAQ"])

market_df = load_market_tickers(market_sel)
if market_df.empty:
    st.error("KRX 종목 데이터를 불러올 수 없습니다. 장 개장 초기나 휴일에는 잠시 후 시도해주세요.")
    st.stop()

if menu_sel == "KOSDAQ" and market_df.empty: # small hack to keep market_df scope when needed
    pass # just avoiding indent changes on the original code layout, actually the stop condition handles it.

ticker_options = market_df.reset_index()

# Ensure types are string before concatenation 
# Ticker might be parsed as int/float from sqlite if it consists of numbers
ticker_options['티커'] = ticker_options['티커'].astype(str).str.zfill(6)
ticker_options['종목명'] = ticker_options['종목명'].astype(str)

ticker_options['display'] = ticker_options['종목명'] + " (" + ticker_options['티커'] + ")"

search_term = st.sidebar.selectbox("Search Stock", ticker_options['display'].tolist())
selected_ticker = ticker_options[ticker_options['display'] == search_term]['티커'].values[0]
selected_name = ticker_options[ticker_options['display'] == search_term]['종목명'].values[0]

# --- Main Dashboard ---
if menu_sel == "Stock Valuation":
    st.header(f"📊 {selected_name} ({selected_ticker})")

    df = load_and_process_stock(selected_ticker)

    if not df.empty:
        tab1, tab2 = st.tabs(["Valuation Bands", "Market Scatter"])
        
        with tab1:
            st.subheader("Price vs Historical PBR Bands")
            # Plotly Chart
            fig_pbr = go.Figure()
            
            # Colors for bands (Vivid and distinct)
            colors = ['#ef553b', '#00cc96', '#ab63fa', '#ffa15a', '#19d3f3', '#ff6692']
            
            # Bands
            pbr_cols = [c for c in df.columns if c.startswith('Price_PBR_')]
            # Sort to ensure lowest multiple is drawn first
            pbr_cols.sort(key=lambda x: float(x.replace('Price_PBR_', '')))
            
            for i, col in enumerate(pbr_cols):
                multiple = col.replace('Price_PBR_', '')
                fig_pbr.add_trace(go.Scatter(
                    x=df.index, y=df[col], mode='lines', 
                    name=f'{multiple}배', 
                    line=dict(color=colors[i % len(colors)], width=1.5, dash='solid')
                ))
                
            # Price (Plot last to keep on top)
            fig_pbr.add_trace(go.Scatter(x=df.index, y=df['종가'], mode='lines', name='Price', line=dict(color='#1f77b4', width=3.5)))
            
            # Y-axis scaling trick: Bound Y-axis slightly around price to prevent extreme multiples from flattening the chart
            max_price = df['종가'].max()
            min_price = df['종가'].min()
            fig_pbr.update_layout(
                template="plotly_dark", 
                yaxis=dict(range=[min_price * 0.4, max_price * 1.6]),
                hovermode="x unified", height=500, title="PBR Band Chart (Fixed Multiples)"
            )
            st.plotly_chart(fig_pbr, use_container_width=True)
            
            st.subheader("Price vs Historical PER Bands")
            fig_per = go.Figure()
            
            per_cols = [c for c in df.columns if c.startswith('Price_PER_')]
            per_cols.sort(key=lambda x: float(x.replace('Price_PER_', '')))
            
            for i, col in enumerate(per_cols):
                multiple = col.replace('Price_PER_', '')
                fig_per.add_trace(go.Scatter(
                    x=df.index, y=df[col], mode='lines', 
                    name=f'{multiple}배', 
                    line=dict(color=colors[i % len(colors)], width=1.5, dash='solid')
                ))
                
            fig_per.add_trace(go.Scatter(x=df.index, y=df['종가'], mode='lines', name='Price', line=dict(color='#1f77b4', width=3.5)))
            
            fig_per.update_layout(
                template="plotly_dark", 
                yaxis=dict(range=[min_price * 0.4, max_price * 1.6]),
                hovermode="x unified", height=500, title="PER Band Chart (Fixed Multiples)"
            )
            st.plotly_chart(fig_per, use_container_width=True)
            
            st.subheader("Latest Financials")
            st.dataframe(df[['종가', 'BPS', 'PER', 'PBR', 'EPS']].tail(5))
            
        with tab2:
            st.subheader(f"Peer Comparison Scatter: {market_sel}")
            st.write("X: PER, Y: PBR. (Exclude negative earnings, PER > 100, PBR > 10)")
            
            scatter_df = load_market_scatter(market_sel)
            # Add a column to identify the selected stock
            scatter_df['Color'] = 'Others'
            if selected_ticker in scatter_df.index:
                scatter_df.at[selected_ticker, 'Color'] = 'Selected'
                
            # Also need ticker names for hover
            scatter_df = scatter_df.join(market_df, how='inner')
                
            fig_scatter = px.scatter(
                scatter_df, x='PER', y='PBR', hover_name='종목명',
                color='Color', color_discrete_map={'Others': '#1f77b4', 'Selected': '#ff7f0e'},
                title=f"Relative Valuation in {market_sel}"
            )
            fig_scatter.update_layout(template="plotly_dark")
            st.plotly_chart(fig_scatter, use_container_width=True)

    else:
        st.error("데이터를 불러오지 못했습니다. (적자 기업이거나 데이터가 부족할 수 있습니다.)")

elif menu_sel == "Market Sectors":
    st.header(f"🥧 {market_sel} 커버리지 섹터 분석")
    st.markdown("전체 시장의 업종별 비중과 시가총액 순 종목을 확인하세요.")

    @st.cache_data(ttl=3600)
    def load_sector_and_ytd(market: str):
        target_date = get_latest_market_date()
        with st.spinner(f"Loading Sector & YTD data for {market}..."):
            sector_df = fetch_sector_classifications(target_date, market)
            ytd_df = fetch_ytd_returns(target_date, market)

            if not sector_df.empty and not ytd_df.empty:
                # Merge logic
                # ytd_df index is ticker. sector_df index is also ticker.
                merged = sector_df.join(ytd_df[['등락률']], rsuffix='_YTD')
                merged.rename(columns={'등락률_YTD': 'YTD(%)'}, inplace=True)
                return merged
            return sector_df # fallback

    sector_data = load_sector_and_ytd(market_sel)

    if not sector_data.empty:
        # 1. 시가총액 기반 섹터별 비중 파이 차트 (가독성 개선)
        sector_weights = sector_data.groupby('업종명')['시가총액'].sum().reset_index()
        sector_weights = sector_weights[sector_weights['시가총액'] > 0]
        
        # 1% 미만 비중의 섹터는 '기타(Others)'로 묶기
        total_market_cap = sector_weights['시가총액'].sum()
        sector_weights['비중'] = sector_weights['시가총액'] / total_market_cap * 100
        sector_weights.loc[sector_weights['비중'] < 1.5, '업종명'] = '기타(Others)'
        
        # 재집계 및 정렬
        sector_weights_agg = sector_weights.groupby('업종명')['시가총액'].sum().reset_index()
        sector_weights_agg = sector_weights_agg.sort_values(by='시가총액', ascending=False)
        
        # '기타(Others)'를 맨 뒤로 보내기 위한 로직
        others_mask = sector_weights_agg['업종명'] == '기타(Others)'
        others_df = sector_weights_agg[others_mask]
        main_df = sector_weights_agg[~others_mask]
        sector_weights_agg = pd.concat([main_df, others_df])
        
        st.subheader(f"🥧 {market_sel} 섹터별 비중 (Top Sectors)")
        fig_pie = px.pie(
            sector_weights_agg, 
            values='시가총액', 
            names='업종명', 
            hole=0.4
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(template="plotly_dark", height=450, margin=dict(t=30, b=30, l=10, r=10))
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # 2. YTD Heatmap (Treemap)
        st.subheader("🟩🟥 YTD Sector Heatmap (Treemap)")
        st.markdown("전체 시장의 종목 시가총액(크기)과 연초 대비 수익률(색상)을 한눈에 파악하세요.")
        
        heatmap_data = sector_data.copy()
        heatmap_data = heatmap_data[heatmap_data['시가총액'] > 0]
        
        if 'YTD(%)' in heatmap_data.columns:
            heatmap_data['YTD(%)'] = heatmap_data['YTD(%)'].fillna(0)
            # Clip extreme values for better color scaling visually
            heatmap_data['YTD_Color'] = heatmap_data['YTD(%)'].clip(lower=-30, upper=30)
            
            # Custom Color Scale (Blue: -30%, Gray: 0%, Red: +30%)
            kor_scale = [
                (0.0, '#2b64d1'), # Blue
                (0.5, '#40444d'), # Dark Gray (near zero)
                (1.0, '#f23a47')  # Red
            ]
            
            fig_tree = px.treemap(
                heatmap_data, 
                path=[px.Constant(market_sel), '업종명', '종목명'], 
                values='시가총액',
                color='YTD_Color',
                color_continuous_scale=kor_scale,
                color_continuous_midpoint=0,
                hover_data=['YTD(%)', '종가']
            )
            # Add YTD percentage string into each box and adjust fonts
            fig_tree.update_traces(
                texttemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%",
                textposition="middle center",
                textfont=dict(color="white", size=14),
                hovertemplate='<b>%{label}</b><br>시가총액: ₩%{value:,.0f}<br>YTD: %{customdata[0]:+.2f}%<br>종가: ₩%{customdata[1]:,.0f}'
            )
        else:
            # Fallback if YTD fails
            fig_tree = px.treemap(
                heatmap_data, 
                path=[px.Constant(market_sel), '업종명', '종목명'], 
                values='시가총액'
            )
            
        fig_tree.update_layout(template="plotly_dark", height=750, margin=dict(t=30, b=30, l=10, r=10))
        st.plotly_chart(fig_tree, use_container_width=True)
        
        # 3. 섹터 선택 드롭다운 및 테이블
        st.divider()
        st.subheader("📊 섹터 상세 및 종목 리스트")
        # For the selectbox, we use the raw un-agged weights so they can see ALL sectors
        sector_weights_raw = sector_data.groupby('업종명')['시가총액'].sum().reset_index()
        sector_weights_raw = sector_weights_raw.sort_values(by='시가총액', ascending=False)
        sector_list = sector_weights_raw['업종명'].tolist()
        
        selected_sector = st.selectbox("업종 선택", sector_list)
        
        # 해당 섹터의 종목 리스트 출력 (시가총액 순 정렬, 종목명, 주가, YTD 포함)
        sector_stocks = sector_data[sector_data['업종명'] == selected_sector]
        sector_stocks = sector_stocks.sort_values(by='시가총액', ascending=False)
        
        # Select required columns
        display_cols = ['종목명', '종가', 'YTD(%)', '시가총액']
        if 'YTD(%)' not in sector_stocks.columns:
            display_cols = ['종목명', '종가', '시가총액']

        # Format numeric values implicitly via column config
        formatted_df = sector_stocks[display_cols].copy()
            
        st.dataframe(
            formatted_df, 
            use_container_width=True, 
            hide_index=False,
            column_config={
                "종가": st.column_config.NumberColumn(format="₩%d"),
                "시가총액": st.column_config.NumberColumn(format="₩%d"),
                "YTD(%)": st.column_config.NumberColumn(format="%.2f%%")
            }
        )
    else:
        st.error(f"{market_sel} 시장의 섹터 데이터를 불러오지 못했습니다. 장 휴일이나 주말일 수 있습니다.")
