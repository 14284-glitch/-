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
