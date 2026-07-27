"""Interactive multi-stage strategy backtest dashboard."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtest.backtester import BacktestConfig, BacktestResult, run_backtest
from backtest.optimizer import (
    optimize_ma,
    training_validation_analysis,
    walk_forward_analysis,
)
from backtest.performance import monthly_returns
from backtest.storage import delete_strategy, load_strategies, save_strategy
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
    tabs = st.tabs(("策略設定", "回測結果", "交易紀錄", "月年度績效", "策略比較", "參數最佳化", "策略儲存與匯出"))
    setup, results_tab, trades_tab, period_tab, comparison_tab, optimizer_tab, export_tab = tabs
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
        include_dividends = st.checkbox("計入真實現金股息", value=False)
        reinvest_dividends = st.checkbox("股息於下一交易日自動再投入", value=False, disabled=not include_dividends)
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
            include_dividends=include_dividends, reinvest_dividends=reinvest_dividends,
        )
        dividends = _load_dividends(symbol) if include_dividends else pd.DataFrame()
        try:
            with st.spinner("正在依序產生訊號、模擬下一交易日成交並計算績效…"):
                result = _cached_run(frame, strategy, parameters, config, dividends)
                benchmark = _cached_run(
                    frame, "買進持有", {},
                    replace(config, stop_loss=0.0, take_profit=0.0),
                    dividends,
                )
            st.session_state["backtest_result"] = result
            st.session_state["backtest_benchmark"] = benchmark
            st.session_state["backtest_context"] = {"symbol": symbol, "name": stock_name, "strategy": strategy}
            st.session_state["backtest_parameters"] = parameters
            st.session_state["backtest_config"] = config
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
    with period_tab:
        _render_period_performance(result)
    with comparison_tab:
        _render_comparison(frame, st.session_state["backtest_config"])
    with optimizer_tab:
        _render_optimizer(frame, strategy, parameters, st.session_state["backtest_config"])
    with export_tab:
        _render_exports(result, context, parameters, st.session_state["backtest_config"])
        st.divider()
        st.subheader("刪除回測紀錄")
        st.caption("只清除目前瀏覽器工作階段的回測結果，不會刪除股票行情、股息資料或已匯出的檔案。")
        confirm_delete = st.checkbox("我確認要刪除目前的策略回測紀錄", key="confirm_delete_backtest")
        if st.button(
            "刪除本次回測紀錄",
            type="secondary",
            disabled=not confirm_delete,
            use_container_width=True,
        ):
            _clear_backtest_session()
            st.success("策略回測紀錄已刪除。")
            st.rerun()


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
    if strategy == "KD交叉":
        a, b, c = st.columns(3)
        return {"kd_period": a.number_input("KD期間", 3, 60, 9), "kd_low": b.number_input("低檔門檻", 1, 50, 20), "kd_high": c.number_input("高檔門檻", 50, 99, 80)}
    if strategy in {"布林均值回歸", "布林突破"}:
        a, b, c = st.columns(3)
        return {
            "bollinger_period": a.number_input("布林期間", 5, 120, 20),
            "bollinger_std": b.number_input("標準差倍數", 0.5, 4.0, 2.0, 0.1),
            "volume_multiple": c.number_input("突破量能倍數", 1.0, 5.0, 1.5, 0.1),
        }
    if strategy == "成交量突破":
        a, b, c = st.columns(3)
        return {
            "breakout_high": a.number_input("突破高點期間", 5, 120, 20),
            "breakout_low": b.number_input("跌破低點期間", 2, 60, 10),
            "volume_multiple": c.number_input("成交量倍數", 1.0, 5.0, 1.5, 0.1),
            "volume_period": 20,
        }
    if strategy == "自訂條件":
        st.caption("第一階段視覺化條件器支援同一群組內AND／OR；指標可用收盤價、MA5、MA20、MA60、RSI、成交量倍數及漲跌幅。")
        indicators = ("close", "MA5", "MA20", "MA60", "RSI", "成交量倍數", "漲跌幅")
        operators = ("大於", "小於", "大於等於", "小於等於", "向上突破", "向下跌破")
        entry_connector = st.radio("買進條件連接", ("AND", "OR"), horizontal=True)
        e1, e2, e3 = st.columns(3)
        entry = [{"left": e1.selectbox("買進指標", indicators), "operator": e2.selectbox("買進比較", operators), "value": e3.number_input("買進比較值", value=0.0)}]
        exit_connector = st.radio("賣出條件連接", ("OR", "AND"), horizontal=True)
        x1, x2, x3 = st.columns(3)
        exit_conditions = [{"left": x1.selectbox("賣出指標", indicators), "operator": x2.selectbox("賣出比較", operators), "value": x3.number_input("賣出比較值", value=0.0)}]
        return {"entry_conditions": entry, "exit_conditions": exit_conditions, "entry_connector": entry_connector, "exit_connector": exit_connector}
    st.info("回測第一個可成交交易日買進，持有至期間結束。")
    return {}


@st.cache_data(show_spinner=False)
def _cached_run(frame: pd.DataFrame, strategy: str, parameters: dict, config: BacktestConfig, dividends: pd.DataFrame) -> BacktestResult:
    return run_backtest(frame, strategy, parameters, config, dividends)


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


def _render_period_performance(result: BacktestResult) -> None:
    st.subheader("月度與年度績效")
    monthly = monthly_returns(result.equity)
    st.dataframe(
        monthly.style.format({"報酬率": "{:+.2%}"}),
        hide_index=True, width="stretch",
    )
    equity = result.equity.copy()
    equity["年度"] = pd.to_datetime(equity["date"]).dt.year
    annual = equity.groupby("年度").agg(
        年初資產=("total_equity", "first"), 年末資產=("total_equity", "last"),
        年度最大回撤=("drawdown", "min"), 股息收入=("dividend_income", "sum"),
    ).reset_index()
    annual["年度報酬率"] = annual["年末資產"] / annual["年初資產"] - 1
    st.dataframe(
        annual.style.format({
            "年初資產": "NT$ {:,.0f}", "年末資產": "NT$ {:,.0f}",
            "年度最大回撤": "{:.2%}", "年度報酬率": "{:+.2%}", "股息收入": "NT$ {:,.0f}",
        }),
        hide_index=True, width="stretch",
    )
    heat = go.Figure(go.Bar(
        x=monthly["月份"], y=monthly["報酬率"] * 100,
        marker_color=[COLORS["candlestick"]["up"] if value >= 0 else COLORS["candlestick"]["down"] for value in monthly["報酬率"]],
        name="月報酬率",
    ))
    _layout(heat, "月度報酬（紅色正報酬／綠色負報酬）", "報酬率（%）")
    st.plotly_chart(heat, width="stretch", config={"displaylogo": False, "scrollZoom": False})


def _render_comparison(frame: pd.DataFrame, config: BacktestConfig) -> None:
    st.subheader("多策略比較")
    choices = st.multiselect("選擇最多5個策略", STRATEGIES[:-1], default=["買進持有", "均線交叉", "RSI反轉", "MACD交叉"], max_selections=5)
    if not st.button("執行多策略比較", use_container_width=True):
        return
    rows, curves = [], []
    defaults = {
        "均線交叉": {"short_ma": 5, "long_ma": 20},
        "RSI反轉": {"rsi_period": 14, "oversold": 30, "overbought": 70},
        "MACD交叉": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9},
        "KD交叉": {"kd_period": 9, "kd_low": 20, "kd_high": 80},
        "布林均值回歸": {"bollinger_period": 20, "bollinger_std": 2},
        "布林突破": {"bollinger_period": 20, "bollinger_std": 2, "volume_multiple": 1.5},
        "成交量突破": {"breakout_high": 20, "breakout_low": 10, "volume_period": 20, "volume_multiple": 1.5},
    }
    for name in choices:
        result = run_backtest(frame, name, defaults.get(name, {}), config)
        rows.append({"策略名稱": name, **result.metrics})
        curves.append((name, result.equity))
    comparison = pd.DataFrame(rows)
    st.dataframe(comparison[["策略名稱", "total_return", "annualized_return", "max_drawdown", "sharpe_ratio", "win_rate", "profit_factor", "completed_trades", "final_equity", "total_transaction_costs"]], hide_index=True, width="stretch")
    fig = go.Figure()
    palette = [COLORS["backtest"]["strategy"], COLORS["backtest"]["benchmark"], COLORS["backtest"]["cash"], COLORS["dmi"]["adx"], COLORS["dividend"]["shares"]]
    for index, (name, equity) in enumerate(curves):
        fig.add_scatter(x=equity["date"], y=equity["total_equity"], name=name, line={"color": palette[index], "width": 2})
    _layout(fig, "多策略資產曲線", "資產（NT$）")
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": False})


def _render_optimizer(frame: pd.DataFrame, strategy: str, parameters: dict, config: BacktestConfig) -> None:
    st.subheader("參數最佳化與樣本外驗證")
    st.warning("歷史最佳參數可能存在過度擬合，不代表未來市場中仍能維持相同績效。")
    a, b, c = st.columns(3)
    short_start, short_end, short_step = a.number_input("短均線起始", 2, 50, 5), b.number_input("短均線結束", 3, 60, 20), c.number_input("短均線間隔", 1, 20, 5)
    a, b, c = st.columns(3)
    long_start, long_end, long_step = a.number_input("長均線起始", 5, 120, 20), b.number_input("長均線結束", 10, 240, 120), c.number_input("長均線間隔", 1, 40, 20)
    objective = st.selectbox("最佳化目標", ("年化報酬率最高", "Sharpe Ratio最高", "Sortino Ratio最高", "最大回撤最低", "Calmar Ratio最高", "Profit Factor最高"))
    if st.button("執行參數最佳化", use_container_width=True):
        try:
            optimized = optimize_ma(frame, config, list(range(short_start, short_end + 1, short_step)), list(range(long_start, long_end + 1, long_step)), objective)
            st.session_state["optimization_result"] = optimized
        except ValueError as exc:
            st.error(str(exc))
    optimized = st.session_state.get("optimization_result")
    if isinstance(optimized, pd.DataFrame) and not optimized.empty:
        st.success(f"最佳參數：短期{int(optimized.iloc[0]['短期均線'])}日／長期{int(optimized.iloc[0]['長期均線'])}日")
        st.dataframe(optimized.head(10), hide_index=True, width="stretch")
        st.download_button("匯出參數最佳化CSV", optimized.to_csv(index=False).encode("utf-8-sig"), "optimization.csv", "text/csv")
    if st.button("執行70/30驗證與Walk-forward", use_container_width=True):
        analysis = training_validation_analysis(frame, strategy, parameters, config)
        st.session_state["validation_analysis"] = analysis
        st.session_state["walk_forward"] = walk_forward_analysis(frame, strategy, parameters, config)
    analysis = st.session_state.get("validation_analysis")
    if isinstance(analysis, dict):
        comparison = pd.DataFrame([
            {"期間": "訓練期70%", **analysis["training"]},
            {"期間": "驗證期30%", **analysis["validation"]},
        ])
        st.dataframe(comparison[["期間", "total_return", "annualized_return", "max_drawdown", "sharpe_ratio", "profit_factor"]], hide_index=True, width="stretch")
        if analysis["overfit_risk"]:
            st.warning("此策略的驗證期表現明顯低於訓練期，可能存在過度擬合風險。")
        st.dataframe(st.session_state["walk_forward"], hide_index=True, width="stretch")
    st.info("AI策略：目前缺少逐日保存的歷史AI預測訊號，因此不使用最新預測回填過去；待歷史訊號累積後才會啟用。")


def _render_exports(result: BacktestResult, context: dict, parameters: dict, config: BacktestConfig) -> None:
    st.download_button("匯出交易紀錄CSV", result.trades.to_csv(index=False).encode("utf-8-sig"), "backtest_trades.csv", "text/csv")
    st.download_button("匯出每日資產曲線CSV", result.equity.to_csv(index=False).encode("utf-8-sig"), "backtest_equity.csv", "text/csv")
    monthly = monthly_returns(result.equity)
    st.download_button("匯出月度績效CSV", monthly.to_csv(index=False).encode("utf-8-sig"), "backtest_monthly.csv", "text/csv")
    strategy_record = {"name": f"{context['symbol']}-{context['strategy']}", "symbol": context["symbol"], "strategy": context["strategy"], "parameters": parameters, "config": asdict(config)}
    setting = json.dumps(strategy_record, ensure_ascii=False, indent=2)
    st.download_button("匯出策略設定JSON", setting, "backtest_strategy.json", "application/json")
    storage_path = PROJECT_ROOT / "data" / "processed" / "saved_strategies.json"
    strategy_name = st.text_input("策略名稱", value=strategy_record["name"])
    if st.button("儲存策略設定"):
        save_strategy(storage_path, {**strategy_record, "name": strategy_name})
        st.success("策略已儲存；Streamlit雲端重新部署時本機儲存可能重置，請同時下載JSON備份。")
    saved = load_strategies(storage_path)
    if saved:
        names = [item.get("name", "未命名") for item in saved]
        selected = st.selectbox("已儲存策略", names)
        confirm = st.checkbox("我確認要刪除此策略")
        if st.button("刪除所選策略", disabled=not confirm):
            delete_strategy(storage_path, selected)
            st.success("策略已刪除")


def _load_dividends(symbol: str) -> pd.DataFrame:
    path = PROJECT_ROOT / "data" / "processed" / "dividends" / f"{symbol.removesuffix('.TW')}.csv"
    if not path.exists():
        st.warning("目前沒有此標的真實股息公告資料，股息回測將不計入股息。")
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, ValueError):
        st.warning("股息公告資料格式異常，股息回測將不計入股息。")
        return pd.DataFrame()


def _clear_backtest_session() -> None:
    keys = (
        "backtest_result",
        "backtest_benchmark",
        "backtest_context",
        "backtest_parameters",
        "backtest_config",
        "optimization_result",
        "validation_analysis",
        "walk_forward",
        "confirm_delete_backtest",
    )
    for key in keys:
        st.session_state.pop(key, None)


def _layout(fig: go.Figure, title: str, y_title: str) -> None:
    fig.update_layout(title=title, template="plotly_white", hovermode="x unified", legend={"orientation": "v", "x": 1.01, "y": 1},
                      margin={"l": 40, "r": 130, "t": 55, "b": 40}, xaxis={"title": "日期"}, yaxis={"title": y_title})
