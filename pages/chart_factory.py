"""Shared Plotly chart factory. No dashboard page should define series colors locally."""

import pandas as pd
import plotly.graph_objects as go

from config.color_config import COLORS, LINE_STYLES
from config.indicator_glossary import bilingual


RANGE_BUTTONS = [
    dict(count=4, label="4天", step="day", stepmode="backward"),
    dict(count=5, label="5天", step="day", stepmode="backward"),
    dict(count=7, label="7天", step="day", stepmode="backward"),
    dict(count=10, label="10天", step="day", stepmode="backward"),
    dict(count=15, label="15天", step="day", stepmode="backward"),
    dict(count=1, label="1月", step="month", stepmode="backward"),
    dict(count=3, label="3月", step="month", stepmode="backward"),
    dict(count=6, label="6月", step="month", stepmode="backward"),
    dict(count=1, label="1年", step="year", stepmode="backward"),
    dict(step="all", label="全部"),
]

DATE_TICK_FORMAT_STOPS = [
    dict(dtickrange=[None, 86_400_000], value="%m/%d"),
    dict(dtickrange=[86_400_000, 2_678_400_000], value="%m/%d"),
    dict(dtickrange=[2_678_400_000, 31_536_000_000], value="%Y/%m"),
    dict(dtickrange=[31_536_000_000, None], value="%Y"),
]


def apply_chart_layout(figure: go.Figure, title: str, y_title: str, rangeslider: bool = False) -> go.Figure:
    figure.update_layout(
        title=dict(text=title, x=0.01), template="plotly_white", hovermode="x",
        paper_bgcolor=COLORS["layout"]["background"], plot_bgcolor=COLORS["layout"]["background"],
        hoverlabel=dict(
            bgcolor=COLORS["layout"]["tooltip_background"],
            bordercolor=COLORS["layout"]["tooltip_border"],
            font=dict(color=COLORS["layout"]["tooltip_text"], size=14),
            namelength=-1,
        ),
        legend=dict(
            orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
            title=dict(text="圖例｜滑鼠移至項目查看說明"),
        ),
        margin=dict(l=55, r=190, t=70, b=45),
        xaxis=dict(
            title="日期", type="date", showgrid=True, gridcolor=COLORS["layout"]["grid"],
            rangeselector=dict(buttons=RANGE_BUTTONS), rangeslider=dict(visible=rangeslider),
            tickformat="%Y/%m/%d", tickformatstops=DATE_TICK_FORMAT_STOPS,
            hoverformat="%Y/%m/%d", ticklabelmode="period",
        ),
        yaxis=dict(title=y_title, showgrid=True, gridcolor=COLORS["layout"]["grid"], fixedrange=False),
        hoverdistance=100,
    )
    figure.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot",
        spikecolor=COLORS["layout"]["date_cursor"], spikethickness=2,
    )
    return figure


def add_attention_trace(figure: go.Figure, x: pd.Series, y: pd.Series, notes: pd.Series) -> None:
    """Add a transparent hover target with a second yellow/blue attention tooltip."""
    figure.add_trace(go.Scatter(
        x=x, y=y, mode="markers", marker=dict(size=12, opacity=0),
        customdata=notes.fillna("目前沒有額外警示。"),
        hovertemplate="<b>觀看提醒</b><br>%{customdata}<extra></extra>",
        hoverlabel=dict(
            bgcolor=COLORS["layout"]["attention_background"],
            bordercolor=COLORS["layout"]["attention_border"],
            font=dict(color=COLORS["layout"]["attention_text"], size=14),
        ),
        name="觀看提醒", showlegend=False,
    ))


def price_chart(frame: pd.DataFrame, stock_name: str) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Candlestick(
        x=frame["trade_date"], open=frame["open"], high=frame["high"], low=frame["low"], close=frame["close"],
        name=bilingual("KLINE", "Candlestick"), increasing_line_color=COLORS["candlestick"]["up"],
        decreasing_line_color=COLORS["candlestick"]["down"],
        increasing_fillcolor=COLORS["candlestick"]["up"], decreasing_fillcolor=COLORS["candlestick"]["down"],
        hovertext="紅漲／綠跌",
    ))
    for key in ("ma5", "ma10", "ma20", "ma60", "ma120", "ma240"):
        if key in frame:
            figure.add_trace(go.Scatter(
                x=frame["trade_date"], y=frame[key], name=bilingual(key.upper(), key.upper()), mode="lines",
                line=dict(color=COLORS["moving_average"][key], width=LINE_STYLES["moving_average"][key], dash="solid"),
                hovertemplate=f"{bilingual(key.upper(), key.upper())}：%{{y:.2f}}<extra></extra>",
            ))
    if "bollinger_upper" in frame:
        figure.add_trace(go.Scatter(
            x=frame["trade_date"], y=frame["bollinger_upper"], name="Bollinger Upper｜布林上軌", mode="lines",
            line=dict(color=COLORS["bollinger"]["upper"], width=2, dash=LINE_STYLES["bollinger"]["upper"]),
            hovertemplate="布林上軌：%{y:.2f}<extra></extra>",
        ))
        figure.add_trace(go.Scatter(
            x=frame["trade_date"], y=frame["bollinger_lower"], name="Bollinger Lower｜布林下軌", mode="lines",
            line=dict(color=COLORS["bollinger"]["lower"], width=2, dash=LINE_STYLES["bollinger"]["lower"]),
            fill="tonexty", fillcolor=COLORS["bollinger"]["fill"],
            hovertemplate="布林下軌：%{y:.2f}<extra></extra>",
        ))
    notes = pd.Series("觀察股價與MA20的相對位置及均線排列。", index=frame.index)
    if "ma20" in frame:
        notes = pd.Series(
            ["股價高於MA20，留意能否守穩及量能是否配合。" if close >= ma20 else "股價低於MA20，留意短中期趨勢轉弱風險。"
             if pd.notna(ma20) else "MA20資料尚未累積完整。" for close, ma20 in zip(frame["close"], frame["ma20"])],
            index=frame.index,
        )
    add_attention_trace(figure, frame["trade_date"], frame["close"], notes)
    return apply_chart_layout(figure, f"{stock_name}｜價格、均線與布林通道", "價格（TWD）", True)


def volume_chart(frame: pd.DataFrame) -> go.Figure:
    colors = [COLORS["candlestick"]["volume_up"] if close >= open_ else COLORS["candlestick"]["volume_down"]
              for open_, close in zip(frame["open"], frame["close"])]
    figure = go.Figure(go.Bar(
        x=frame["trade_date"], y=frame["volume"], name=bilingual("VOLUME", "Volume"), marker_color=colors,
        hovertemplate="成交量：%{y:,.0f}<extra></extra>",
    ))
    if "volume_ma20" in frame:
        figure.add_trace(go.Scatter(
            x=frame["trade_date"], y=frame["volume_ma20"], name=bilingual("VOLUME_MA20", "Volume MA20"), mode="lines",
            line=dict(color=COLORS["moving_average"]["ma20"], width=3, dash="solid"),
            hovertemplate="20日均量：%{y:,.0f}<extra></extra>",
        ))
    notes = pd.Series("比較當日成交量與20日均量。", index=frame.index)
    if "volume_ma20" in frame:
        notes = pd.Series([
            "成交量高於20日均量，注意價格方向是否獲得量能確認。" if pd.notna(avg) and volume > avg
            else "成交量未高於20日均量，突破或跌破訊號的確認度較低。"
            for volume, avg in zip(frame["volume"], frame["volume_ma20"])
        ], index=frame.index)
    add_attention_trace(figure, frame["trade_date"], frame["volume"], notes)
    return apply_chart_layout(figure, "成交量｜紅色為上漲日、綠色為下跌日", "成交量")


def kd_chart(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_hrect(y0=80, y1=100, fillcolor=COLORS["kd"]["overbought"], line_width=0)
    figure.add_hrect(y0=0, y1=20, fillcolor=COLORS["kd"]["oversold"], line_width=0)
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["kd_k"], name=bilingual("K", "K"), mode="lines",
                                line=dict(color=COLORS["kd"]["k"], width=3, dash="solid")))
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["kd_d"], name=bilingual("D", "D"), mode="lines",
                                line=dict(color=COLORS["kd"]["d"], width=2, dash="dash")))
    figure.update_yaxes(range=[0, 100])
    notes = pd.Series([
        "KD位於80以上，注意短線過熱與反轉風險。" if k >= 80 else
        "KD位於20以下，注意超賣後反彈可能，但仍需價格確認。" if k <= 20 else
        "KD位於中間區域，重點觀察K、D交叉方向。" for k in frame["kd_k"].fillna(50)
    ], index=frame.index)
    add_attention_trace(figure, frame["trade_date"], frame["kd_k"], notes)
    return apply_chart_layout(figure, "KD 指標｜80以上過熱、20以下超賣", "KD")


def macd_chart(frame: pd.DataFrame) -> go.Figure:
    histogram_colors = [COLORS["macd"]["positive"] if value >= 0 else COLORS["macd"]["negative"]
                        for value in frame["macd_histogram"].fillna(0)]
    figure = go.Figure()
    figure.add_trace(go.Bar(x=frame["trade_date"], y=frame["macd_histogram"], name="柱狀體",
                            marker_color=histogram_colors))
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["macd"], name=bilingual("DIF", "DIF"), mode="lines",
                                line=dict(color=COLORS["macd"]["dif"], width=3, dash="solid")))
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["macd_signal"], name=bilingual("SIGNAL", "Signal"), mode="lines",
                                line=dict(color=COLORS["macd"]["signal"], width=2, dash="dash")))
    figure.add_hline(y=0, line=dict(color=COLORS["macd"]["zero"], width=1, dash=LINE_STYLES["reference"]))
    notes = pd.Series([
        "DIF高於Signal，動能偏多；注意是否同步站上零軸。" if dif >= signal else
        "DIF低於Signal，動能偏弱；注意負柱是否持續擴大。"
        for dif, signal in zip(frame["macd"].fillna(0), frame["macd_signal"].fillna(0))
    ], index=frame.index)
    add_attention_trace(figure, frame["trade_date"], frame["macd"].fillna(0), notes)
    return apply_chart_layout(figure, "MACD｜趨勢與動能", "MACD")


def rsi_chart(frame: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_hrect(y0=70, y1=100, fillcolor=COLORS["rsi"]["overbought"], line_width=0)
    figure.add_hrect(y0=0, y1=30, fillcolor=COLORS["rsi"]["oversold"], line_width=0)
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["rsi14"], name=bilingual("RSI", "RSI(14)"), mode="lines",
                                line=dict(color=COLORS["rsi"]["line"], width=3, dash="solid")))
    figure.add_hline(y=50, line=dict(color=COLORS["rsi"]["midline"], width=1, dash=LINE_STYLES["reference"]))
    figure.update_yaxes(range=[0, 100])
    notes = pd.Series([
        "RSI高於70，注意過熱、背離與回檔風險。" if value >= 70 else
        "RSI低於30，注意超賣反彈可能，但不要單獨作為買進依據。" if value <= 30 else
        "RSI位於30至70，注意是否站上50及指標方向。" for value in frame["rsi14"].fillna(50)
    ], index=frame.index)
    add_attention_trace(figure, frame["trade_date"], frame["rsi14"].fillna(50), notes)
    return apply_chart_layout(figure, "RSI｜70以上過熱、30以下超賣", "RSI")


def prediction_chart(frame: pd.DataFrame) -> go.Figure:
    required = {"trade_date", "actual_price", "predicted_price", "prediction_upper", "prediction_lower"}
    if not required.issubset(frame.columns):
        raise ValueError(f"prediction data missing columns: {sorted(required - set(frame.columns))}")
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["prediction_upper"], name="Prediction Upper｜預測上界", mode="lines",
                                line=dict(color=COLORS["prediction"]["upper"], width=2, dash="dash")))
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["prediction_lower"], name="Prediction Lower｜預測下界", mode="lines",
                                line=dict(color=COLORS["prediction"]["lower"], width=2, dash="dot"),
                                fill="tonexty", fillcolor=COLORS["prediction"]["interval"]))
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["actual_price"], name=bilingual("ACTUAL_PRICE", "Actual Price"), mode="lines",
                                line=dict(color=COLORS["prediction"]["actual"], width=3, dash="solid")))
    figure.add_trace(go.Scatter(x=frame["trade_date"], y=frame["predicted_price"], name=bilingual("PREDICTED_PRICE", "Predicted Price"), mode="lines+markers",
                                line=dict(color=COLORS["prediction"]["predicted"], width=3, dash="dash"), marker=dict(size=5)))
    interval_width = frame["prediction_upper"] - frame["prediction_lower"]
    relative_width = interval_width / frame["predicted_price"].replace(0, pd.NA)
    notes = pd.Series([
        "預測區間偏寬，代表不確定性較高，應降低對單一預測值的依賴。" if pd.notna(width) and width >= 0.10
        else "預測區間相對較窄，仍需搭配風險與技術面確認。" for width in relative_width
    ], index=frame.index)
    add_attention_trace(figure, frame["trade_date"], frame["predicted_price"], notes)
    return apply_chart_layout(figure, "實際價格與模型預測區間", "價格（TWD）", True)
