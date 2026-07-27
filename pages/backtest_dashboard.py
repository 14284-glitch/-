"""Interactive first-stage strategy backtest dashboard."""

from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtest.backtester import BacktestConfig, BacktestResult, run_backtest
from backtest.performance import monthly_returns
from backtest.strategy import STRATEGIES
from config.color_config import COLORS
from config.settings import PROJECT_ROOT, get_settings
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from pages.stock_analysis import _load_price_history, _sort_stocks_by_popularity

DISCLAIMER = (
    "策略回測係依歷史市場資料、設定條件及交易成本假設進行模擬。歷史績效不代表未來結果，"
    "回測可能受到資料品質、滑價、流動性、交易成本、參數過度擬合及前視偏誤等因素影響。"
    "本功能僅供研究與投資參考，不構成買進、賣出或持有任何金融商品之建議。"
    "投資人應自行評估並承擔投資風險。"
)


def render() -> None:
    st.header("策略回測")
    st.warning(DISCLAIMER)
    frame, symbol, stock_name = _stock_and_range()
    if frame is None:
        return
    settings = get_settings()
    setup, results_tab, trades_tab, export_tab = st.tabs(("策略設定", "回測結果", "交易紀錄", "匯出"))
    with setup:
        strategy = st.selectbox("內建策略", STRATEGIES)
        parameters = _strategy_parameters(strategy)
        capital = st.number_input("初始本金（NT$）", min_value=1_000.0, value=1_000_000.0, step=100_000.0)
        left, middle, right = st.columns(3)
        commission = left.number_input("買賣手續費率（%）", min_value=0.0, value=settings.backtest_commission_rate * 100, step=0.01) / 100
        tax = middle.number_input("賣出交易稅率（%）", min_value=0.0, value=settings.backtest_transaction_tax_rate * 100, step=0.01) / 100
        slippage = right.number_input("單邊滑價（%）", min_value=0.0, value=settings.backtest_slippage_rate * 100, step=0.01) / 100
        left, middle, right = st.columns(3)
        minimum_commission = left.number_input("最低手續費（NT$）", min_value=0.0, value=20.0, step=1.0)
        stop_loss = middle.number_input("固定停損（%）", min_value=0.0, max_value=100.0, value=8.0, step=1.0) / 100
        take_profit = right.number_input("固定停利（%）", min_value=0.0, value=20.0, step=1.0) / 100
        allow_odd_lots = st.checkbox("允許零股交易", value=False)
        position_fraction = st.slider("每次投入可用資金比例", 10, 100, 100, 5) / 100
        st.caption("訊號使用當期收盤資料判斷，預設於下一交易日開盤成交；最後一期沒有下一期資料時不執行新訊號。")
        st.caption("交易成本預設值僅供模擬，實際費率依券商折扣、商品類型及當年度法規而異。")
        run_clicked = st.button("執行回測", type="primary", use_container_width=True)
    if run_clicked:
        config = BacktestConfig(
            symbol=symbol, initial_capital=capital, commission_rate=commission,
            minimum_commission=minimum_commission, transaction_tax_rate=tax,
            slippage_rate=slippage, position_fraction=position_fraction,
            allow_odd_lots=allow_odd_lots, stop_loss=stop_loss, take_profit=take_profit,
        )
        try:
            with st.spinner("正在依序產生訊號、模擬下一交易日成交並計算績效…"):
                result = _cached_run(frame, strategy, parameters, config)
                benchmark = _cached_run(
                    frame, "買進持有", {},
                    replace(config, stop_loss=0.0, take_profit=0.0),
                )
            st.session_state["backtest_result"] = result
            st.session_state["backtest_benchmark"] = benchmark
            st.session_state["backtest_context"] = {"symbol": symbol, "name": stock_name, "strategy": strategy}
        except ValueError as exc:
            st.error(f"無法執行回測：{exc}")
    result = st.session_state.get("backtest_result")
    context = st.session_state.get("backtest_context", {})
    if not isinstance(result, BacktestResult) or context.get("symbol") != symbol:
        with results_tab:
            st.info("請先在「策略設定」按下執行回測。")
        return
    benchmark = st.session_state["backtest_benchmark"]
    with results_tab:
        _render_results(result, benchmark, frame, context)
    with trades_tab:
        _render_trades(result)
    with export_tab:
        _render_exports(result, context)


def _stock_and_range() -> tuple[pd.DataFrame | None, str, str]:
    universe = {**_sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS), **load_popular_etfs()}
    previous = st.session_state.get("selected_stock_symbol")
    symbols = list(universe)
    default = symbols.index(previous) if previous in symbols else 0
    symbol = st.selectbox(
        "回測標的（沿用其他頁面的最近選擇）", symbols, index=default,
        format_func=lambda item: f"{universe[item]}（{item.removesuffix('.TW')}）",
    )
    st.session_state["selected_stock_symbol"], st.session_state["selected_stock_name"] = symbol, universe[symbol]
    path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
    if not path.exists():
        st.warning("找不到此標的歷史資料，請先到「系統狀態」更新。")
        return None, symbol, universe[symbol]
    try:
        full = _load_price_history(path)
    except (OSError, ValueError) as exc:
        st.error(f"無法載入歷史行情：{exc}")
        return None, symbol, universe[symbol]
    if len(full) < 60:
        st.warning("目前歷史資料不足，至少需要60筆才能執行第一階段回測。")
        return None, symbol, universe[symbol]
    minimum, maximum = full["trade_date"].min().date(), full["trade_date"].max().date()
    preset = st.selectbox("日期範圍", ("近1年", "近3年", "近5年", "近10年", "自訂日期"), index=1)
    years = {"近1年": 1, "近3年": 3, "近5年": 5, "近10年": 10}.get(preset)
    default_start = max(minimum, (pd.Timestamp(maximum) - pd.DateOffset(years=years or 3)).date())
    if preset == "自訂日期":
        start, end = st.date_input("自訂回測日期", (default_start, maximum), min_value=minimum, max_value=maximum)
    else:
        start, end = default_start, maximum
    frame = full[(full["trade_date"].dt.date >= start) & (full["trade_date"].dt.date <= end)].copy()
    if len(frame) < 2:
        st.warning("目前歷史資料不足，無法完成所選期間的回測。")
        return None, symbol, universe[symbol]
    latest = frame.iloc[-1]
    cols = st.columns(5)
    cols[0].metric("股票", f"{universe[symbol]} {symbol.removesuffix('.TW')}")
    cols[1].metric("市場", "台灣")
    cols[2].metric("最新股價", f"NT$ {latest['close']:,.2f}")
    cols[3].metric("資料筆數", f"{len(frame):,}")
    cols[4].metric("使用週期", "日線")
    st.caption(f"資料期間：{frame['trade_date'].min():%Y-%m-%d}～{frame['trade_date'].max():%Y-%m-%d}｜真實歷史日K資料")
    return frame, symbol, universe[symbol]


def _strategy_parameters(strategy: str) -> dict[str, float]:
    if strategy == "均線交叉":
        a, b = st.columns(2)
        return {"short_ma": a.number_input("短期均線", 2, 120, 5), "long_ma": b.number_input("長期均線", 3, 240, 20)}
    if strategy == "RSI反轉":
        a, b, c = st.columns(3)
        return {"rsi_period": a.number_input("RSI期間", 2, 60, 14), "oversold": b.number_input("超賣門檻", 1, 50, 30), "overbought": c.number_input("超買門檻", 50, 99, 70)}
    if strategy == "MACD交叉":
        a, b, c = st.columns(3)
        return {"macd_fast": a.number_input("快速期間", 2, 60, 12), "macd_slow": b.number_input("慢速期間", 3, 120, 26), "macd_signal": c.number_input("Signal期間", 2, 60, 9)}
    st.info("回測第一個可成交交易日買進，持有至期間結束。")
    return {}


@st.cache_data(show_spinner=False)
def _cached_run(frame: pd.DataFrame, strategy: str, parameters: dict, config: BacktestConfig) -> BacktestResult:
    return run_backtest(frame, strategy, parameters, config)


def _render_results(result: BacktestResult, benchmark: BacktestResult, frame: pd.DataFrame, context: dict) -> None:
    m, bm = result.metrics, benchmark.metrics
    st.subheader(f"{context['name']}｜{context['strategy']}回測摘要")
    cols = st.columns(4)
    cards = [
        ("最終資產", f"NT$ {m['final_equity']:,.0f}"), ("總報酬率", f"{m['total_return']:+.2%}"),
        ("年化報酬率", f"{m['annualized_return']:+.2%}"), ("最大回撤", f"{m['max_drawdown']:.2%}"),
        ("勝率", f"{m['win_rate']:.2%}"), ("Profit Factor", f"{m['profit_factor']:.2f}"),
        ("Sharpe Ratio", f"{m['sharpe_ratio']:.2f}"), ("交易成本", f"NT$ {m['total_transaction_costs']:,.0f}"),
    ]
    for index, (label, value) in enumerate(cards):
        cols[index % 4].metric(label, value)
    st.caption(
        f"有效回測起始日：{result.equity['date'].min():%Y-%m-%d}｜"
        f"指標暖機期：{result.warmup_periods}期｜實際資料：{len(result.equity)}筆｜"
        f"買進持有報酬：{bm['total_return']:+.2%}"
    )
    merged = result.equity[["date", "total_equity"]].rename(columns={"total_equity": "策略資產"}).merge(
        benchmark.equity[["date", "total_equity"]].rename(columns={"total_equity": "買進持有"}), on="date", how="left"
    )
    fig = go.Figure()
    fig.add_scatter(x=merged["date"], y=merged["策略資產"], name="策略資產", line={"color": COLORS["backtest"]["strategy"], "width": 3})
    fig.add_scatter(x=merged["date"], y=merged["買進持有"], name="買進持有", line={"color": COLORS["backtest"]["benchmark"], "width": 2, "dash": "dash"})
    _layout(fig, "策略資產與買進持有比較", "資產（NT$）")
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": False})
    draw = go.Figure(go.Scatter(x=result.equity["date"], y=result.equity["drawdown"] * 100, fill="tozeroy", name="回撤", line={"color": COLORS["backtest"]["drawdown"], "width": 2}))
    _layout(draw, "策略回撤曲線", "回撤（%）")
    st.plotly_chart(draw, width="stretch", config={"displaylogo": False, "scrollZoom": False})
    _render_trade_chart(frame, result.trades)


def _render_trade_chart(frame: pd.DataFrame, trades: pd.DataFrame) -> None:
    fig = go.Figure(go.Candlestick(
        x=frame["trade_date"], open=frame["open"], high=frame["high"], low=frame["low"], close=frame["close"],
        name="K線", increasing_line_color=COLORS["candlestick"]["up"], decreasing_line_color=COLORS["candlestick"]["down"],
    ))
    if not trades.empty:
        for side, symbol, color in (("買進", "triangle-up", COLORS["candlestick"]["down"]), ("賣出", "triangle-down", COLORS["candlestick"]["up"])):
            rows = trades[trades["side"] == side]
            fig.add_scatter(x=rows["execution_date"], y=rows["price"], mode="markers+text", text=["買" if side == "買進" else "賣"] * len(rows),
                            textposition="top center", name=f"{side}點", marker={"symbol": symbol, "size": 13, "color": color},
                            customdata=rows[["shares", "total_cost", "reason"]], hovertemplate="日期：%{x}<br>價格：%{y:.2f}<br>股數：%{customdata[0]:,.0f}<br>成本：%{customdata[1]:,.2f}<br>原因：%{customdata[2]}<extra></extra>")
    _layout(fig, "K線買賣點（買／賣文字輔助辨識）", "價格")
    fig.update_layout(xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": False})


def _render_trades(result: BacktestResult) -> None:
    st.subheader("完整交易明細")
    if result.trades.empty:
        st.info("所選期間沒有產生可成交交易。")
        return
    display = result.trades.rename(columns={
        "id": "交易編號", "signal_date": "訊號日期", "execution_date": "成交日期", "symbol": "股票代號", "side": "交易方向",
        "price": "成交價格", "shares": "成交股數", "gross_amount": "成交金額", "commission": "手續費",
        "tax": "交易稅", "slippage": "滑價成本", "total_cost": "總交易成本", "reason": "交易原因", "holding_periods": "持有天數",
        "realized_profit": "單筆損益", "return_percent": "單筆報酬率", "cash_after": "交易後現金",
        "position_after": "交易後持股", "equity_after": "交易後總資產",
    })
    st.dataframe(display, hide_index=True, width="stretch")


def _render_exports(result: BacktestResult, context: dict) -> None:
    st.download_button("匯出交易紀錄CSV", result.trades.to_csv(index=False).encode("utf-8-sig"), "backtest_trades.csv", "text/csv")
    st.download_button("匯出每日資產曲線CSV", result.equity.to_csv(index=False).encode("utf-8-sig"), "backtest_equity.csv", "text/csv")
    monthly = monthly_returns(result.equity)
    st.download_button("匯出月度績效CSV", monthly.to_csv(index=False).encode("utf-8-sig"), "backtest_monthly.csv", "text/csv")
    setting = json.dumps({"股票": context["symbol"], "策略": context["strategy"]}, ensure_ascii=False, indent=2)
    st.download_button("匯出策略設定JSON", setting, "backtest_strategy.json", "application/json")


def _layout(fig: go.Figure, title: str, y_title: str) -> None:
    fig.update_layout(title=title, template="plotly_white", hovermode="x unified", legend={"orientation": "v", "x": 1.01, "y": 1},
                      margin={"l": 40, "r": 130, "t": 55, "b": 40}, xaxis={"title": "日期"}, yaxis={"title": y_title})
