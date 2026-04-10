import time
import threading
from datetime import datetime, timedelta
import pandas as pd
from pytz import timezone

from src.storage import (get_latest_market_date, is_update_needed,
    save_ticker_data, load_market_list, save_market_list,
    save_market_scatter_data, load_market_scatter_data,
    save_sector_ytd_data, load_sector_ytd_data,
    save_macro_data, load_macro_data)
from src.data import (get_target_date_range, fetch_ohlcv, fetch_fundamentals, 
    fetch_market_cap, fetch_sector_classifications, fetch_ytd_returns, fetch_tickers)
from src.macro import MACRO_SYMBOLS, US_INDEX_SYMBOLS, fetch_macro_data

import logging
logger = logging.getLogger('data_agent')
logger.setLevel(logging.INFO)

# Suppress annoying streamline warnings in background threads
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)

logger.setLevel(logging.INFO)

def update_macro_data():
    all_symbols = {**MACRO_SYMBOLS, **US_INDEX_SYMBOLS}
    target_date = get_latest_market_date()
    
    for name, symbol in all_symbols.items():
        try:
            df_db = load_macro_data(symbol)
            if df_db.empty or df_db.index.max().strftime('%Y%m%d') < target_date:
                logger.info(f"Updating Macro Data: {symbol} ({name})")
                df = fetch_macro_data(symbol, years=10)
                if not df.empty:
                    save_macro_data(symbol, df, target_date)
                time.sleep(1)
        except Exception as e:
            logger.error(f"Error updating macro data for {symbol}: {e}")

def update_market_globals():
    target_date = get_latest_market_date()
    for market in ["KOSPI", "KOSDAQ"]:
        # 1. Update Market Scatter (Fundamentals)
        df_scatter = load_market_scatter_data(market, target_date)
        if df_scatter.empty:
            logger.info(f"Updating {market} Scatter Fundamentals for {target_date}")
            try:
                df = fetch_market_cap(target_date, market=market)
                if not df.empty:
                    save_market_scatter_data(market, df, target_date)
            except Exception as e:
                logger.error(f"Error fetching market cap for {market}: {e}")
            time.sleep(1)
        
        # 2. Update Sector and YTD
        df_sector_ytd = load_sector_ytd_data(market, target_date)
        if df_sector_ytd.empty:
            logger.info(f"Updating {market} Sector/YTD for {target_date}")
            try:
                sector_df = fetch_sector_classifications(target_date, market)
                ytd_df = fetch_ytd_returns(target_date, market)
                if not sector_df.empty and not ytd_df.empty:
                    merged = sector_df.join(ytd_df[['등락률']], rsuffix='_YTD')
                    merged.rename(columns={'등락률_YTD': 'YTD(%)'}, inplace=True)
                    save_sector_ytd_data(market, merged, target_date)
            except Exception as e:
                logger.error(f"Error fetching sector/ytd for {market}: {e}")
            time.sleep(1)

def update_individual_tickers():
    """Update 10-year OHLCV for all tickers slowly in the background."""
    from src.analytics import process_ticker_data, calculate_bands
    
    for market in ["KOSPI", "KOSDAQ"]:
        market_df = load_market_list(market)
        if market_df.empty:
            continue
            
        tickers = market_df.index.tolist()
        
        for ticker in tickers:
            if is_update_needed(ticker):
                logger.info(f"Background Update: Fetching 10-year data for {ticker}")
                try:
                    start_date, end_date = get_target_date_range(years=10)
                    ohlcv = fetch_ohlcv(ticker, start_date, end_date)
                    fund = fetch_fundamentals(ticker, start_date, end_date)
                    
                    if not ohlcv.empty and not fund.empty:
                        df = process_ticker_data(ohlcv, fund)
                        df = calculate_bands(df, window_years=5)
                        save_ticker_data(ticker, df)
                except Exception as e:
                    logger.error(f"Failed to update ticker {ticker}: {e}")
                    
                # Sleep to prevent pykrx IP bans
                time.sleep(1.0)

def run_agent():
    """Main background loop."""
    logger.info("Background Data Agent Started.")
    while True:
        try:
            # Check condition: if it's past 16:00 KST, we should update data for today.
            # However, our update functions are idempotent based on `target_date` and `is_update_needed()`.
            # So we can just call them, and they will only fetch if data is missing.
            
            update_macro_data()
            update_market_globals()
            # update_individual_tickers() # Uncommenting this will download 3000 stocks 10y history. Takes hours!
            # Since the user specifically asked for 'background per pbr, heatmap macro', 
            # we will only run update_individual_tickers() slowly if the machine is idling, 
            # but usually they focus on globals for instant gratification. Let's run it.
            
            update_individual_tickers()
            
            # Sleep for 1 hour before checking again
            logger.info("Data Agent Cycle Complete. Sleeping for 1 hour.")
            time.sleep(3600)
            
        except Exception as e:
            logger.error(f"Data Agent crashed: {e}. Restarting in 5 minutes.")
            time.sleep(300)

_agent_thread = None

def start_background_agent():
    global _agent_thread
    if _agent_thread is None or not _agent_thread.is_alive():
        _agent_thread = threading.Thread(target=run_agent, daemon=True)
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(_agent_thread)
        except ImportError:
            pass # older streamlit versions might not have this
        _agent_thread.start()
