#!/usr/bin/env python3
"""
Pixel Data Visualizer for Mill Stand Analysis
==============================================
Visualizes pixel data from CSV using Plotly interactive graphs.
Displays statistics table for both absolute pixel counts and ratios.

Usage:
    python scripts/visualize_pixels.py                    # Use default pixel_log.csv
    python scripts/visualize_pixels.py --input data/pixel_log.csv
    python scripts/visualize_pixels.py --threshold 10000  # Add pixel threshold line
    python scripts/visualize_pixels.py --ratio-threshold 0.15  # Add ratio threshold line
"""

import csv
import sys
import argparse
from pathlib import Path
from typing import List, Dict
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    print("Error: plotly is not installed.")
    print("Install it with: pip install plotly")
    sys.exit(1)


def load_csv(file_path: str) -> List[Dict]:
    """Load pixel data from CSV file."""
    data = []
    with open(file_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = {
                "frame": int(row["frame"]),
                "timestamp_sec": float(row["timestamp_sec"]),
                "timestamp_str": row["timestamp_str"],
                "left_pixels": int(row["left_pixels"]),
                "right_pixels": int(row["right_pixels"]),
                "left_brightness": float(row["left_brightness"]),
                "right_brightness": float(row["right_brightness"]),
            }
            # Handle ratio fields (may not exist in old CSV files)
            if "left_ratio" in row:
                entry["left_ratio"] = float(row["left_ratio"])
                entry["right_ratio"] = float(row["right_ratio"])
                entry["left_total"] = int(row["left_total"])
                entry["right_total"] = int(row["right_total"])
            else:
                # Calculate ratio if total is not available (estimate from config)
                entry["left_ratio"] = 0.0
                entry["right_ratio"] = 0.0
                entry["left_total"] = 0
                entry["right_total"] = 0
            data.append(entry)
    return data


def calculate_statistics(values: List, label: str, is_ratio: bool = False) -> Dict:
    """Calculate statistics for a list of values."""
    arr = np.array(values)
    if is_ratio:
        return {
            "label": label,
            "count": len(arr),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "std": float(np.std(arr)),
            "p25": float(np.percentile(arr, 25)),
            "p50": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)),
            "p85": float(np.percentile(arr, 85)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
        }
    else:
        return {
            "label": label,
            "count": len(arr),
            "min": int(np.min(arr)),
            "max": int(np.max(arr)),
            "mean": int(np.mean(arr)),
            "median": int(np.median(arr)),
            "std": int(np.std(arr)),
            "p25": int(np.percentile(arr, 25)),
            "p50": int(np.percentile(arr, 50)),
            "p75": int(np.percentile(arr, 75)),
            "p85": int(np.percentile(arr, 85)),
            "p90": int(np.percentile(arr, 90)),
            "p95": int(np.percentile(arr, 95)),
        }


def print_statistics_table(
    left_pixel_stats: Dict,
    right_pixel_stats: Dict,
    left_ratio_stats: Dict,
    right_ratio_stats: Dict,
    pixel_threshold: int,
    ratio_threshold: float,
):
    """Print statistics tables to console."""
    print()
    print("=" * 110)
    print("PIXEL COUNT STATISTICS (Absolute)")
    print("=" * 110)
    print()

    # Header for pixel stats
    header = f"{'Zone':<10} | {'Count':>7} | {'Min':>8} | {'Max':>8} | {'Mean':>8} | {'Median':>8} | {'Std':>8} | {'P75':>8} | {'P85':>8} | {'P95':>8}"
    print(header)
    print("-" * len(header))

    # Data rows
    for stats in [left_pixel_stats, right_pixel_stats]:
        row = f"{stats['label']:<10} | {stats['count']:>7,} | {stats['min']:>8,} | {stats['max']:>8,} | {stats['mean']:>8,} | {stats['median']:>8,} | {stats['std']:>8,} | {stats['p75']:>8,} | {stats['p85']:>8,} | {stats['p95']:>8,}"
        print(row)

    print()
    print(f"Pixel threshold: {pixel_threshold:,} pixels")
    print(
        f"  - LEFT P85: {left_pixel_stats['p85']:,} | RIGHT P85: {right_pixel_stats['p85']:,}"
    )

    # Ratio statistics
    print()
    print("=" * 110)
    print("RATIO STATISTICS (bright_pixels / total_pixels)")
    print("=" * 110)
    print()

    # Header for ratio stats
    header = f"{'Zone':<10} | {'Count':>7} | {'Min':>8} | {'Max':>8} | {'Mean':>8} | {'Median':>8} | {'Std':>8} | {'P75':>8} | {'P85':>8} | {'P95':>8}"
    print(header)
    print("-" * len(header))

    # Data rows for ratio
    for stats in [left_ratio_stats, right_ratio_stats]:
        row = f"{stats['label']:<10} | {stats['count']:>7,} | {stats['min']:>8.4f} | {stats['max']:>8.4f} | {stats['mean']:>8.4f} | {stats['median']:>8.4f} | {stats['std']:>8.4f} | {stats['p75']:>8.4f} | {stats['p85']:>8.4f} | {stats['p95']:>8.4f}"
        print(row)

    print()
    print(f"Ratio threshold: {ratio_threshold:.4f} ({ratio_threshold * 100:.2f}%)")
    print(
        f"  - LEFT P85: {left_ratio_stats['p85']:.4f} ({left_ratio_stats['p85'] * 100:.2f}%) | RIGHT P85: {right_ratio_stats['p85']:.4f} ({right_ratio_stats['p85'] * 100:.2f}%)"
    )

    # Recommendations
    print()
    print("=" * 110)
    print("THRESHOLD RECOMMENDATIONS")
    print("=" * 110)
    print()
    print("For PIXEL-based threshold:")
    print(f"  - Current: {pixel_threshold:,}")
    print(
        f"  - Suggested (P85): LEFT={left_pixel_stats['p85']:,}, RIGHT={right_pixel_stats['p85']:,}"
    )
    print(
        f"  - Suggested (P90): LEFT={left_pixel_stats['p90']:,}, RIGHT={right_pixel_stats['p90']:,}"
    )
    print()
    print("For RATIO-based threshold:")
    print(f"  - Current: {ratio_threshold:.4f} ({ratio_threshold * 100:.2f}%)")
    print(
        f"  - Suggested (P85): LEFT={left_ratio_stats['p85']:.4f} ({left_ratio_stats['p85'] * 100:.2f}%), RIGHT={right_ratio_stats['p85']:.4f} ({right_ratio_stats['p85'] * 100:.2f}%)"
    )
    print(
        f"  - Suggested (P90): LEFT={left_ratio_stats['p90']:.4f} ({left_ratio_stats['p90'] * 100:.2f}%), RIGHT={right_ratio_stats['p90']:.4f} ({right_ratio_stats['p90'] * 100:.2f}%)"
    )
    print("=" * 110)
    print()


def create_visualization(
    data: List[Dict],
    pixel_threshold: int = 10000,
    ratio_threshold: float = 0.15,
    output_html: str = None,
    show: bool = True,
):
    """Create interactive Plotly visualization with both pixel counts and ratios."""

    # Extract data
    timestamps = [d["timestamp_sec"] for d in data]
    timestamp_strs = [d["timestamp_str"] for d in data]
    left_pixels = [d["left_pixels"] for d in data]
    right_pixels = [d["right_pixels"] for d in data]
    left_ratio = [d["left_ratio"] for d in data]
    right_ratio = [d["right_ratio"] for d in data]
    left_brightness = [d["left_brightness"] for d in data]
    right_brightness = [d["right_brightness"] for d in data]

    # Check if ratio data is available
    has_ratio = any(r > 0 for r in left_ratio) or any(r > 0 for r in right_ratio)

    # Calculate statistics
    left_pixel_stats = calculate_statistics(left_pixels, "LEFT", is_ratio=False)
    right_pixel_stats = calculate_statistics(right_pixels, "RIGHT", is_ratio=False)

    if has_ratio:
        left_ratio_stats = calculate_statistics(left_ratio, "LEFT", is_ratio=True)
        right_ratio_stats = calculate_statistics(right_ratio, "RIGHT", is_ratio=True)
    else:
        left_ratio_stats = {"label": "LEFT", "p85": 0, "p90": 0}
        right_ratio_stats = {"label": "RIGHT", "p85": 0, "p90": 0}

    # Print statistics table
    print_statistics_table(
        left_pixel_stats,
        right_pixel_stats,
        left_ratio_stats,
        right_ratio_stats,
        pixel_threshold,
        ratio_threshold,
    )

    # Create figure with 3 rows
    num_rows = 3 if has_ratio else 2
    row_heights = [0.4, 0.4, 0.2] if has_ratio else [0.7, 0.3]
    subplot_titles = (
        ["Pixel Counts (Absolute)", "Ratio (bright/total)", "Brightness"]
        if has_ratio
        else ["Pixel Counts (Absolute)", "Brightness"]
    )

    fig = make_subplots(
        rows=num_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=subplot_titles,
        row_heights=row_heights,
    )

    # --- Row 1: Pixel counts ---
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=left_pixels,
            mode="lines",
            name="LEFT Pixels",
            line=dict(color="#2ecc71", width=1.5),
            hovertemplate="<b>LEFT</b><br>Time: %{text}<br>Pixels: %{y:,}<extra></extra>",
            text=timestamp_strs,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=right_pixels,
            mode="lines",
            name="RIGHT Pixels",
            line=dict(color="#e74c3c", width=1.5),
            hovertemplate="<b>RIGHT</b><br>Time: %{text}<br>Pixels: %{y:,}<extra></extra>",
            text=timestamp_strs,
        ),
        row=1,
        col=1,
    )

    # Pixel threshold line
    fig.add_trace(
        go.Scatter(
            x=[timestamps[0], timestamps[-1]],
            y=[pixel_threshold, pixel_threshold],
            mode="lines",
            name=f"Pixel Thresh ({pixel_threshold:,})",
            line=dict(color="#f39c12", width=2, dash="dash"),
            hovertemplate=f"Pixel Threshold: {pixel_threshold:,}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # --- Row 2: Ratios (if available) ---
    if has_ratio:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=left_ratio,
                mode="lines",
                name="LEFT Ratio",
                line=dict(color="#27ae60", width=1.5),
                hovertemplate="<b>LEFT</b><br>Time: %{text}<br>Ratio: %{y:.4f}<extra></extra>",
                text=timestamp_strs,
            ),
            row=2,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=right_ratio,
                mode="lines",
                name="RIGHT Ratio",
                line=dict(color="#c0392b", width=1.5),
                hovertemplate="<b>RIGHT</b><br>Time: %{text}<br>Ratio: %{y:.4f}<extra></extra>",
                text=timestamp_strs,
            ),
            row=2,
            col=1,
        )

        # Ratio threshold line
        fig.add_trace(
            go.Scatter(
                x=[timestamps[0], timestamps[-1]],
                y=[ratio_threshold, ratio_threshold],
                mode="lines",
                name=f"Ratio Thresh ({ratio_threshold:.2%})",
                line=dict(color="#9b59b6", width=2, dash="dash"),
                hovertemplate=f"Ratio Threshold: {ratio_threshold:.4f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    # --- Row 3 (or 2): Brightness ---
    brightness_row = 3 if has_ratio else 2

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=left_brightness,
            mode="lines",
            name="LEFT Bright",
            line=dict(color="#2ecc71", width=1),
            hovertemplate="<b>LEFT</b><br>Brightness: %{y:.1f}<extra></extra>",
            showlegend=False,
        ),
        row=brightness_row,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=right_brightness,
            mode="lines",
            name="RIGHT Bright",
            line=dict(color="#e74c3c", width=1),
            hovertemplate="<b>RIGHT</b><br>Brightness: %{y:.1f}<extra></extra>",
            showlegend=False,
        ),
        row=brightness_row,
        col=1,
    )

    # Update layout
    fig.update_layout(
        title=dict(
            text="Mill Stand Pixel Analysis (Absolute & Ratio)", font=dict(size=20)
        ),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=800 if has_ratio else 700,
        template="plotly_white",
    )

    # Update axes
    fig.update_xaxes(title_text="Time (seconds)", row=num_rows, col=1)
    fig.update_yaxes(title_text="Pixel Count", row=1, col=1)
    if has_ratio:
        fig.update_yaxes(title_text="Ratio", row=2, col=1)
    fig.update_yaxes(title_text="Brightness", row=brightness_row, col=1)

    # Add range slider
    fig.update_xaxes(
        rangeslider=dict(visible=True, thickness=0.05), row=num_rows, col=1
    )

    # Save to HTML if requested
    if output_html:
        output_path = Path(output_html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))
        print(f"Interactive graph saved to: {output_html}")

    # Show in browser
    if show:
        print("Opening interactive graph in browser...")
        fig.show()

    return fig


def main():
    parser = argparse.ArgumentParser(
        description="Visualize pixel data from mill stand analysis"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(PROJECT_ROOT / "data" / "pixel_log.csv"),
        help="Input CSV file path",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=10000,
        help="Pixel threshold line value (default: 10000)",
    )
    parser.add_argument(
        "--ratio-threshold",
        type=float,
        default=0.15,
        help="Ratio threshold line value (default: 0.15 = 15%%)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "data" / "pixel_visualization.html"),
        help="Output HTML file path",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Don't open browser, just save HTML",
    )

    args = parser.parse_args()

    # Check input file exists
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        print("Run log_pixel_data.py first to generate the CSV file.")
        sys.exit(1)

    # Load data
    print(f"Loading data from: {args.input}")
    data = load_csv(args.input)
    print(f"Loaded {len(data)} samples")

    # Create visualization
    create_visualization(
        data,
        pixel_threshold=args.threshold,
        ratio_threshold=args.ratio_threshold,
        output_html=args.output,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
