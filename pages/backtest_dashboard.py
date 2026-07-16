"""Backtest page placeholder that does not present invented performance."""

import streamlit as st


def render() -> None:
    st.header("策略回測")
    st.info("⏳ 正在訓練模型中")
    st.caption("模型完成驗證後才會進行策略回測，避免使用尚未驗證的預測訊號計算績效。")
    st.progress(20, text="目前進度：等待基準模型完成與測試通過")
    st.warning("回測完成前不顯示虛構績效曲線或投資報酬。")
