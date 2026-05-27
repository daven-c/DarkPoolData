import marimo

__generated_with = "0.23.8"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import httpx
    import os
    import sys
    import json
    import io
    from dotenv import load_dotenv

    # Load environmental variables (in case the user wants to use env interpolation or reference)
    load_dotenv(dotenv_path="../.env")
    api_key = os.getenv("MASSIVE_API_KEY")

    return api_key, httpx, io, json, mo, os, pd


@app.cell
def _(api_key, mo):
    mo.md(
        r"""
        # 📡 Universal Endpoint Fetcher & Viewer
        Enter an API URL to fetch and download tick records, or browse and inspect existing local datasets saved in the `data/` folder.
        """
    )

    # Show helper tip with API key from .env to make copy-pasting easier for the user
    if api_key and not api_key.startswith("YOUR_"):
        mo.md(f"💡 **Your MASSIVE_API_KEY is configured:** `{api_key}`\n\n*Use it in your URL as a parameter: `&apiKey={api_key}`*")
    else:
        mo.md("⚠️ **Warning:** No valid API key found in root `.env`.")
    return


@app.cell
def _(mo):
    # Mode selector - Download vs View Existing
    mode_selector = mo.ui.radio(
        options=["Download Data", "View Existing Data"],
        value="Download Data",
        label="Select Action Mode"
    )

    mode_selector
    return (mode_selector,)


@app.cell
def _(api_key, mo, mode_selector):
    # Render API downloader widgets only in API mode
    if mode_selector.value != "Download Data":
        url_input = None
        filename_input = None
        fetch_btn = None
        downloader_panel = mo.md("")
    else:
        default_url = f"" if api_key else ""

        url_input = mo.ui.text(value=default_url, label="API Endpoint URL", placeholder="https://api.example.com/data")
        filename_input = mo.ui.text(value="data", label="Save Filename (without extension)")
        fetch_btn = mo.ui.run_button(label="📥 Fetch and Save Endpoint Response", kind="success")

        downloader_panel = mo.vstack([
            mo.md("### ⚡ API Data Fetcher"),
            url_input,
            filename_input,
            fetch_btn
        ])

    downloader_panel
    return fetch_btn, filename_input, url_input


@app.cell
def _(mo, mode_selector, os):
    # Render local file selection only in Local file mode
    data_dir = os.path.abspath(os.path.join(os.getcwd(), "../data"))

    if mode_selector.value != "View Existing Data":
        file_dropdown = None
        local_files = []
        loader_panel = mo.md("")
    else:
        local_files = []
        if os.path.exists(data_dir):
            local_files = [f for f in os.listdir(data_dir) if f.endswith(".csv") or f.endswith(".json")]

        local_files.sort()

        if not local_files:
            file_dropdown = None
            loader_panel = mo.md("⚠️ No CSV/JSON datasets found in the `data/` directory. Switch to download mode to fetch one!")
        else:
            file_dropdown = mo.ui.dropdown(options=local_files, label="📂 Select Dataset")
            loader_panel = mo.vstack([
                mo.md("### 📂 Local File Loader"),
                file_dropdown
            ])

    loader_panel
    return data_dir, file_dropdown


@app.cell
def _(
    data_dir,
    fetch_btn,
    file_dropdown,
    filename_input,
    httpx,
    io,
    json,
    mo,
    mode_selector,
    os,
    pd,
    url_input,
):
    df_active = None
    status_card = mo.md("")
    filepath = None
    json_data = None
    save_filepath = None
    selected_file = None

    # 1. Download Mode
    if mode_selector.value == "Download Data" and fetch_btn and fetch_btn.value:
        url = url_input.value.strip()
        save_name = filename_input.value.strip()

        if not url:
            status_card = mo.md("❌ **Error:** URL endpoint cannot be empty.")
        elif not save_name:
            status_card = mo.md("❌ **Error:** Save filename cannot be empty.")
        else:
            status_card = mo.md(f"Requesting data from: `{url}`...")
            try:
                res = httpx.get(url, timeout=10.0)

                if res.status_code != 200:
                    status_card = mo.md(f"❌ **Request Failed:** Received status code `{res.status_code}`.\n\n*Response:* {res.text[:300]}")
                else:
                    content_type = res.headers.get("content-type", "")

                    # A. Parse JSON Response
                    if "json" in content_type or res.text.strip().startswith("{") or res.text.strip().startswith("["):
                        json_data = res.json()
                        if isinstance(json_data, dict) and "results" in json_data:
                            df_active = pd.json_normalize(json_data["results"])
                        else:
                            df_active = pd.json_normalize(json_data)

                        save_filepath = os.path.join(data_dir, f"{save_name}.json")
                        with open(save_filepath, "w") as f:
                            json.dump(json_data, f, indent=2)

                        status_card = mo.md(
                            f"✅ **JSON Saved & Loaded!**\n\n"
                            f"* **Saved file path:** `data/{save_name}.json`\n"
                            f"* **Records parsed:** {len(df_active):,}"
                        )

                    # B. Parse CSV Response
                    else:
                        df_active = pd.read_csv(io.StringIO(res.text))
                        save_filepath = os.path.join(data_dir, f"{save_name}.csv")
                        df_active.to_csv(save_filepath, index=False)

                        status_card = mo.md(
                            f"✅ **CSV Saved & Loaded!**\n\n"
                            f"* **Saved file path:** `data/{save_name}.csv`\n"
                            f"* **Records parsed:** {len(df_active):,}"
                        )
            except Exception as e:
                status_card = mo.md(f"❌ **Fetch Error:** {str(e)}")

    # 2. View Mode
    elif mode_selector.value == "View Existing Data" and file_dropdown and file_dropdown.value:
        selected_file = file_dropdown.value
        filepath = os.path.join(data_dir, selected_file)

        status_card = mo.md(f"Loading local dataset: `{selected_file}`...")
        try:
            if selected_file.endswith(".json"):
                with open(filepath, "r") as f:
                    json_data = json.load(f)
                if isinstance(json_data, dict) and "results" in json_data:
                    df_active = pd.json_normalize(json_data["results"])
                else:
                    df_active = pd.json_normalize(json_data)
            else: # CSV
                df_active = pd.read_csv(filepath)

            status_card = mo.md(f"✅ Loaded local file `{selected_file}` containing **{len(df_active):,}** records.")
        except Exception as e:
            status_card = mo.md(f"❌ **Load Error:** {str(e)}")

    mo.vstack([
        mo.md("### 📡 Operation Status"),
        status_card
    ])
    return (df_active,)


@app.cell
def _(df_active, mo):
    if df_active is None:
        viewer = mo.md("")
    else:
        viewer = mo.vstack([
            mo.md("### 📋 Response Result Viewer"),
            mo.ui.table(df_active, pagination=True)
        ])

    viewer
    return


@app.cell
def _(df_active):
    # Explore Data in df_active
    df_active.columns
    return


if __name__ == "__main__":
    app.run()
