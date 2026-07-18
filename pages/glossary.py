"""Reusable right-side interactive legends and Chinese explanation panels."""

from dataclasses import dataclass
from html import escape

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from config.color_config import COLORS, LINE_STYLES, PLOTLY_CONFIG
from config.indicator_glossary import INDICATOR_GLOSSARY


@dataclass(frozen=True)
class LegendItem:
    key: str
    english: str
    color: str
    line_style: str = "solid"
    focus: str = ""


def render_chart_with_legend(figure: go.Figure, items: tuple[LegendItem, ...], date_key: str) -> None:
    """Render a chart with an accessible hover/focus explanation legend on its right."""
    figure.update_layout(showlegend=False)
    all_dates = []
    for trace in figure.data:
        if getattr(trace, "x", None) is not None:
            all_dates.extend(list(trace.x))
    valid_dates = pd.to_datetime(pd.Series(all_dates), errors="coerce").dropna()
    if not valid_dates.empty:
        selected_date = st.date_input(
            "指定資訊游標日期", value=valid_dates.max().date(),
            min_value=valid_dates.min().date(), max_value=valid_dates.max().date(),
            format="YYYY/MM/DD", key=f"chart_cursor_{date_key}",
            help="選擇日期後會在圖上標出該日，並顯示當日主要數值；不會改變圖表範圍。",
        )
        selected_timestamp = pd.Timestamp(selected_date)
        figure.add_shape(
            type="line", x0=selected_timestamp, x1=selected_timestamp, y0=0, y1=1,
            xref="x", yref="paper", line=dict(color=COLORS["layout"]["date_cursor"], width=3, dash="dot"),
        )
        figure.add_annotation(
            x=selected_timestamp, y=1, xref="x", yref="paper", text=f"資訊日期 {selected_date:%Y/%m/%d}",
            showarrow=True, arrowcolor=COLORS["layout"]["date_cursor"], bgcolor=COLORS["layout"]["tooltip_background"],
            bordercolor=COLORS["layout"]["tooltip_border"], font=dict(color=COLORS["layout"]["tooltip_text"]),
        )
        selected_values = _values_for_date(figure, selected_timestamp)
        st.info(f"指定日期：{selected_date:%Y/%m/%d}｜" + "｜".join(selected_values[:6]))
    # The chart receives most of the desktop width; the external legend stays readable on the right.
    chart_column, legend_column = st.columns([84, 16], gap="small", vertical_alignment="top")
    y_minimum, y_maximum = _figure_y_bounds(figure)
    with legend_column:
        st.markdown("#### 顯示範圍")
        if y_minimum is not None and y_maximum is not None:
            span = y_maximum - y_minimum
            padding_percent = st.slider(
                "頂點保護留白",
                min_value=2,
                max_value=30,
                value=6,
                step=1,
                key=f"y_range_{date_key}",
                help="調整最高點與最低點外側的留白。資料頂點永遠保留，不會因放大縮小被裁切。",
            )
            padding = max(span * padding_percent / 100, abs(y_maximum) * 0.005, 0.01)
            protected_range = [float(y_minimum - padding), float(y_maximum + padding)]
            figure.update_yaxes(range=protected_range, autorange=False, fixedrange=False)
            st.caption(f"最高點 {y_maximum:,.2f}、最低點 {y_minimum:,.2f} 均受保護")
        else:
            st.caption("本圖沒有可調整的數值範圍。")
    with chart_column:
        figure.update_layout(margin=dict(l=50, r=18, t=70, b=45), autosize=True)
        st.markdown(
            '<div class="mobile-chart-hint">圖表會依手機螢幕寬度自動縮放；下方拉桿可調整日期位置。</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(figure, width="stretch", config=PLOTLY_CONFIG)
    with legend_column:
        st.markdown("#### 本圖圖例")
        st.caption("將滑鼠移到圖例項目，可查看名詞解釋與觀看重點。")
        blocks = []
        for item in items:
            chinese, purpose = INDICATOR_GLOSSARY[item.key]
            explanation = purpose if not item.focus else f"{purpose} 觀看重點：{item.focus}"
            border_style = {"solid": "solid", "dash": "dashed", "dot": "dotted", "dashdot": "dashed"}.get(
                item.line_style, "solid"
            )
            blocks.append(
                f'<div class="legend-help" tabindex="0" aria-label="{escape(item.english)}，{escape(chinese)}。{escape(explanation)}">'
                f'<span class="legend-swatch" style="border-top-color:{escape(item.color)};border-top-style:{border_style}"></span>'
                f'<span><b>{escape(item.english)}</b><br>{escape(chinese)}</span>'
                f'<span class="legend-tip"><b>{escape(chinese)}</b><br>{escape(explanation)}</span></div>'
            )
        st.html(
            "<style>"
            ".legend-help{position:relative;display:flex;align-items:center;gap:.55rem;padding:.45rem .2rem;cursor:help;}"
            ".legend-help:focus{outline:2px solid currentColor;outline-offset:2px;}"
            ".legend-swatch{display:inline-block;width:28px;border-top-width:3px;flex:0 0 auto;}"
            f".legend-tip{{display:none;position:absolute;right:0;top:100%;z-index:20;min-width:240px;"
            f"padding:.65rem;background:{COLORS['layout']['tooltip_background']};"
            f"color:{COLORS['layout']['tooltip_text']};"
            f"border:1px solid {COLORS['layout']['tooltip_border']};border-radius:.35rem;}}"
            ".legend-help:hover .legend-tip,.legend-help:focus .legend-tip{display:block;}"
            "</style>" + "".join(blocks)
        )


def _figure_y_bounds(figure: go.Figure) -> tuple[float | None, float | None]:
    """Return finite visible y bounds for scatter, bar and candlestick traces."""
    values: list[float] = []
    for trace in figure.data:
        if trace.name == "觀看提醒":
            continue
        candidates = []
        for field in ("y", "high", "low"):
            series = getattr(trace, field, None)
            if series is not None:
                candidates.extend(list(series))
        numeric = pd.to_numeric(pd.Series(candidates), errors="coerce").dropna()
        values.extend(float(value) for value in numeric if pd.notna(value))
    if not values:
        return None, None
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        margin = max(abs(minimum) * 0.05, 1.0)
        return minimum - margin, maximum + margin
    return minimum, maximum


def _values_for_date(figure: go.Figure, selected_date: pd.Timestamp) -> list[str]:
    values: list[str] = []
    for trace in figure.data:
        if trace.name == "觀看提醒" or getattr(trace, "x", None) is None:
            continue
        dates = pd.to_datetime(pd.Series(list(trace.x)), errors="coerce")
        matches = dates.dt.normalize() == selected_date.normalize()
        if not matches.any():
            continue
        index = int(matches[matches].index[0])
        series = getattr(trace, "close", None) if trace.type == "candlestick" else getattr(trace, "y", None)
        if series is None or index >= len(series) or pd.isna(series[index]):
            continue
        try:
            values.append(f"{trace.name}：{float(series[index]):,.2f}")
        except (TypeError, ValueError):
            continue
    return values or ["該日沒有可顯示數值"]


def price_legend_items() -> tuple[LegendItem, ...]:
    items = [LegendItem("KLINE", "Candlestick", COLORS["candlestick"]["up"], focus="先看紅綠K棒的方向與實體大小。")]
    for key in ("ma5", "ma10", "ma20", "ma60", "ma120", "ma240"):
        items.append(LegendItem(key.upper(), key.upper(), COLORS["moving_average"][key], "solid", "比較股價位於均線上方或下方，以及均線排列。"))
    items.append(LegendItem("BOLLINGER", "Bollinger Bands", COLORS["bollinger"]["upper"], "dash", "觀察通道擴張、收縮及價格是否接近上下軌。"))
    return tuple(items)


def volume_legend_items() -> tuple[LegendItem, ...]:
    return (
        LegendItem("VOLUME", "Volume", COLORS["candlestick"]["volume_up"], "solid", "比較放量或縮量，並確認價格趨勢是否有量能支持。"),
        LegendItem("VOLUME_MA20", "Volume MA20", COLORS["moving_average"]["ma20"], "solid", "目前成交量高於均量代表交易活躍度上升。"),
    )


def kd_legend_items() -> tuple[LegendItem, ...]:
    return (
        LegendItem("K", "K", COLORS["kd"]["k"], "solid", "觀察K與D交叉，以及是否進入80以上或20以下區域。"),
        LegendItem("D", "D", COLORS["kd"]["d"], "dash", "D線較平滑，用來確認K線訊號。"),
    )


def rsi_legend_items() -> tuple[LegendItem, ...]:
    return (LegendItem("RSI", "RSI(14)", COLORS["rsi"]["line"], "solid", "注意70、50、30三個位置與指標方向。"),)


def macd_legend_items() -> tuple[LegendItem, ...]:
    return (
        LegendItem("DIF", "DIF", COLORS["macd"]["dif"], "solid", "觀察DIF與Signal交叉及是否站上零軸。"),
        LegendItem("SIGNAL", "Signal", COLORS["macd"]["signal"], "dash", "用來確認DIF的趨勢轉折。"),
        LegendItem("MACD", "Histogram", COLORS["macd"]["positive"], "solid", "柱體由小轉大代表動能增強，由大轉小代表動能減弱。"),
    )


def market_legend_items() -> tuple[LegendItem, ...]:
    return (
        LegendItem("TWII", "TWII", COLORS["market"]["twii"], LINE_STYLES["market"]["twii"], "作為台股市場基準，與美股主要指數比較。"),
        LegendItem("SP500", "S&P 500", COLORS["market"]["sp500"], LINE_STYLES["market"]["sp500"], "比較美國大型股與台股走勢。"),
        LegendItem("NASDAQ100", "Nasdaq 100", COLORS["market"]["nasdaq100"], LINE_STYLES["market"]["nasdaq100"], "觀察大型科技股風險偏好。"),
        LegendItem("SOX", "SOX", COLORS["market"]["sox"], LINE_STYLES["market"]["sox"], "觀察半導體族群是否領先或落後大盤。"),
    )


def prediction_legend_items() -> tuple[LegendItem, ...]:
    return (
        LegendItem("ACTUAL_PRICE", "Actual Price", COLORS["prediction"]["actual"], "solid", "作為模型預測的真實比較基準。"),
        LegendItem("PREDICTED_PRICE", "Predicted Price", COLORS["prediction"]["predicted"], "dash", "比較預測方向與實際價格，並同時查看區間寬度。"),
        LegendItem("PREDICTION_INTERVAL", "Prediction Interval", COLORS["prediction"]["upper"], "dot", "區間越寬代表模型不確定性越高。"),
    )


def render_glossary(keys: tuple[str, ...], title: str = "英文指標中文說明與用途") -> None:
    with st.expander(f"📖 {title}", expanded=False):
        for key in keys:
            chinese, purpose = INDICATOR_GLOSSARY[key]
            st.markdown(f"**{key}｜{chinese}**")
            st.write(purpose)
