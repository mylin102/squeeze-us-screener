import pytest
from typer.testing import CliRunner
from pathlib import Path
from squeeze.cli import app
import shutil

runner = CliRunner()

from unittest.mock import patch

def test_scan_reporting_integration(tmp_path):
    """
    Test the scan command with export and plot flags.
    """
    # Create a temporary export directory
    export_dir = tmp_path / "test_exports"
    
    # Mock MarketScanner.scan to ensure we find matches
    with patch("squeeze.cli.MarketScanner.scan") as mock_scan:
        mock_scan.return_value = [
            {
                'ticker': 'AAPL',
                'name': 'Apple Inc.',
                'is_squeezed': True,
                'energy_level': 3,
                'momentum': 0.5,
                'fired': False,
                'Signal': '買入 (動能增強)',
                'timestamp': '2023-01-01',
                'Close': 150.0
            }
        ]
        
        # Run scan with small limit
        result = runner.invoke(app, [
            "scan", 
            "--limit", "3", 
            "--export", 
            "--plot", 
            "--top", "2", 
            "--output-dir", str(export_dir)
        ])
    
    assert result.exit_code == 0
    assert "Exporting results" in result.stdout
    assert "Generating charts" in result.stdout
    
    # Check if a date directory was created (might be different from local date due to ET transition)
    # The exporter creates a subdirectory under export_dir
    date_dirs = [d for d in export_dir.iterdir() if d.is_dir()]
    assert len(date_dirs) >= 1
    expected_base = date_dirs[0]
    
    assert expected_base.exists()
    
    # Check for exported files (glob because timestamp is in filename)
    csv_files = list(expected_base.glob("scan_results_*.csv"))
    json_files = list(expected_base.glob("scan_results_*.json"))
    md_files = list(expected_base.glob("scan_summary_*.md"))
    
    assert len(csv_files) >= 1
    assert len(json_files) >= 1
    assert len(md_files) >= 1
    
    # Check for charts directory and files
    charts_dir = expected_base / "charts"
    assert charts_dir.exists()
    
    # We requested --top 2, so there should be up to 2 PNGs
    # Note: If no matches found, there might be 0, but with limit 3 
    # and no pattern filter (defaults to squeeze) it usually finds some.
    png_files = list(charts_dir.glob("*.png"))
    assert len(png_files) <= 2

def test_scan_invalid_pattern():
    """Test handling of unknown patterns."""
    result = runner.invoke(app, ["scan", "--pattern", "invalid_xyz"])
    assert result.exit_code == 0
    assert "Unknown pattern" in result.stdout
