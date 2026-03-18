# Roadmap: Squeeze Stock Screener

## Phase 1: Core Engine & Data (Foundation)
**Goal**: Build the infrastructure to fetch Taiwan stock data and calculate Squeeze indicators.
**Plans:** 3 plans
- [ ] 01-01-PLAN.md — Project scaffolding and ISIN ticker discovery.
- [ ] 01-02-PLAN.md — Optimized data downloader with caching.
- [ ] 01-03-PLAN.md — Refactored indicator engine using pandas-ta.

- [ ] 1.1 Project scaffolding (directory structure, dependencies).
- [ ] 1.2 Implement Taiwan ticker fetching (TWSE/TPEx).
- [ ] 1.3 Implement historical data downloader (optimized for bulk fetching).
- [ ] 1.4 Refactor `PowerSqueezeIndicator` from `squeeze.py` into a reusable module.
- [ ] 1.5 Unit tests for indicator accuracy.

## Phase 2: Screener & Pattern Logic
**Goal**: Implement the logic to scan the market and identify specific patterns.
- [ ] 2.1 Implement basic Squeeze screener (All stocks currently in Squeeze).
- [ ] 2.2 Implement "Houyi Shooting the Sun" pattern detection.
- [ ] 2.3 Implement Multi-Timeframe (Daily + Weekly) "Whale Trading" logic.
- [ ] 2.4 Performance optimization for full market scan.

## Phase 3: Reporting & Visualization
**Goal**: Generate user-friendly outputs and charts.
- [ ] 3.1 Implement CSV/JSON report generation.
- [ ] 3.2 Implement automated chart generation for top picks using `matplotlib`.
- [ ] 3.3 Create a CLI command to run specific screens (e.g., `--pattern houyi`).

## Phase 4: Automation & Deployment
**Goal**: Set up scheduled runs and historical tracking.
- [ ] 4.1 Configure GitHub Actions workflow for daily execution.
- [ ] 4.2 Implement historical result persistence.
- [ ] 4.3 (Optional) Integration with Line Bot for notifications (from Phase 3 logic).

## Phase 5: Refinement & Fundamentals
**Goal**: Add advanced filtering and improve reliability.
- [ ] 5.1 Integrate fundamental data filtering (e.g., volume thresholds, price filters).
- [ ] 5.2 Improve error handling and retry logic for data providers.
- [ ] 5.3 Final documentation and user guide.
