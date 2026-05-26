import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import os
    import sys
    from polygon import RESTClient

    # Add parent directory to resolve backend settings config if needed
    sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..")))

    try:
        from backend.app.core.config import settings
        default_api_key = settings.MASSIVE_API_KEY
    except Exception:
        default_api_key = ""

    return RESTClient, default_api_key, mo, os, pd


@app.cell
def _(mo):
    mo.md(r"""
    # 📥 Massive.com CSV Data Downloader & Viewer
    This notebook allows you to download historical trade-level tick data (including FINRA TRF off-exchange/dark pool trades) directly from Massive.com and save it locally as CSV files in the `data/` folder. It also provides an interactive viewer to inspect and analyze saved data.
    """)
    return


@app.cell
def _(default_api_key, mo):
    # Form controls for Downloading
    api_key_input = mo.ui.text(value=default_api_key, label="Massive.com API Key", password=True)
    ticker_input = mo.ui.text(value="AAPL", label="Ticker Symbol")
    date_input = mo.ui.text(value="2026-05-22", label="Date (YYYY-MM-DD)")

    download_btn = mo.ui.run_button(label="Download & Save Trades to CSV", kind="success")

    downloader_grid = mo.vstack([
        mo.md("### ⚡ Download Data from API"),
        api_key_input,
        mo.hstack([ticker_input, date_input]),
        download_btn
    ])

    downloader_grid
    return api_key_input, date_input, download_btn, ticker_input


@app.cell
def _(
    RESTClient,
    api_key_input,
    date_input,
    download_btn,
    mo,
    os,
    pd,
    ticker_input,
):
    # Download Execution Logic
    if not download_btn.value:
        download_status = mo.md("")
    else:
        if not api_key_input.value or api_key_input.value.startswith("YOUR_"):
            download_status = mo.md("❌ **Error:** Please enter a valid Massive.com API Key.")
        else:
            ticker = ticker_input.value.upper().strip()
            target_date = date_input.value.strip()

            download_status = mo.md(f"Ingesting trades for **{ticker}** on **{target_date}**...")

            try:
                client = RESTClient(api_key=api_key_input.value)

                # Fetch trades
                trades_iter = client.list_trades(
                    ticker=ticker,
                    timestamp_gte=f"{target_date}T00:00:00Z",
                    timestamp_lte=f"{target_date}T23:59:59Z",
                    limit=50000
                )

                trade_records = []
                for t in trades_iter:
                    ts_ns = getattr(t, "participant_timestamp", getattr(t, "sip_timestamp", 0))
                    ts = pd.to_datetime(ts_ns, unit="ns", utc=True).tz_convert("US/Eastern")

                    trade_records.append({
                        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S.%f"),
                        "price": t.price,
                        "size": t.size,
                        "exchange": t.exchange,
                        "is_dark_pool": t.exchange == 4,
                        "trf_id": getattr(t, "trf_id", None)
                    })

                if not trade_records:
                    download_status = mo.md(f"⚠️ No trades found for {ticker} on {target_date}.")
                else:
                    df = pd.DataFrame(trade_records)

                    # Ensure data directory exists
                    data_dir = os.path.abspath(os.path.join(os.getcwd(), "../data"))
                    os.makedirs(data_dir, exist_ok=True)

                    filename = f"{ticker}_{target_date}_trades.csv"
                    filepath = os.path.join(data_dir, filename)

                    # Save to CSV
                    df.to_csv(filepath, index=False)

                    download_status = mo.md(
                        f"✅ **Success!** Downloaded **{len(df):,}** trades for **{ticker}**.\n\n"
                        f"Saved file to: `data/{filename}`"
                    )
            except Exception as e:
                download_status = mo.md(f"❌ **API Error:** {str(e)}")

    download_status
    return


@app.cell
def _(mo, os):
    # CSV file scanner
    data_dir_path = os.path.abspath(os.path.join(os.getcwd(), "../data"))

    csv_files = []
    if os.path.exists(data_dir_path):
        csv_files = [f for f in os.listdir(data_dir_path) if f.endswith(".csv")]

    csv_files.sort()

    if not csv_files:
        file_selector = mo.md("No CSV files found in the `data/` directory. Download one above first!")
    else:
        file_selector = mo.ui.dropdown(options=csv_files, label="📂 Select Local CSV File to View")

    mo.vstack([
        mo.md("### 📊 Local File Explorer & Viewer"),
        file_selector
    ])
    return csv_files, data_dir_path, file_selector


@app.cell
def _(csv_files, data_dir_path, file_selector, mo, os, pd):
    # Load and View selected CSV
    if not csv_files or not file_selector.value:
        viewer_output = mo.md("")
    else:
        selected_file = file_selector.value
        csv_path = os.path.join(data_dir_path, selected_file)

        try:
            df_local = pd.read_csv(csv_path)

            # Aggregate stats
            tot_rows = len(df_local)
            tot_vol = df_local["size"].sum()

            # exchange=4 or is_dark_pool column
            dark_df = df_local[df_local["is_dark_pool"] == True]
            dark_vol = dark_df["size"].sum()
            dark_ratio = (dark_vol / tot_vol) if tot_vol > 0 else 0.0

            s1 = mo.stat(value=f"{tot_rows:,}", label="Total Trades")
            s2 = mo.stat(value=f"{tot_vol:,.0f}", label="Total Volume (Shares)")
            s3 = mo.stat(value=f"{dark_ratio*100:.2f}%", label="Dark Pool Ratio")
            s4 = mo.stat(value=f"${df_local['price'].mean():.2f}", label="Avg Trade Price")

            viewer_output = mo.vstack([
                mo.md(f"#### 🔍 Summary of `{selected_file}`"),
                mo.hstack([s1, s2, s3, s4]),
                mo.md("##### 📋 Trade Log Preview"),
                mo.ui.table(df_local.head(100), pagination=True)
            ])
        except Exception as e:
            viewer_output = mo.md(f"❌ **Error reading file:** {str(e)}")

    viewer_output
    return (df_local,)


@app.cell
def _(csv_files, df_local, file_selector, mo):
    # Charting price timeline
    if not csv_files or not file_selector.value or 'df_local' not in locals():
        chart_view = mo.md("")
    else:
        import altair as alt

        # Resample or limit points to prevent Altair from bloating
        sample_df = df_local.sample(n=min(2000, len(df_local))).sort_values("timestamp")

        chart = alt.Chart(sample_df).mark_circle(size=8, opacity=0.4).encode(
            x=alt.X('timestamp:T', title='Timeline'),
            y=alt.Y('price:Q', title='Execution Price ($)', scale=alt.Scale(zero=False)),
            color=alt.Color('is_dark_pool:N', title='Dark Pool Trade', scale=alt.Scale(range=['#3b82f6', '#8b5cf6'])),
            tooltip=['timestamp:T', 'price:Q', 'size:Q']
        ).properties(
            width=700,
            height=300,
            title="Price Distribution & Off-Exchange Transactions"
        )

        chart_view = mo.vstack([
            mo.md("##### 📈 Price Distribution Chart"),
            mo.as_html(chart)
        ])

    chart_view
    return


if __name__ == "__main__":
    app.run()
