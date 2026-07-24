"""Financial-news navigation page."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from collectors.news_collector import EXCLUDED_TERMS, collect_financial_news, load_news_cache

TAIPEI = ZoneInfo("Asia/Taipei")


@st.cache_data(ttl=600, show_spinner=False)
def _load_news() -> dict[str, object]:
    return load_news_cache()


def _time(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TAIPEI).strftime("%Y/%m/%d %H:%M")
    except (ValueError, TypeError):
        return value or "時間未提供"


def _published(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TAIPEI)
    except (ValueError, TypeError):
        return None


def render() -> None:
    st.header("財經新聞")
    st.caption("彙整公開 RSS 新聞標題與摘要；點選標題可前往原始新聞來源。")
    if st.button("立即更新新聞", type="primary"):
        with st.spinner("正在更新財經新聞……"):
            collect_financial_news()
        _load_news.clear()
        st.rerun()
    try:
        payload = _load_news()
    except Exception as exc:
        st.error(f"新聞暫時無法載入：{exc}")
        return
    items = [item for item in payload.get("items", [])
             if not any(term in f"{item.get('title', '')} {item.get('summary', '')}" for term in EXCLUDED_TERMS)]
    categories = [
        "全部財經新聞", "本日頭條新聞", "本週頭條新聞",
        "台股市場", "產業科技", "美股國際", "投資理財",
        "投資人－股魚", "投資人－陳重銘", "投資人－施昇輝", "投資人－華倫老師（周文偉）",
    ]
    left, middle, right = st.columns([1, 1.4, 2])
    category = left.selectbox("新聞分類", categories)
    sources = sorted({str(item.get("source", "來源未提供")) for item in items})
    source = middle.selectbox("新聞來源", ["全部新聞來源"] + sources)
    keyword = right.text_input("關鍵字篩選", placeholder="例如：台積電、AI、利率")
    now = datetime.now(TAIPEI)
    if category == "本日頭條新聞":
        items = [item for item in items if (published := _published(str(item.get("published_at", "")))) and published.date() == now.date()]
    elif category == "本週頭條新聞":
        week_start = (now - timedelta(days=now.weekday())).date()
        items = [item for item in items if (published := _published(str(item.get("published_at", "")))) and week_start <= published.date() <= now.date()]
    elif category != "全部財經新聞":
        items = [item for item in items if item.get("category") == category]
    if source != "全部新聞來源":
        items = [item for item in items if item.get("source") == source]
    if keyword.strip():
        needle = keyword.strip().casefold()
        items = [item for item in items if needle in f"{item.get('title', '')} {item.get('summary', '')}".casefold()]
    st.caption(f"最近更新：{_time(str(payload.get('updated_at', '')))}｜目前顯示 {len(items)} 則")
    if payload.get("using_cache"):
        st.warning("新聞來源暫時無法連線，目前顯示最近一次成功更新的內容。")
    for error in payload.get("errors", []):
        st.caption(f"來源提醒：{error}")
    if not items:
        st.info("目前沒有符合條件的新聞，請更換分類或關鍵字。")
    for item in items[:60]:
        st.markdown(f"### [{item['title']}]({item['link']})")
        st.caption(f"{item.get('source', '來源未提供')}｜{item.get('category', '其他')}｜{_time(str(item.get('published_at', '')))}")
        if item.get("summary"):
            st.write(item["summary"])
        st.divider()
    st.info("新聞僅供資料研究與市場觀察，內容與時效請以原始來源為準，不構成投資建議或獲利保證。")
