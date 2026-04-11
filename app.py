import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pykrx import stock

from src.data import (
    get_target_date_range,
    fetch_ohlcv,
    fetch_fundamentals,
    fetch_market_cap,
    get_ticker_name,
    fetch_sector_classifications,
    fetch_multi_horizon_returns,
    SECTOR_HEATMAP_RETURN_COLUMNS,
    get_detailed_financials,
)
from src.analytics import process_ticker_data, calculate_bands
from src.storage import is_update_needed, save_ticker_data, load_ticker_data, save_market_list, load_market_list, get_latest_market_date
from src.macro import fetch_macro_data, MACRO_SYMBOLS, GLOBAL_INDEX_SYMBOLS
from src.data_agent import start_background_agent
from src.storage import (load_market_scatter_data, save_market_scatter_data,
                        load_sector_ytd_data, save_sector_ytd_data,
                        load_macro_data, save_macro_data,
                        SECTOR_YTD_CACHE_VERSION)

st.set_page_config(page_title="Korean Stock Valuation Dashboard", layout="wide")

@st.cache_resource
def init_agent():
    start_background_agent()
    return True
init_agent()


def _format_market_cap_krw_jo_eok(value) -> str:
    """원 단위 시가총액을 '1,219조 4,454억' 형식으로 표시."""
    if pd.isna(value):
        return "—"
    try:
        won = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    if won <= 0:
        return "—"
    jo = won // 10**12
    rem = won % 10**12
    eok = rem // 10**8
    parts = []
    if jo > 0:
        parts.append(f"{jo:,}조")
    if eok > 0:
        parts.append(f"{eok:,}억")
    if not parts:
        return f"{won:,}원"
    return " ".join(parts)


def _cap_weighted_mean_return(df: pd.DataFrame, cap_col: str, ret_col: str):
    """시가총액 가중 평균 수익률(%). 유효 데이터가 없으면 None."""
    if ret_col not in df.columns or cap_col not in df.columns:
        return None
    caps = pd.to_numeric(df[cap_col], errors="coerce")
    rets = pd.to_numeric(df[ret_col], errors="coerce")
    valid = caps.notna() & rets.notna() & (caps > 0)
    if not valid.any():
        return None
    c = caps[valid]
    r = rets[valid]
    total = float(c.sum())
    if total <= 0:
        return None
    return float((r * c).sum() / total)


# --- CSS Styling ---
st.markdown("""
<style>
    /* Dark mode optimized and sleek UI */
    .stApp {
        background-color: #0c0d12;
        color: #ffffff;
    }
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        color: #ffffff;
        font-weight: 700;
    }
    /* Add subtle gradient card look to metrics */
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #161821 0%, #0c0d12 100%);
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #232635;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
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
    df = load_market_scatter_data(market, target_date)
    if df.empty:
        with st.spinner(f"Loading latest market fundamental data for {market}..."):
            df = fetch_market_cap(target_date, market=market)
            if not df.empty:
                save_market_scatter_data(market, df, target_date)
    
    if not df.empty:
        # Filter realistic values
        df = df[(df['PER'] > 0) & (df['PER'] < 100)]
        df = df[(df['PBR'] > 0) & (df['PBR'] < 10)]
    return df


# --- UI Setup ---
st.title("📈 K-Stock Valuation Platform")
st.markdown("한국 주식 종목의 10년 치 PER / PBR 밴드 차트 및 업종 비교")

# Sidebar
st.sidebar.header("Navigation")
menu_sel = st.sidebar.radio("Menu", ["Stock Valuation", "Market Sectors", "Macro Indicators", "Global Indices"])

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
        
        @st.cache_data(ttl=3600)
        def load_detailed_financials(ticker: str):
            return get_detailed_financials(ticker)
        
        detailed_fin_df = load_detailed_financials(selected_ticker)
        
        with tab1:
            st.subheader("Price vs Historical PBR Bands")
            # Plotly Chart
            fig_pbr = go.Figure()
            
            # Colors for bands (Vivid and distinct)
            colors = ['#ff6692', '#ab63fa', '#19d3f3', '#00cc96', '#ffa15a']
            fill_colors = ['rgba(255,102,146,0.1)', 'rgba(171,99,250,0.15)', 'rgba(25,211,243,0.15)', 'rgba(0,204,150,0.15)', 'rgba(255,161,90,0.15)']
            
            # Bands
            pbr_cols = [c for c in df.columns if c.startswith('Price_PBR_')]
            # Sort to ensure lowest multiple is drawn first
            pbr_cols.sort(key=lambda x: float(x.replace('Price_PBR_', '')))
            
            for i, col in enumerate(pbr_cols):
                multiple = col.replace('Price_PBR_', '')
                fig_pbr.add_trace(go.Scatter(
                    x=df.index, y=df[col], mode='lines', 
                    name=f'{multiple}배', 
                    line=dict(color=colors[i % len(colors)], width=2.5, dash='solid'),
                    fill='tonexty' if i > 0 else 'none',
                    fillcolor=fill_colors[i % len(fill_colors)] if i > 0 else 'rgba(0,0,0,0)'
                ))
                
            # Price (Plot last to keep on top, thick white/blue line)
            fig_pbr.add_trace(go.Scatter(x=df.index, y=df['종가'], mode='lines', name='Price', line=dict(color='#ffffff', width=3.5)))
            
            # Y-axis scaling trick: Bound Y-axis slightly around price to prevent extreme multiples from flattening the chart
            max_price = df['종가'].max()
            min_price = df['종가'].min()
            fig_pbr.update_layout(
                template="plotly_dark", 
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(range=[min_price * 0.4, max_price * 1.6], showgrid=True, gridcolor='#232635'),
                xaxis=dict(showgrid=True, gridcolor='#232635'),
                hovermode="x unified", height=500, title="PBR Band Chart (Fixed Multiples)"
            )
            st.plotly_chart(fig_pbr, width='stretch')
            
            st.subheader("Price vs Historical PER Bands")
            fig_per = go.Figure()
            
            per_cols = [c for c in df.columns if c.startswith('Price_PER_')]
            per_cols.sort(key=lambda x: float(x.replace('Price_PER_', '')))
            
            for i, col in enumerate(per_cols):
                multiple = col.replace('Price_PER_', '')
                fig_per.add_trace(go.Scatter(
                    x=df.index, y=df[col], mode='lines', 
                    name=f'{multiple}배', 
                    line=dict(color=colors[i % len(colors)], width=2.5, dash='solid'),
                    fill='tonexty' if i > 0 else 'none',
                    fillcolor=fill_colors[i % len(fill_colors)] if i > 0 else 'rgba(0,0,0,0)'
                ))
                
            fig_per.add_trace(go.Scatter(x=df.index, y=df['종가'], mode='lines', name='Price', line=dict(color='#ffffff', width=3.5)))
            
            fig_per.update_layout(
                template="plotly_dark", 
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(range=[min_price * 0.4, max_price * 1.6], showgrid=True, gridcolor='#232635'),
                xaxis=dict(showgrid=True, gridcolor='#232635'),
                hovermode="x unified", height=500, title="PER Band Chart (Fixed Multiples)"
            )
            st.plotly_chart(fig_per, width='stretch')
            
            st.subheader("Latest Financials")
            st.dataframe(df[['종가', 'BPS', 'PER', 'PBR', 'EPS']].tail(5))
            
            st.subheader("📋 FnGuide 기업실적분석 (Annual / Consensus)")
            if not detailed_fin_df.empty:
                st.dataframe(detailed_fin_df, width='stretch')
            else:
                st.warning("현재 종목의 상세 기업실적 데이터를 불러올 수 없습니다.")
            
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
            st.plotly_chart(fig_scatter, width='stretch')

    else:
        st.error("데이터를 불러오지 못했습니다. (적자 기업이거나 데이터가 부족할 수 있습니다.)")

elif menu_sel == "Market Sectors":
    st.header(f"🥧 {market_sel} 커버리지 섹터 분석")
    st.markdown("전체 시장의 업종별 비중과 시가총액 순 종목을 확인하세요.")

    @st.cache_data(ttl=3600)
    def load_sector_and_ytd(market: str, _sector_cache_ver: int):
        target_date = get_latest_market_date()
        df = load_sector_ytd_data(market, target_date)
        if not df.empty and set(SECTOR_HEATMAP_RETURN_COLUMNS).issubset(df.columns):
            return df

        with st.spinner(f"Loading Sector & multi-period returns for {market}..."):
            sector_df = fetch_sector_classifications(target_date, market)
            ret_df = fetch_multi_horizon_returns(target_date, market)

            if not sector_df.empty:
                merged = sector_df.join(ret_df, how="left")
                for c in SECTOR_HEATMAP_RETURN_COLUMNS:
                    if c not in merged.columns:
                        merged[c] = pd.NA
                save_sector_ytd_data(market, merged, target_date)
                return merged
            return sector_df


    sector_data = load_sector_and_ytd(market_sel, SECTOR_YTD_CACHE_VERSION)

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
        st.plotly_chart(fig_pie, width='stretch')
        
        # 2. Multi-period sector heatmap (Treemap)
        st.subheader("🟩🟥 Sector Heatmap (Treemap)")
        period_labels = ("1일", "1개월", "3개월", "YTD")
        period_to_col = {
            "1일": "RET_1D",
            "1개월": "RET_1M",
            "3개월": "RET_3M",
            "YTD": "YTD(%)",
        }
        period_to_colorbar = {
            "1일": "1D_Color",
            "1개월": "1M_Color",
            "3개월": "3M_Color",
            "YTD": "YTD_Color",
        }
        period_descriptions = {
            "1일": "전일 대비",
            "1개월": "1개월 전 대비",
            "3개월": "3개월 전 대비",
            "YTD": "연초 대비",
        }

        td_raw = get_latest_market_date()
        td_fmt = f"{td_raw[:4]}.{td_raw[4:6]}.{td_raw[6:8]} 장마감"
        row1, row2, row3 = st.columns([0.11, 0.62, 0.27])
        with row1:
            st.markdown("**변동률**")
        with row2:
            selected_period = st.radio(
                "변동률 기간",
                period_labels,
                horizontal=True,
                label_visibility="collapsed",
            )
        with row3:
            st.caption(td_fmt)

        sel_col = period_to_col[selected_period]
        st.markdown(
            f"전체 시장의 종목 시가총액(크기)과 **{period_descriptions[selected_period]}** 수익률(색상)을 한눈에 파악하세요."
        )

        heatmap_data = sector_data.copy()
        heatmap_data = heatmap_data[heatmap_data['시가총액'] > 0]

        colorbar_title = period_to_colorbar[selected_period]

        if sel_col in heatmap_data.columns:
            ret_series = pd.to_numeric(heatmap_data[sel_col], errors="coerce")
            heatmap_data["_Heatmap_Color"] = ret_series.fillna(0).clip(lower=-30, upper=30)

            kor_scale = [
                (0.0, "#2b64d1"),
                (0.5, "#40444d"),
                (1.0, "#f23a47"),
            ]

            fig_tree = px.treemap(
                heatmap_data,
                path=[px.Constant(market_sel), "업종명", "종목명"],
                values="시가총액",
                color="_Heatmap_Color",
                color_continuous_scale=kor_scale,
                color_continuous_midpoint=0,
                hover_data=[sel_col, "종가"],
            )
            fig_tree.update_traces(
                texttemplate="<b>%{label}</b><br>%{customdata[0]:+.2f}%",
                textposition="middle center",
                textfont=dict(color="white", size=14),
                hovertemplate=(
                    "<b>%{label}</b><br>시가총액: ₩%{value:,.0f}<br>"
                    f"{selected_period}: %{{customdata[0]:+.2f}}%<br>종가: ₩%{{customdata[1]:,.0f}}"
                ),
            )
            fig_tree.update_layout(
                template="plotly_dark",
                height=750,
                margin=dict(t=30, b=30, l=10, r=10),
                coloraxis_colorbar=dict(title=colorbar_title),
            )
        else:
            fig_tree = px.treemap(
                heatmap_data,
                path=[px.Constant(market_sel), "업종명", "종목명"],
                values="시가총액",
            )
            fig_tree.update_layout(template="plotly_dark", height=750, margin=dict(t=30, b=30, l=10, r=10))

        st.plotly_chart(fig_tree, width="stretch")
        
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
        
        sector_detail_ret_col = "YTD(%)"
        sector_w_ret = _cap_weighted_mean_return(
            sector_stocks, "시가총액", sector_detail_ret_col
        )
        if sector_w_ret is not None:
            sign = "+" if sector_w_ret >= 0 else ""
            st.markdown(
                f"**{selected_sector}** 섹터 시가총액 가중 "
                f"**{period_descriptions['YTD']}** 수익률: "
                f"**{sign}{sector_w_ret:.2f}%**"
            )
        else:
            st.caption(
                "선택한 섹터의 **연초 대비** 가중 수익률을 계산할 수 없습니다. "
                "(YTD 데이터 부족)"
            )

        list_df = sector_stocks.reset_index()
        idx0 = list_df.columns[0]
        list_df = list_df.rename(columns={idx0: "종목코드"})

        display_cols = ["종목코드", "종목명", "종가"]
        if sector_detail_ret_col in list_df.columns:
            display_cols.append(sector_detail_ret_col)
        display_cols.append("시가총액")

        formatted_df = list_df[display_cols].copy()
        formatted_df["시가총액"] = list_df["시가총액"].map(_format_market_cap_krw_jo_eok)

        col_cfg = {
            "종목코드": st.column_config.TextColumn("종목코드", width="small"),
            "종목명": st.column_config.TextColumn("종목명", width="medium"),
            "종가": st.column_config.NumberColumn("종가", format="₩%d"),
            "시가총액": st.column_config.TextColumn("시가총액"),
        }
        if sector_detail_ret_col in formatted_df.columns:
            col_cfg[sector_detail_ret_col] = st.column_config.NumberColumn(
                "YTD",
                format="%.2f%%",
            )

        st.dataframe(
            formatted_df,
            width="stretch",
            hide_index=True,
            column_config=col_cfg,
        )
    else:
        st.error(f"{market_sel} 시장의 섹터 데이터를 불러오지 못했습니다. 장 휴일이나 주말일 수 있습니다.")

elif menu_sel == "Macro Indicators":
    st.header("🌍 매크로 경제 지표 (Macro Indicators)")
    st.markdown("주요 환율, 유가, 금리 등 매크로 지표의 현재 가격과 추이를 확인하세요.")
    
    # 5개의 카드를 배치하기 위해 위 3개, 아래 2개 형태의 컬럼을 구성합니다.
    items = list(MACRO_SYMBOLS.items())
    
    # 1st row: 3 columns
    cols1 = st.columns(3)
    for i in range(3):
        with cols1[i]:
            name, symbol = items[i]
            df = fetch_macro_data(symbol, years=10)
            if not df.empty and len(df) >= 2:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                pct_change = (current_price - prev_price) / prev_price * 100
                diff = current_price - prev_price
                
                # Metric
                st.metric(label=name, value=f"{current_price:,.2f}", delta=f"{diff:+,.2f} ({pct_change:+.2f}%)")
                
                # Mini Sparkline chart (last 90 days)
                df_recent = df.last('90D')
                color = '#00cc96' if pct_change >= 0 else '#ef553b'
                fig_mini = go.Figure(go.Scatter(x=df_recent.index, y=df_recent['Close'], mode='lines', line=dict(color=color, width=2)))
                fig_mini.update_layout(
                    height=80, margin=dict(l=0, r=0, t=0, b=0),
                    xaxis=dict(visible=False, showgrid=False),
                    yaxis=dict(visible=False, showgrid=False),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    showlegend=False, hovermode='x'
                )
                st.plotly_chart(fig_mini, width='stretch', config={'displayModeBar': False})
                
                with st.expander(f"📊 {name} 10년 트렌드 기록"):
                    fig_full = go.Figure(go.Scatter(x=df.index, y=df['Close'], name=name, line=dict(color='#19d3f3')))
                    fig_full.update_layout(
                        template='plotly_dark',
                        height=350, margin=dict(l=10, r=10, t=30, b=10),
                        title=f"{name} (10-Year)",
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig_full, width='stretch')
            else:
                st.error(f"{name} 데이터를 불러올 수 없습니다.")

    st.divider()
    
    # 2nd row: 2 columns
    cols2 = st.columns(2)
    for i in range(3, 5):
        with cols2[i-3]:
            name, symbol = items[i]
            df = fetch_macro_data(symbol, years=10)
            if not df.empty and len(df) >= 2:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                pct_change = (current_price - prev_price) / prev_price * 100
                diff = current_price - prev_price
                
                # Metric
                st.metric(label=name, value=f"{current_price:,.2f}", delta=f"{diff:+,.2f} ({pct_change:+.2f}%)")
                
                # Mini Sparkline chart (last 90 days)
                df_recent = df.last('90D')
                color = '#00cc96' if pct_change >= 0 else '#ef553b'
                fig_mini = go.Figure(go.Scatter(x=df_recent.index, y=df_recent['Close'], mode='lines', line=dict(color=color, width=2)))
                fig_mini.update_layout(
                    height=80, margin=dict(l=0, r=0, t=0, b=0),
                    xaxis=dict(visible=False, showgrid=False),
                    yaxis=dict(visible=False, showgrid=False),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    showlegend=False, hovermode='x'
                )
                st.plotly_chart(fig_mini, width='stretch', config={'displayModeBar': False})
                
                with st.expander(f"📊 {name} 10년 트렌드 기록"):
                    fig_full = go.Figure(go.Scatter(x=df.index, y=df['Close'], name=name, line=dict(color='#19d3f3')))
                    fig_full.update_layout(
                        template='plotly_dark',
                        height=350, margin=dict(l=10, r=10, t=30, b=10),
                        title=f"{name} (10-Year)",
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig_full, width='stretch')
            else:
                st.error(f"{name} 데이터를 불러올 수 없습니다.")

elif menu_sel == "Global Indices":
    st.header("🌐 국내/해외 주요 지수 (Global Indices)")
    st.markdown("KOSPI, KOSDAQ, S&P 500, 그리고 나스닥 지수의 현재 가격과 10년 트렌드를 확인하세요.")
    
    items = list(GLOBAL_INDEX_SYMBOLS.items())
    
    # 4 columns for 4 indices
    cols = st.columns(len(items))
    for i, (name, symbol) in enumerate(items):
        with cols[i]:
            df = fetch_macro_data(symbol, years=10)
            if not df.empty and len(df) >= 2:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                pct_change = (current_price - prev_price) / prev_price * 100
                diff = current_price - prev_price
                
                # Metric
                st.metric(label=name, value=f"{current_price:,.2f}", delta=f"{diff:+,.2f} ({pct_change:+.2f}%)")
                
                # Mini Sparkline chart (last 90 days)
                df_recent = df.last('90D')
                color = '#00cc96' if pct_change >= 0 else '#ef553b'
                fig_mini = go.Figure(go.Scatter(x=df_recent.index, y=df_recent['Close'], mode='lines', line=dict(color=color, width=2)))
                fig_mini.update_layout(
                    height=80, margin=dict(l=0, r=0, t=0, b=0),
                    xaxis=dict(visible=False, showgrid=False),
                    yaxis=dict(visible=False, showgrid=False),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    showlegend=False, hovermode='x'
                )
                st.plotly_chart(fig_mini, width='stretch', config={'displayModeBar': False})
                
                with st.expander(f"📊 {name} 10년 트렌드 기록"):
                    fig_full = go.Figure(go.Scatter(x=df.index, y=df['Close'], name=name, line=dict(color='#19d3f3')))
                    fig_full.update_layout(
                        template='plotly_dark',
                        height=350, margin=dict(l=10, r=10, t=30, b=10),
                        title=f"{name} (10-Year)",
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig_full, width='stretch')
            else:
                st.error(f"{name} 데이터를 불러올 수 없습니다.")
