import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging
from squeeze.data.downloader import download_market_data

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """
    Tracks recommendations and evaluates their performance after a set period.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_taiwan_now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    def _init_db(self):
        if not self.db_path.exists():
            df = pd.DataFrame(columns=[
                'date', 'ticker', 'name', 'entry_price', 'signal', 'exit_price', 'return_pct', 'evaluated'
            ])
            df.to_csv(self.db_path, index=False)

    def record_recommendations(self, results: List[Dict[str, Any]]):
        """Records new buy recommendations."""
        if not results:
            return

        now_str = self._get_taiwan_now().strftime("%Y-%m-%d")
        new_records = []
        
        for r in results:
            new_records.append({
                'date': now_str,
                'ticker': r.get('ticker'),
                'name': r.get('name'),
                'entry_price': r.get('Close'),
                'signal': r.get('Signal'),
                'exit_price': None,
                'return_pct': None,
                'evaluated': False
            })
        
        df_new = pd.DataFrame(new_records)
        df_old = pd.read_csv(self.db_path)
        
        # Avoid duplicate entries for same day/ticker
        df_combined = pd.concat([df_old, df_new]).drop_duplicates(subset=['date', 'ticker'], keep='last')
        df_combined.to_csv(self.db_path, index=False)
        logger.info(f"Recorded {len(new_records)} recommendations to {self.db_path}")

    def evaluate_performance(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Looks for recommendations from 'days' ago and checks current price.
        Returns a list of evaluated results.
        """
        df = pd.read_csv(self.db_path)
        if df.empty:
            return []

        target_date = (self._get_taiwan_now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Find pending evaluations from target_date or older
        pending = df[(df['date'] <= target_date) & (df['evaluated'] == False)].copy()
        
        if pending.empty:
            return []

        tickers = pending['ticker'].unique().tolist()
        logger.info(f"Evaluating performance for {len(tickers)} tickers from {target_date}...")
        
        # Download current data
        current_data = download_market_data(tickers, period="1d")
        
        results = []
        for index, row in pending.iterrows():
            ticker = row['ticker']
            try:
                # Extract current price
                if len(tickers) == 1:
                    price_now = current_data['Close'].iloc[-1]
                else:
                    price_now = current_data[ticker]['Close'].iloc[-1]
                
                entry_price = float(row['entry_price'])
                return_pct = ((price_now - entry_price) / entry_price) * 100
                
                # Update main dataframe
                df.at[index, 'exit_price'] = price_now
                df.at[index, 'return_pct'] = return_pct
                df.at[index, 'evaluated'] = True
                
                results.append({
                    'date': row['date'],
                    'ticker': ticker,
                    'name': row['name'],
                    'entry': entry_price,
                    'current': price_now,
                    'return': return_pct
                })
            except Exception as e:
                logger.error(f"Error evaluating {ticker}: {e}")

        df.to_csv(self.db_path, index=False)
        return results
