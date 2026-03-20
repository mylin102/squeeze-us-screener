import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging
from squeeze.data.downloader import download_market_data

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """
    Tracks recommendations daily for 14 days and evaluates their performance.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _get_taiwan_now(self) -> datetime:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    def _init_db(self):
        if not self.db_path.exists():
            df = pd.DataFrame(columns=[
                'date', 'ticker', 'name', 'entry_price', 'signal', 
                'current_price', 'return_pct', 'days_tracked', 'last_updated', 'status'
            ])
            df.to_csv(self.db_path, index=False)

    def record_recommendations(self, results: List[Dict[str, Any]]):
        """Records new potential buy signals."""
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
                'current_price': r.get('Close'),
                'return_pct': 0.0,
                'days_tracked': 0,
                'last_updated': now_str,
                'status': 'tracking'
            })
        
        df_new = pd.DataFrame(new_records)
        try:
            df_old = pd.read_csv(self.db_path)
        except Exception:
            self._init_db()
            df_old = pd.read_csv(self.db_path)
            
        # Avoid duplicate entries for same day/ticker
        df_combined = pd.concat([df_old, df_new]).drop_duplicates(subset=['date', 'ticker'], keep='last')
        df_combined.to_csv(self.db_path, index=False)
        logger.info(f"Recorded {len(new_records)} potential signals to {self.db_path}")

    def update_daily_performance(self) -> List[Dict[str, Any]]:
        """
        Updates current price and returns for all active 'tracking' recommendations.
        Continuous tracking for 14 days.
        """
        df = pd.read_csv(self.db_path)
        if df.empty:
            return []

        # Find entries still in 'tracking' status
        active = df[df['status'] == 'tracking'].copy()
        if active.empty:
            return []

        now = self._get_taiwan_now()
        now_str = now.strftime("%Y-%m-%d")
        
        # Don't update if already updated today
        active = active[active['last_updated'] != now_str]
        if active.empty:
            return []

        tickers = active['ticker'].unique().tolist()
        logger.info(f"Updating performance for {len(tickers)} active tickers...")
        
        # Download current data
        current_data = download_market_data(tickers, period="1d")
        if current_data.empty:
            logger.warning("Could not fetch current market data for performance update.")
            return []
        
        results = []
        for index, row in active.iterrows():
            ticker = row['ticker']
            try:
                # Extract current price
                if len(tickers) == 1:
                    price_now = current_data['Close'].iloc[-1]
                else:
                    # Check if ticker exists in columns
                    if ticker in current_data.columns.get_level_values(0):
                        price_now = current_data[ticker]['Close'].iloc[-1]
                    else:
                        continue
                
                entry_price = float(row['entry_price'])
                return_pct = ((price_now - entry_price) / entry_price) * 100
                
                # Calculate days since recommendation
                rec_date = datetime.strptime(row['date'], "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8)))
                days_passed = (now - rec_date).days
                
                # Update record
                df.at[index, 'current_price'] = price_now
                df.at[index, 'return_pct'] = return_pct
                df.at[index, 'days_tracked'] = days_passed
                df.at[index, 'last_updated'] = now_str
                
                if days_passed >= 14:
                    df.at[index, 'status'] = 'completed'
                
                results.append({
                    'date': row['date'],
                    'ticker': ticker,
                    'name': row['name'],
                    'entry': entry_price,
                    'current': price_now,
                    'return': return_pct,
                    'days': days_passed
                })
            except Exception as e:
                logger.error(f"Error updating performance for {ticker}: {e}")

        df.to_csv(self.db_path, index=False)
        return results

    def get_active_tracking_list(self) -> List[Dict[str, Any]]:
        """Returns all currently tracking recommendations for the report."""
        df = pd.read_csv(self.db_path)
        if df.empty:
            return []
        
        # Return all that are not completed, or completed within the last 2 days for visibility
        # For simplicity, just return everything still being tracked
        active = df[df['status'] == 'tracking'].sort_values(by='date', ascending=False)
        return active.to_dict('records')
