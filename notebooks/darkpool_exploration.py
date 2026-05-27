import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import altair as alt
    import os
    import sys

    # Add the root directory to path to resolve backtester package
    sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..")))

    from backtester import MockDataProvider, APIDataProvider, BacktestEngine, DarkPoolSpikeStrategy

    return (
        BacktestEngine,
        DarkPoolSpikeStrategy,
        MockDataProvider,
        alt,
        mo,
        pd,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # 📈 Dark Pool Indicator Visualizer
    Use this interactive Marimo notebook to explore stock price movements alongside institutional dark pool volume concentrations and spike alerts.
    """)
    return


@app.cell
def _(mo):
    # Form widgets
    ticker_input = mo.ui.text(value="AAPL", label="Stock Ticker")
    start_date_input = mo.ui.text(value="2026-01-01", label="Start Date (YYYY-MM-DD)")
    end_date_input = mo.ui.text(value="2026-05-20", label="End Date (YYYY-MM-DD)")

    threshold_slider = mo.ui.slider(start=0.1, stop=0.9, step=0.05, value=0.40, label="Dark Pool Ratio Threshold")
    run_btn = mo.ui.run_button(label="Generate Indicator Plot", kind="success")

    inputs_grid = mo.vstack([
        mo.md("### ⚙️ Visualizer Settings"),
        mo.hstack([ticker_input, start_date_input, end_date_input]),
        mo.hstack([threshold_slider]),
        run_btn
    ])

    inputs_grid
    return (
        end_date_input,
        run_btn,
        start_date_input,
        threshold_slider,
        ticker_input,
    )


@app.cell
def _(
    BacktestEngine,
    DarkPoolSpikeStrategy,
    MockDataProvider,
    end_date_input,
    run_btn,
    start_date_input,
    threshold_slider,
    ticker_input,
):
    # Execute the indicator analysis on button press
    if not run_btn.value:
        res = None
    else:
        # Load strategy
        strategy = DarkPoolSpikeStrategy({
            "dark_ratio_threshold": threshold_slider.value
        })

        # Load mock data provider
        provider = MockDataProvider(
            symbols=[ticker_input.value],
            start_date=start_date_input.value,
            end_date=end_date_input.value
        )

        engine = BacktestEngine(data_provider=provider, strategy=strategy, symbol=ticker_input.value)
        res = engine.run()

    return res,


@app.cell
def _(mo, res):
    # Output metrics
    if res is None:
        metrics_output = mo.md("Configure inputs and click **Generate Indicator Plot** to view stats.")
    else:
        c1 = mo.stat(value=f"${res['metrics']['avg_price']:.2f}", label="Average Stock Price")
        c2 = mo.stat(value=f"{res['metrics']['max_indicator']*100:.2f}%", label="Max Dark Pool Ratio")
        c3 = mo.stat(value=str(res['metrics']['total_signals']), label="Triggered Alerts")

        metrics_output = mo.vstack([
            mo.md("### 📊 Indicator Ingestion Summary"),
            mo.hstack([c1, c2, c3])
        ])

    metrics_output
    return


@app.cell
def _(alt, mo, pd, res, threshold_slider, ticker_input):
    # Render dual Y-axis chart (Price left axis, Dark ratio right axis)
    if res is None or not res["series"]:
        chart_output = mo.md("")
    else:
        df_series = pd.DataFrame(res["series"])
        df_series["timestamp"] = pd.to_datetime(df_series["timestamp"])

        # Base timeline encoding
        base = alt.Chart(df_series).encode(
            x=alt.X('timestamp:T', title='Timeline')
        )

        # Price line on left axis (blue)
        price_line = base.mark_line(color='#3b82f6', strokeWidth=2).encode(
            y=alt.Y('price:Q', title='Stock Price ($)', scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip('timestamp:T', title='Date'), alt.Tooltip('price:Q', title='Stock Price', format='$,.2f')]
        )

        # Dark Ratio line on right axis (purple)
        ratio_line = base.mark_line(color='#8b5cf6', strokeWidth=1.5).encode(
            y=alt.Y('indicator_1:Q', title='Dark Pool Ratio', scale=alt.Scale(domain=[0, 1])),
            tooltip=[alt.Tooltip('timestamp:T', title='Date'), alt.Tooltip('indicator_1:Q', title='Dark Ratio', format='.2%')]
        )

        # Spike threshold reference line (red dashed)
        threshold_df = pd.DataFrame({'y': [threshold_slider.value]})
        threshold_rule = alt.Chart(threshold_df).mark_rule(
            color='#ef4444',
            strokeDash=[4, 4]
        ).encode(
            y=alt.Y('y:Q')
        )

        # Build dual axis layered plot
        chart = alt.layer(
            price_line,
            alt.layer(ratio_line, threshold_rule)
        ).resolve_scale(
            y='independent'
        ).properties(
            width=700,
            height=320,
            title=f"Price & Dark Pool Volume Concentrations for {ticker_input.value}"
        )

        chart_output = mo.vstack([
            mo.md("### 📈 Price & Concentrations Over Time"),
            mo.as_html(chart)
        ])

    chart_output
    return


@app.cell
def _(mo, pd, res):
    # Render signals table
    if res is None:
        signals_output = mo.md("")
    elif not res["signals"]:
        signals_output = mo.md("No dark pool spikes triggered in this period.")
    else:
        df_signals = pd.DataFrame(res["signals"])
        # Format timestamps nicely for display
        df_signals["timestamp"] = pd.to_datetime(df_signals["timestamp"]).dt.strftime("%Y-%m-%d")
        
        signals_table = mo.ui.table(df_signals, pagination=True)
        signals_output = mo.vstack([
            mo.md("### 🚨 Triggered Indicator Spikes Log"),
            signals_table
        ])

    signals_output
    return


if __name__ == "__main__":
    app.run()
