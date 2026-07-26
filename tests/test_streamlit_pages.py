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
