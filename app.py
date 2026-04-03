import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pykrx import stock

from src.data import get_target_date_range, fetch_ohlcv, fetch_fundamentals, fetch_market_cap, get_ticker_name
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
st.sidebar.header("Filter & Search")
market_sel = st.sidebar.radio("Market", ["KOSPI", "KOSDAQ"])

market_df = load_market_tickers(market_sel)
if market_df.empty:
    st.error("KRX 종목 데이터를 불러올 수 없습니다. 장 개장 초기나 휴일에는 잠시 후 시도해주세요.")
    st.stop()

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
