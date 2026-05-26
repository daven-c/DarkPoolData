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

    from backtester import MockDataProvider, APIDataProvider, Portfolio, BacktestEngine, DarkPoolSpikeStrategy

    return (
        BacktestEngine,
        DarkPoolSpikeStrategy,
        MockDataProvider,
        Portfolio,
        alt,
        mo,
        pd,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # 📈 Dark Pool Exploration & Backtester
    Use this interactive Marimo notebook to explore dark pool parameters and simulate institutional block trading strategies.
    """)
    return


@app.cell
def _(mo):
    # Form widgets
    ticker_input = mo.ui.text(value="AAPL", label="Stock Ticker")
    start_date_input = mo.ui.text(value="2026-01-01", label="Start Date (YYYY-MM-DD)")
    end_date_input = mo.ui.text(value="2026-05-20", label="End Date (YYYY-MM-DD)")

    threshold_slider = mo.ui.slider(start=0.1, stop=0.9, step=0.05, value=0.40, label="Dark Pool Ratio Threshold")
    holding_slider = mo.ui.number(start=1, stop=30, step=1, value=5, label="Holding Period (Days)")

    run_btn = mo.ui.run_button(label="Run Strategy Backtest", kind="success")

    inputs_grid = mo.vstack([
        mo.md("### ⚙️ Strategy & Simulation Settings"),
        mo.hstack([ticker_input, start_date_input, end_date_input]),
        mo.hstack([threshold_slider, holding_slider]),
        run_btn
    ])

    inputs_grid
    return (
        end_date_input,
        holding_slider,
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
    Portfolio,
    end_date_input,
    holding_slider,
    run_btn,
    start_date_input,
    threshold_slider,
    ticker_input,
):
    # Execute the backtest on button press
    if not run_btn.value:
        res = None
        portfolio = None
    else:
        # Load strategy
        strategy = DarkPoolSpikeStrategy({
            "dark_ratio_threshold": threshold_slider.value,
            "holding_period": holding_slider.value
        })

        # Load mock data provider (to run locally without polygon/massive api key)
        provider = MockDataProvider(
            symbols=[ticker_input.value],
            start_date=start_date_input.value,
            end_date=end_date_input.value
        )

        portfolio = Portfolio(initial_cash=100000.0)
        engine = BacktestEngine(data_provider=provider, strategy=strategy, portfolio=portfolio)
        res = engine.run()

    return portfolio, res


@app.cell
def _(mo, res):
    # Output metrics
    if res is None:
        metrics_output = mo.md("Set your inputs above and click **Run Strategy Backtest** to view results.")
    else:
        c1 = mo.stat(value=f"${res['final_value']:.2f}", label="Final Portfolio Value")
        c2 = mo.stat(value=f"{res['total_return']*100:.2f}%", label="Total Return", inverse=res['total_return'] < 0)
        c3 = mo.stat(value=f"{res['max_drawdown']*100:.2f}%", label="Max Drawdown", inverse=True)
        c4 = mo.stat(value=f"{res['sharpe_ratio']:.2f}", label="Sharpe Ratio")

        metrics_output = mo.vstack([
            mo.md("### 📊 Performance Summary"),
            mo.hstack([c1, c2, c3, c4]),
            mo.md(f"**Total trades executed:** {res['total_trades']} | **Remaining cash:** ${res['remaining_cash']:.2f}")
        ])

    metrics_output
    return


@app.cell
def _(alt, mo, pd, portfolio, res):
    # Render equity curve chart
    if res is None or portfolio is None or not portfolio.equity_history:
        chart_output = mo.md("")
    else:
        df_eq = pd.DataFrame(portfolio.equity_history)

        # Create Altair plot
        chart = alt.Chart(df_eq).mark_line(color="#8884d8", strokeWidth=2).encode(
            x=alt.X('timestamp:T', title='Timeline'),
            y=alt.Y('total_value:Q', title='Portfolio Equity ($)', scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip('timestamp:T', title='Date'), alt.Tooltip('total_value:Q', title='Equity', format='$,.2f')]
        ).properties(
            width=700,
            height=300,
            title="Equity Growth Curve"
        ).configure_title(
            fontSize=16,
            anchor='start',
            color='#111'
        )

        chart_output = mo.vstack([
            mo.md("### 📈 Equity History Plot"),
            mo.as_html(chart)
        ])

    chart_output
    return


@app.cell
def _(mo, pd, portfolio, res):
    # Render trades table
    if res is None or portfolio is None:
        trades_output = mo.md("")
    elif not portfolio.trades:
        trades_output = mo.md("No trades were executed with current threshold.")
    else:
        df_trades = pd.DataFrame(portfolio.trades)
        # Format timestamps nicely
        df_trades["timestamp"] = df_trades["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        trades_table = mo.ui.table(df_trades, pagination=True)
        trades_output = mo.vstack([
            mo.md("### 📑 Transaction Log"),
            trades_table
        ])

    trades_output
    return


if __name__ == "__main__":
    app.run()
