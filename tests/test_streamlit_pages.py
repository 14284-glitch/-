from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_stock_analysis_tabs_load_without_exceptions():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    app.sidebar.radio[0].set_value("個股分析")
    app.run(timeout=30)
    assert not app.exception
    labels = [tab.label for tab in app.tabs]
    assert "技術面" in labels
    assert "股息與試算" in labels
    assert "基本面" in labels
    assert "籌碼面" in labels


def test_dividend_calculator_inputs_update_real_results():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    app.sidebar.radio[0].set_value("個股分析")
    app.run(timeout=30)

    inputs = {widget.label: widget for widget in app.number_input}
    inputs["持有股數"].set_value(250.0)
    inputs["每股現金股利"].set_value(4.0)
    inputs["每股買進成本"].set_value(80.0)
    inputs["目前股價"].set_value(100.0)
    inputs["預估所得稅率（%）"].set_value(10.0)
    app.run(timeout=30)

    metrics = {metric.label: metric.value for metric in app.metric}
    assert not app.exception
    assert metrics["持有張數"] == "0.250張"
    assert metrics["持有股數"] == "250股"
    assert metrics["預估現金股息"] == "NT$ 1,000.00"
    assert metrics["預估所得稅"] == "NT$ 100.00"
    assert metrics["預估實領股息"] == "NT$ 900.00"
    assert metrics["成本殖利率"] == "5.00%"
    assert metrics["目前殖利率"] == "4.00%"


def test_standalone_dividend_page_is_in_sidebar_and_interactive():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    options = app.sidebar.radio[0].options
    assert "股息分析" in options

    app.sidebar.radio[0].set_value("股息分析")
    app.run(timeout=30)
    assert not app.exception
    assert any(header.value == "股息分析與試算" for header in app.header)

    inputs = {widget.label: widget for widget in app.number_input}
    inputs["持有股數"].set_value(125.0)
    inputs["每股現金股利"].set_value(3.0)
    app.run(timeout=30)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["預估現金股息"] == "NT$ 375.00"


def test_backtest_page_executes_and_exposes_results_and_exports():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60).run()
    app.sidebar.radio[0].set_value("策略回測")
    app.run(timeout=60)
    assert not app.exception
    run_buttons = [button for button in app.button if button.label == "執行回測"]
    assert len(run_buttons) == 1
    run_buttons[0].click()
    app.run(timeout=60)
    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert {"最終資產", "總報酬率", "最大回撤", "勝率", "Profit Factor"} <= set(metrics)
    downloads = {button.label for button in app.get("download_button")}
    assert {"匯出交易紀錄CSV", "匯出每日資產曲線CSV"} <= downloads
    delete_buttons = [button for button in app.button if button.label == "刪除本次回測紀錄"]
    assert len(delete_buttons) == 1
    assert delete_buttons[0].disabled
    confirmations = [
        checkbox for checkbox in app.checkbox
        if checkbox.label == "我確認要刪除目前的策略回測紀錄"
    ]
    assert len(confirmations) == 1
    confirmations[0].set_value(True)
    app.run(timeout=60)
    delete_buttons = [button for button in app.button if button.label == "刪除本次回測紀錄"]
    assert not delete_buttons[0].disabled
    delete_buttons[0].click()
    app.run(timeout=60)
    assert not app.exception
    assert "backtest_result" not in app.session_state
