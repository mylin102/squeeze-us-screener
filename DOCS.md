# Squeeze Stock Screener Technical Documentation v1.2.1 (US Market)

## Overview
This project is a Python-based automated stock scanning system designed to identify high-potential trading opportunities using the Squeeze Momentum indicator and advanced pattern recognition. It covers S&P 500, NASDAQ 100, DJI, and SOX constituents.

## Technical Indicators

### 1. Squeeze Momentum (TTM Squeeze)
*   **Squeeze ON**: Triggered when Bollinger Bands (20, 2.0) are completely inside Keltner Channels (20, 1.5). This indicates low volatility and energy accumulation.
*   **Squeeze Fired**: Triggered when Bollinger Bands break out of Keltner Channels, indicating the start of a trend.
*   **Energy Level**: 
    *   Formula: `(KC_Width - BB_Width) / KC_Width`
    *   Levels: 0 (No Squeeze) to 3 (Extreme Squeeze ★★★).

### 2. Momentum Histogram
*   **Cyan**: Upward trend + increasing strength.
*   **Blue**: Upward trend + decreasing strength.
*   **Red**: Downward trend + increasing strength.
*   **Maroon**: Downward trend + decreasing strength.

## Pattern Recognition Logic

### 1. Houyi Shooting Sun
Designed for "Strong Stock Pullbacks":
*   Previous rally > 20%.
*   Retracement to 0.5 - 0.618 Fibonacci support zone.
*   Appearance of a "Shooting Star" wick combined with Squeeze ON status.

### 2. Whale Trading
Multi-timeframe alignment:
*   Both Daily and Weekly charts are in Squeeze ON status.
*   Both timeframes have positive momentum (> 0).

## Visualization and Reporting

### Chart Markers
*   **Black Square (⬛)**: Plotted below the zero line on the indicator panel, representing **Squeeze ON**.
*   **Light Gray Square (⬜)**: Represents **Squeeze OFF**.
*   **Positioning**: Fixed below the zero axis to avoid overlap with the momentum histogram.

### Notification System
*   **HTML Email**: Formatted tables with color-coded signals (Green for Buy / Red for Sell).
*   **Attachments**: Automatically includes PNG charts for the top 15 candidates.
*   **LINE Notification**: Real-time summary of scan results and tracking performance.

## Project Structure
*   `src/squeeze/data/`: Data acquisition (yfinance, Wikipedia scrapers).
*   `src/squeeze/engine/`: Core analytics (Indicators, Patterns).
*   `src/squeeze/report/`: Reporting and Notifications (Jinja2, SMTP, LINE).
*   `recommendations.csv`: Tracking database (limited to latest 25 picks).
