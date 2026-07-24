from pathlib import Path
from collectors.news_collector import DEFAULT_FEEDS, collect_financial_news, parse_rss

RSS = """<rss><channel><item><title>台股測試新聞</title><link>https://example.com/news/1</link><description><![CDATA[<b>摘要</b> 內容]]></description><pubDate>Thu, 16 Jul 2026 01:30:00 GMT</pubDate></item></channel></rss>"""


def test_parse_rss_strips_markup_and_preserves_metadata():
    item = parse_rss(RSS, "測試來源", "台股市場")[0]
    assert item["title"] == "台股測試新聞"
    assert item["summary"] == "摘要 內容"
    assert item["source"] == "測試來源"
    assert item["published_at"].startswith("2026-07-16")


def test_parse_rss_excludes_lottery_results():
    lottery = RSS.replace("台股測試新聞", "威力彩開獎號碼公布")
    assert parse_rss(lottery, "測試來源", "台股市場") == []


def test_major_publishers_are_configured():
    sources = {source for source, _, _ in DEFAULT_FEEDS}
    assert {"中央社產經證券", "自由財經", "經濟日報", "工商時報", "聯合新聞網",
            "MoneyDJ理財網", "鉅亨網", "今周刊", "商業周刊", "財訊"} <= sources


def test_collector_uses_existing_cache_when_all_sources_fail(tmp_path: Path):
    cache = tmp_path / "news.json"
    cache.write_text('{"updated_at":"2026-07-16T00:00:00+00:00","items":[{"title":"舊聞","link":"https://example.com"}]}', encoding="utf-8")
    result = collect_financial_news(cache, [("失敗來源", "台股市場", "http://127.0.0.1:1/fail")], timeout=0.01)
    assert result["using_cache"] is True
    assert result["items"][0]["title"] == "舊聞"


def test_financial_news_is_rendered_on_home_page():
    app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "def render_home()" in app_source
    assert "financial_news.render()" in app_source
    assert '("首頁", "個股分析", "模型預測", "策略回測", "系統狀態")' in app_source
    assert '"財經新聞": financial_news.render' not in app_source


def test_home_page_reads_news_cache_before_manual_refresh():
    page_source = (Path(__file__).parents[1] / "pages" / "financial_news.py").read_text(encoding="utf-8")
    assert "return load_news_cache()" in page_source
    assert "collect_financial_news()" in page_source
