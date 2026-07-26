"""Single-stock analysis page with separated, color-consistent technical charts."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.color_config import COLORS
from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from collectors.news_collector import load_news_cache
from features.technical_indicators import add_technical_indicators
from pages import dividend_analysis
from pages.chart_factory import kd_chart, macd_chart, price_chart, rsi_chart, volume_chart
from pages.glossary import (
    LegendItem, kd_legend_items, macd_legend_items, price_legend_items, render_chart_with_legend,
    render_glossary, rsi_legend_items, volume_legend_items,
)


def render() -> None:
    st.header("個股技術分析")
    category = st.selectbox(
        "第一步：選擇標的類別",
        ("臺灣50成分股（50檔）", "臺灣市場熱門ETF（50檔）"),
        help="切換後，下方標的選單會顯示該類別的50檔商品。",
    )
    if category == "臺灣50成分股（50檔）":
        universe = _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
        ranking_note = "依最近20個交易日平均成交金額排序"
    else:
        universe = load_popular_etfs()
        ranking_note = "依證交所最新交易日成交金額排序"
    st.success(f"目前類別：{category}｜已載入 {len(universe)} 檔")
    label_to_symbol = {
        f"{rank:02d}｜{name}（{symbol.removesuffix('.TW')}）": symbol
        for rank, (symbol, name) in enumerate(universe.items(), start=1)
    }
    st.caption(f"熱門度排序方式：{ranking_note}")
    selected = st.selectbox(
        "第二步：選擇分析標的",
        list(label_to_symbol),
        help="臺灣50成分股按近20日平均成交金額排序；ETF按證交所最新交易日成交金額排序。",
    )
    with st.expander(f"查看{category}完整名單", expanded=False):
        st.dataframe(
            pd.DataFrame([
                {"熱門排名": rank, "代號": symbol.removesuffix(".TW"), "名稱": name}
                for rank, (symbol, name) in enumerate(universe.items(), start=1)
            ]),
            hide_index=True,
            width="stretch",
        )
    symbol = label_to_symbol[selected]
    st.session_state["selected_stock_symbol"] = symbol
    st.session_state["selected_stock_name"] = universe[symbol]
    path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
    if not path.exists():
        st.warning("尚無行情資料，請先回到系統狀態頁執行更新。")
        return
    try:
        frame = _load_price_history(path)
    except (OSError, ValueError) as exc:
        st.error(f"行情資料格式異常，無法載入：{exc}")
        return
    if frame.empty:
        st.warning("行情資料沒有可用的日期或價格，請回到系統狀態頁重新更新。")
        return
    stock_name = universe[symbol]
    full_frame = add_technical_indicators(frame)
    technical_tab, dividend_tab, fundamental_tab, chip_tab = st.tabs(
        ("技術面", "股息與試算", "基本面", "籌碼面")
    )
    with technical_tab:
        _render_technical_analysis(full_frame, symbol, stock_name)
        _render_related_news(symbol, stock_name)
    with dividend_tab:
        dividend_analysis.render(symbol, stock_name, full_frame)
    with fundamental_tab:
        _render_fundamentals(symbol)
    with chip_tab:
        _render_institutional(symbol)


def _render_technical_analysis(frame: pd.DataFrame, symbol: str, stock_name: str) -> None:
    minimum, maximum = frame["trade_date"].min().date(), frame["trade_date"].max().date()
    default_start = max(minimum, (pd.Timestamp(maximum) - pd.DateOffset(years=1)).date())
    start, end = st.date_input(
        "顯示日期範圍", value=(default_start, maximum),
        min_value=minimum, max_value=maximum, key=f"{symbol}_technical_dates",
    )
    visible = frame[
        (frame["trade_date"].dt.date >= start) & (frame["trade_date"].dt.date <= end)
    ]
    if visible.empty:
        st.info("所選日期範圍沒有交易資料。")
        return
    render_chart_with_legend(
        price_chart(visible, stock_name), price_legend_items(), f"{symbol}_price", default_period="7天"
    )
    render_glossary(("KLINE", "MA5", "MA10", "MA20", "MA60", "MA120", "MA240", "BOLLINGER"))
    render_chart_with_legend(
        volume_chart(visible), volume_legend_items(), f"{symbol}_volume", default_period="7天"
    )
    render_glossary(("VOLUME", "VOLUME_MA20"))
    render_chart_with_legend(
        kd_chart(visible), kd_legend_items(), f"{symbol}_kd", default_period="7天"
    )
    render_glossary(("KD", "K", "D"))
    render_chart_with_legend(
        rsi_chart(visible), rsi_legend_items(), f"{symbol}_rsi", default_period="7天"
    )
    render_glossary(("RSI",))
    render_chart_with_legend(
        macd_chart(visible), macd_legend_items(), f"{symbol}_macd", default_period="7天"
    )
    render_glossary(("MACD", "DIF", "SIGNAL"))


def _sort_stocks_by_popularity(universe: dict[str, str]) -> dict[str, str]:
    scores: list[tuple[float, str, str]] = []
    for symbol, name in universe.items():
        path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
        score = 0.0
        if path.exists():
            try:
                recent = pd.read_csv(path, usecols=["close", "volume"]).tail(20)
                recent["close"] = pd.to_numeric(recent["close"], errors="coerce")
                recent["volume"] = pd.to_numeric(recent["volume"], errors="coerce")
                score = float((recent["close"] * recent["volume"]).mean())
            except (OSError, ValueError, KeyError):
                score = 0.0
        scores.append((score, symbol, name))
    scores.sort(reverse=True)
    return {symbol: name for _, symbol, name in scores}


def _load_price_history(path: Path) -> pd.DataFrame:
    """Load mixed ISO dates safely and reject unusable market rows."""
    frame = pd.read_csv(path)
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"缺少必要欄位：{', '.join(sorted(missing))}")
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], format="mixed", errors="coerce"
    )
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(
        subset=["trade_date", "open", "high", "low", "close", "volume"]
    )
    return (
        frame.sort_values("trade_date")
        .drop_duplicates("trade_date", keep="last")
        .reset_index(drop=True)
    )


def _render_fundamentals(symbol: str) -> None:
    path = PROJECT_ROOT / "data" / "processed" / "financial_features.csv"
    if not path.exists():
        st.info("目前無基本面資料，請先執行資料更新。")
        return
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        st.warning("基本面資料目前無法讀取。")
        return
    stock_id = symbol.removesuffix(".TW")
    rows = frame[frame["stock_id"].astype(str).str.replace(".TW", "", regex=False) == stock_id].copy()
    if rows.empty:
        st.info("目前無資料；系統不會以示範值冒充真實財務數字。")
        return
    date_column = "effective_trade_date" if "effective_trade_date" in rows else "updated_at"
    rows[date_column] = pd.to_datetime(rows[date_column], errors="coerce")
    rows = rows[rows[date_column] <= pd.Timestamp.now().normalize()].sort_values(date_column)
    if rows.empty:
        st.info("最新資料尚未到可使用日期，目前不提前顯示，避免使用未來資訊。")
        return
    latest = rows.iloc[-1]
    st.caption(
        f"資料可使用日期：{latest[date_column]:%Y-%m-%d}｜"
        "僅使用當時已公告或已取得資料，避免未來資訊。"
    )
    metrics = [
        ("營業收入", "revenue", "NT$ {:,.0f}"), ("營收年增率", "revenue_yoy", "{:.2%}"),
        ("營收月增率", "revenue_mom", "{:.2%}"), ("毛利率", "gross_margin", "{:.2%}"),
        ("營業利益率", "operating_margin", "{:.2%}"), ("EPS", "eps", "{:,.2f}"),
        ("ROE", "roe", "{:.2%}"), ("負債比率", "debt_ratio", "{:.2%}"),
        ("自由現金流", "free_cash_flow", "NT$ {:,.0f}"), ("本益比", "pe_ratio", "{:,.2f}"),
        ("股價淨值比", "pb_ratio", "{:,.2f}"), ("殖利率", "dividend_yield", "{:.2f}%"),
    ]
    available = [(label, key, fmt) for label, key, fmt in metrics if key in rows.columns]
    for offset in range(0, len(available), 4):
        columns = st.columns(4)
        for column, (label, key, fmt) in zip(columns, available[offset:offset + 4]):
            value = pd.to_numeric(latest.get(key), errors="coerce")
            column.metric(label, fmt.format(value) if pd.notna(value) else "目前無資料")
    trend_columns = [key for key in ("revenue", "eps", "gross_margin", "roe", "free_cash_flow") if key in rows]
    if len(rows) > 1 and trend_columns:
        selected = st.selectbox(
            "財務趨勢指標", trend_columns,
            format_func={"revenue": "營業收入", "eps": "EPS", "gross_margin": "毛利率",
                         "roe": "ROE", "free_cash_flow": "自由現金流"}.get,
        )
        figure = go.Figure(go.Scatter(
            x=rows[date_column], y=pd.to_numeric(rows[selected], errors="coerce"),
            name=selected, mode="lines+markers",
            line={"color": COLORS["market"]["twii"], "width": 3},
        ))
        figure.update_layout(
            title="已公告財務資料趨勢", template="plotly_white", hovermode="x unified",
            legend={"orientation": "v", "x": 1.02, "y": 1},
            xaxis={"fixedrange": True}, yaxis={"fixedrange": True},
        )
        render_chart_with_legend(figure, (
            LegendItem(
                f"financial_{selected}", selected, COLORS["market"]["twii"], "solid",
                "僅顯示當時已公告且已到可使用日期的財務資料。",
            ),
        ), f"{symbol}_financial_{selected}", default_period="全部日期")
    st.caption("目前來源未完整提供ROA、稅後淨利率及所有季度歷史時，欄位會顯示目前無資料。")


def _render_institutional(symbol: str) -> None:
    path = PROJECT_ROOT / "data" / "raw" / "institutional" / f"{symbol.removesuffix('.TW')}.csv"
    if not path.exists():
        st.info("目前尚未串接此標的的籌碼資料。")
        return
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        st.warning("籌碼資料目前無法讀取。")
        return
    if frame.empty or "trade_date" not in frame:
        st.info("目前尚未串接此標的的籌碼資料。")
        return
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date").tail(120)
    if frame.empty:
        st.info("目前尚未串接此標的的籌碼資料。")
        return
    latest = frame.iloc[-1]
    st.caption(f"資料截至：{latest['trade_date']:%Y-%m-%d}｜資料來源：FinMind")
    metrics = [
        ("外資買賣超", "foreign_net"), ("投信買賣超", "investment_trust_net"),
        ("自營商買賣超", "dealer_net"), ("三大法人合計", "institutional_net"),
        ("融資餘額", "margin_balance"), ("融券餘額", "short_balance"),
        ("借券賣出餘額", "securities_lending"),
    ]
    available = [(label, key) for label, key in metrics if key in frame]
    for offset in range(0, len(available), 4):
        columns = st.columns(4)
        for column, (label, key) in zip(columns, available[offset:offset + 4]):
            value = pd.to_numeric(latest.get(key), errors="coerce")
            column.metric(label, f"{value:,.0f}" if pd.notna(value) else "目前無資料")
    figure = go.Figure()
    styles = (
        ("foreign_net", "外資", COLORS["institutional"]["foreign"]),
        ("investment_trust_net", "投信", COLORS["institutional"]["trust"]),
        ("dealer_net", "自營商", COLORS["institutional"]["dealer"]),
    )
    for key, label, color in styles:
        if key in frame:
            figure.add_scatter(
                x=frame["trade_date"], y=pd.to_numeric(frame[key], errors="coerce"),
                name=label, mode="lines", line={"color": color, "width": 2},
            )
    figure.update_layout(
        title="三大法人每日買賣超", template="plotly_white", hovermode="x unified",
        legend={"orientation": "v", "x": 1.02, "y": 1},
        xaxis={"fixedrange": True}, yaxis={"title": "買賣超", "fixedrange": True},
    )
    render_chart_with_legend(figure, (
        LegendItem("foreign_net", "Foreign Investors", COLORS["institutional"]["foreign"], "solid", "觀察外資買賣超方向與連續性。"),
        LegendItem("trust_net", "Investment Trust", COLORS["institutional"]["trust"], "solid", "觀察投信是否連續布局。"),
        LegendItem("dealer_net", "Dealers", COLORS["institutional"]["dealer"], "solid", "觀察自營商避險與交易方向。"),
    ), f"{symbol}_institutional", default_period="3個月")
    st.caption("外資持股比例、當沖比例、主力與集保股權分散目前沒有授權資料來源，不顯示推估數字。")


@st.cache_data(ttl=600, show_spinner=False)
def _related_news(symbol: str, stock_name: str) -> list[dict[str, object]]:
    payload = load_news_cache()
    code = symbol.removesuffix(".TW")
    name_terms = {
        stock_name.strip(),
        stock_name.replace("元大", "").replace("富邦", "").replace("國泰", "").strip(),
    }
    name_terms = {term for term in name_terms if len(term) >= 2}
    matches: list[dict[str, object]] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        code_hit = code in text and any(marker in text for marker in (f"（{code}）", f"({code})", f" {code}"))
        if code_hit or any(term in text for term in name_terms):
            matches.append(item)
    matches.sort(key=lambda item: str(item.get("published_at", "")), reverse=True)
    return matches[:12]


def _render_related_news(symbol: str, stock_name: str) -> None:
    st.divider()
    st.subheader(f"{stock_name}（{symbol.removesuffix('.TW')}）相關新聞")
    st.caption("依目前選擇的股票或ETF名稱與代碼，自公開新聞快取篩選；點選標題可查看原始來源。")
    try:
        items = _related_news(symbol, stock_name)
    except Exception as exc:
        st.warning(f"相關新聞暫時無法載入：{exc}")
        return
    if not items:
        st.info("目前新聞資料中沒有明確提及此標的；系統不會用產業新聞冒充個股新聞。")
        return
    for item in items:
        published = pd.to_datetime(
            item.get("published_at"), format="mixed", errors="coerce", utc=True
        )
        published_text = (
            published.tz_convert("Asia/Taipei").strftime("%Y/%m/%d %H:%M")
            if pd.notna(published)
            else "時間未提供"
        )
        st.markdown(f"#### [{item.get('title', '未命名新聞')}]({item.get('link', '#')})")
        st.caption(
            f"{item.get('source', '來源未提供')}｜"
            f"{item.get('category', '其他')}｜{published_text}"
        )
        if item.get("summary"):
            st.write(str(item["summary"]))
