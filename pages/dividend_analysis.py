"""Dividend analysis embedded in the existing single-stock page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from config.color_config import COLORS
from config.dividend_config import DIVIDEND_DISCLAIMER, REINVESTMENT_DISCLAIMER
from config.settings import PROJECT_ROOT
from services.dividend_service import (
    build_announced_dividend_history,
    build_dividend_history,
    calculate_dividend,
    simulate_reinvestment,
)
from pages.glossary import LegendItem, render_chart_with_legend


@st.cache_data(ttl=21_600, show_spinner=False)
def load_dividend_history(symbol: str, price_frame: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    announcement_path = (
        PROJECT_ROOT / "data" / "processed" / "dividends" /
        f"{symbol.removesuffix('.TW')}.csv"
    )
    if announcement_path.exists():
        try:
            announcements = pd.read_csv(announcement_path)
            announced = build_announced_dividend_history(
                announcements, price_frame[["trade_date", "close"]]
            )
            if not announced.empty:
                return announced, "FinMind最新公司股利公告"
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            pass
    try:
        dividends = yf.Ticker(symbol).dividends
    except Exception:
        return pd.DataFrame(), "目前無資料"
    return (
        build_dividend_history(dividends, price_frame[["trade_date", "close"]]),
        "Yahoo Finance歷史公司行動（公告快取尚未建立）",
    )


def render(symbol: str, stock_name: str, price_frame: pd.DataFrame) -> None:
    latest_price = float(pd.to_numeric(price_frame["close"], errors="coerce").dropna().iloc[-1])
    history, source = load_dividend_history(symbol, price_frame)
    if history.empty:
        st.info("目前資料來源沒有可驗證的股息歷史；系統不會以示範數字冒充真實股利。")
        latest_cash = 0.0
    else:
        latest_cash = _latest_annual_cash(history)
        latest_stock_rate = float(pd.to_numeric(
            history.get("股票股利配股率", pd.Series([0.0])), errors="coerce"
        ).fillna(0).iloc[0])
        _render_summary(
            symbol, stock_name, latest_price, history, latest_cash, price_frame, source
        )
        _render_history(history)
        _render_trends(history)
    st.divider()
    _render_calculator(
        symbol, stock_name, latest_price, latest_cash,
        latest_stock_rate if not history.empty else 0.0,
    )


def _latest_annual_cash(history: pd.DataFrame) -> float:
    latest_year = int(history["年度"].max())
    return float(history.loc[history["年度"] == latest_year, "每股現金股利"].sum())


def _render_summary(
    symbol: str, stock_name: str, latest_price: float, history: pd.DataFrame,
    latest_cash: float, price_frame: pd.DataFrame, source: str,
) -> None:
    annual = history.groupby("年度", as_index=False).agg(
        每股現金股利=("每股現金股利", "sum"),
        現金殖利率=("現金殖利率", "sum"),
    ).sort_values("年度")
    recent_five = annual.tail(5)
    latest = history.iloc[0]
    frequency = int(history[history["年度"] == history["年度"].max()].shape[0])
    frequency_text = {1: "每年一次", 2: "每半年", 4: "每季"}.get(frequency, f"每年約{frequency}次")
    consecutive = _consecutive_years(set(annual["年度"].astype(int)))
    growth_stable = (
        "是" if len(recent_five) >= 3 and recent_five["每股現金股利"].pct_change().dropna().ge(0).all()
        else "否／仍需觀察"
    )
    st.caption(
        f"股息資料來源：{source}。最新公告優先；公告尚未提供的欄位會明確顯示目前無資料。"
    )
    first = st.columns(4)
    first[0].metric("股票", f"{stock_name}（{symbol.removesuffix('.TW')}）")
    first[1].metric("最新股價", f"NT$ {latest_price:,.2f}")
    first[2].metric("最新年度現金股利", f"NT$ {latest_cash:,.2f}")
    first[3].metric("預估現金殖利率", f"{latest_cash / latest_price:.2%}" if latest_price else "0.00%")
    second = st.columns(4)
    second[0].metric("配息頻率", frequency_text)
    second[1].metric("最近除息日", _date(latest["除息日期"]))
    second[2].metric("最後買進日", _last_buy_date(price_frame, latest["除息日期"]))
    second[3].metric("股息發放日", _date(latest["發放日期"]))
    third = st.columns(4)
    third[0].metric("最近一次是否填息", str(latest["是否完成填息"]))
    third[1].metric("填息日期", _date(latest["填息日期"]))
    third[2].metric("填息天數", f"{int(latest['填息天數'])}天" if pd.notna(latest["填息天數"]) else "尚未填息")
    third[3].metric("連續配息年數", f"{consecutive}年")
    fourth = st.columns(3)
    fourth[0].metric("近5年平均現金股利", f"NT$ {recent_five['每股現金股利'].mean():,.2f}")
    fourth[1].metric("近5年平均殖利率", f"{recent_five['現金殖利率'].mean():.2%}")
    fourth[2].metric("股利是否穩定成長", growth_stable)
    if "公告時間" in history and pd.notna(latest.get("公告時間")):
        st.caption(f"最近公告時間：{pd.to_datetime(latest['公告時間']):%Y-%m-%d %H:%M:%S}")


def _render_history(history: pd.DataFrame) -> None:
    st.subheader("股息歷史資料")
    period = st.selectbox("股息歷史範圍", ("最近5年", "最近10年", "全部年度"), key="dividend_period")
    years = {"最近5年": 5, "最近10年": 10}.get(period)
    visible = history if years is None else history[history["年度"] >= history["年度"].max() - years + 1]
    display = visible.copy()
    for column in ("公告時間", "除息日期", "除權日期", "發放日期", "填息日期"):
        if column in display:
            display[column] = display[column].map(_date)
    display["現金殖利率"] = pd.to_numeric(display["現金殖利率"], errors="coerce").map(
        lambda value: f"{value:.2%}" if pd.notna(value) else "目前無資料"
    )
    display["股票股利"] = display["股票股利"].map(
        lambda value: f"{float(value):,.4f}" if pd.notna(value) else "目前無資料"
    )
    st.dataframe(display, hide_index=True, width="stretch")


def _render_trends(history: pd.DataFrame) -> None:
    annual = history.groupby("年度", as_index=False).agg(
        每股現金股利=("每股現金股利", "sum"),
        現金殖利率=("現金殖利率", "sum"),
        填息天數=("填息天數", "mean"),
    ).sort_values("年度")
    annual["年度股利成長率"] = annual["每股現金股利"].pct_change()
    tabs = st.tabs(("現金股利與殖利率", "填息天數", "年度股利成長率"))
    with tabs[0]:
        figure = go.Figure()
        figure.add_bar(x=annual["年度"], y=annual["每股現金股利"], name="每股現金股利",
                       marker_color=COLORS["dividend"]["cash"])
        figure.add_scatter(x=annual["年度"], y=annual["現金殖利率"] * 100, name="現金殖利率（%）",
                           mode="lines+markers", yaxis="y2", line={"color": COLORS["dividend"]["yield"], "width": 3})
        _layout(figure, "年度現金股利與殖利率", "每股現金股利（NT$）", "殖利率（%）")
        render_chart_with_legend(figure, (
            LegendItem("cash_dividend", "Cash Dividend", COLORS["dividend"]["cash"], "solid", "觀察每股現金股利是否穩定或成長。"),
            LegendItem("cash_yield", "Dividend Yield", COLORS["dividend"]["yield"], "solid", "高殖利率需搭配獲利與配息持續性判讀。"),
        ), "dividend_cash_yield", default_period="全部日期")
    with tabs[1]:
        figure = go.Figure(go.Scatter(x=annual["年度"], y=annual["填息天數"], mode="lines+markers",
                                      name="平均填息天數", line={"color": COLORS["dividend"]["fill_days"], "width": 3}))
        _layout(figure, "年度平均填息天數", "天數")
        render_chart_with_legend(figure, (
            LegendItem("fill_days", "Fill-right Days", COLORS["dividend"]["fill_days"], "solid", "天數越短代表歷史上較快回到除息前參考價。"),
        ), "dividend_fill_days", default_period="全部日期")
    with tabs[2]:
        colors = [COLORS["candlestick"]["up"] if value >= 0 else COLORS["candlestick"]["down"]
                  for value in annual["年度股利成長率"].fillna(0)]
        figure = go.Figure(go.Bar(x=annual["年度"], y=annual["年度股利成長率"] * 100,
                                  name="年度股利成長率", marker_color=colors))
        _layout(figure, "年度股利成長率", "成長率（%）")
        render_chart_with_legend(figure, (
            LegendItem("dividend_growth", "Dividend Growth", COLORS["dividend"]["growth"], "solid", "觀察股利成長是否連續，負值代表年度股利下降。"),
        ), "dividend_growth", default_period="全部日期")


def _render_calculator(
    symbol: str, stock_name: str, latest_price: float, latest_cash: float,
    latest_stock_rate: float,
) -> None:
    st.subheader("股息試算機")
    unit = st.radio("輸入持有單位", ("股數", "張數"), horizontal=True)
    holding = st.number_input(f"持有{unit}", min_value=0.0, value=1000.0 if unit == "股數" else 1.0, step=1.0)
    shares = holding if unit == "股數" else holding * 1000
    inputs = st.columns(3)
    cash = inputs[0].number_input("每股現金股利", min_value=0.0, value=float(latest_cash), step=0.1)
    stock_rate = inputs[1].number_input(
        "股票股利配股率", min_value=0.0, value=float(latest_stock_rate), step=0.01,
        help="例如配股率10%為0.10；有FinMind最新公告時會自動帶入，仍可自行修改。",
    )
    cost = inputs[2].number_input("每股買進成本", min_value=0.0, value=float(latest_price), step=0.5)
    more = st.columns(3)
    current = more[0].number_input("目前股價", min_value=0.0, value=float(latest_price), step=0.5)
    tax_percent = more[1].number_input("預估所得稅率（%）", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    include_nhi = more[2].checkbox("估算二代健保補充保費", value=True)
    result = calculate_dividend(shares, cash, stock_rate, cost, current, tax_percent / 100, include_nhi)
    st.caption(f"試算標的：{stock_name}（{symbol.removesuffix('.TW')}）｜所有輸入可自行修改，零股亦可計算。")
    rows = [
        ("持有張數", f"{result.lots:,.3f}張"), ("持有股數", f"{result.shares:,.0f}股"),
        ("每股現金股利", _money(result.cash_dividend_per_share)),
        ("預估現金股息", _money(result.gross_cash_dividend)),
        ("預估所得稅", _money(result.estimated_income_tax)),
        ("預估二代健保補充保費", _money(result.estimated_nhi_premium)),
        ("預估實領股息", _money(result.estimated_net_dividend)),
        ("股票股利預估新增股數", f"{result.stock_dividend_new_shares:,.2f}股"),
        ("成本殖利率", f"{result.yield_on_cost:.2%}"), ("目前殖利率", f"{result.current_yield:.2%}"),
        ("每季平均股息", _money(result.quarterly_average)), ("每月平均股息", _money(result.monthly_average)),
    ]
    for group_start in range(0, len(rows), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, rows[group_start:group_start + 4]):
            column.metric(label, value)
    st.warning(DIVIDEND_DISCLAIMER)
    with st.expander("股息再投入情境模擬", expanded=False):
        _render_reinvestment(result.shares, current, cash)


def _render_reinvestment(shares: float, price: float, dividend: float) -> None:
    inputs = st.columns(3)
    initial_shares = inputs[0].number_input("初始持股股數", min_value=0.0, value=float(shares), step=1.0)
    initial_price = inputs[1].number_input("初始股價", min_value=0.0, value=float(price), step=0.5)
    annual_dividend = inputs[2].number_input("每股年度現金股利", min_value=0.0, value=float(dividend), step=0.1)
    inputs2 = st.columns(4)
    dividend_growth = inputs2[0].number_input("預估股利年成長率（%）", value=0.0, step=0.5) / 100
    price_growth = inputs2[1].number_input("預估股價年成長率（%）", value=0.0, step=0.5) / 100
    contribution = inputs2[2].number_input("每年額外投入金額", min_value=0.0, value=0.0, step=1000.0)
    years = inputs2[3].selectbox("模擬期間", (5, 10, 15, 20), format_func=lambda value: f"{value}年")
    simulation = simulate_reinvestment(
        initial_shares, initial_price, annual_dividend,
        dividend_growth, price_growth, contribution, years,
    )
    st.dataframe(simulation.style.format({
        "年初持股股數": "{:,.2f}", "當年度每股股利": "{:,.2f}", "當年度現金股息": "NT$ {:,.2f}",
        "額外投入金額": "NT$ {:,.2f}", "可再投入股數": "{:,.2f}", "年末總持股": "{:,.2f}",
        "累積投入成本": "NT$ {:,.2f}", "累積收到股息": "NT$ {:,.2f}",
        "預估持股市值": "NT$ {:,.2f}", "預估股價": "NT$ {:,.2f}",
    }), hide_index=True, width="stretch")
    figure = go.Figure()
    figure.add_scatter(x=simulation["年度"], y=simulation["當年度現金股息"], mode="lines+markers",
                       name="年度股息收入", line={"color": COLORS["dividend"]["cash"], "width": 3})
    figure.add_scatter(x=simulation["年度"], y=simulation["年末總持股"], mode="lines+markers",
                       name="年末持股數", yaxis="y2", line={"color": COLORS["dividend"]["shares"], "width": 3, "dash": "dash"})
    _layout(figure, "股息收入與持股數量情境", "股息收入（NT$）", "持股股數")
    render_chart_with_legend(figure, (
        LegendItem("income", "Dividend Income", COLORS["dividend"]["cash"], "solid", "顯示假設條件下每年的股息收入。"),
        LegendItem("shares", "Total Shares", COLORS["dividend"]["shares"], "dash", "顯示股息與額外投入再買進後的持股變化。"),
    ), "reinvestment_income_shares", default_period="全部日期")
    asset = go.Figure(go.Scatter(x=simulation["年度"], y=simulation["預估持股市值"], mode="lines+markers",
                                 name="預估持股市值", line={"color": COLORS["dividend"]["asset_value"], "width": 3}))
    _layout(asset, "資產價值情境", "預估市值（NT$）")
    render_chart_with_legend(asset, (
        LegendItem("asset_value", "Estimated Asset Value", COLORS["dividend"]["asset_value"], "solid", "為假設成長率下的情境結果，不是價格預測。"),
    ), "reinvestment_asset", default_period="全部日期")
    st.warning(REINVESTMENT_DISCLAIMER)


def _layout(figure: go.Figure, title: str, y_title: str, secondary_title: str | None = None) -> None:
    figure.update_layout(
        title=title, template="plotly_white", hovermode="x unified", legend={"orientation": "v", "x": 1.02, "y": 1},
        margin={"l": 30, "r": 150, "t": 55, "b": 35}, xaxis={"title": "年度", "fixedrange": True},
        yaxis={"title": y_title, "fixedrange": True},
    )
    if secondary_title:
        figure.update_layout(yaxis2={"title": secondary_title, "overlaying": "y", "side": "right", "fixedrange": True})


def _consecutive_years(years: set[int]) -> int:
    if not years:
        return 0
    count, current = 0, max(years)
    while current in years:
        count += 1
        current -= 1
    return count


def _last_buy_date(price_frame: pd.DataFrame, ex_date: object) -> str:
    date = pd.to_datetime(ex_date, errors="coerce")
    if pd.isna(date):
        return "目前無資料"
    dates = pd.to_datetime(price_frame["trade_date"], errors="coerce")
    candidates = dates[dates < date].dropna()
    return candidates.max().strftime("%Y-%m-%d") if not candidates.empty else "目前無資料"


def _date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else "目前無資料"


def _money(value: float) -> str:
    return f"NT$ {value:,.2f}"
