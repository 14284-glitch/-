"""Version-one market universe and the reviewed Taiwan 50 constituent set."""

# Constituent snapshot: 2026-07-15. Review periodically because the index is rebalanced.
TAIWAN_50_CONSTITUENTS = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "2308.TW": "台達電", "2317.TW": "鴻海",
    "3711.TW": "日月光投控", "2303.TW": "聯電", "2383.TW": "台光電", "2327.TW": "國巨",
    "3037.TW": "欣興", "2345.TW": "智邦", "2891.TW": "中信金", "1303.TW": "南亞",
    "2881.TW": "富邦金", "2382.TW": "廣達", "2882.TW": "國泰金", "2887.TW": "台新新光金",
    "2885.TW": "元大金", "2360.TW": "致茂", "3017.TW": "奇鋐", "2344.TW": "華邦電",
    "2408.TW": "南亞科", "2886.TW": "兆豐金", "6669.TW": "緯穎", "2884.TW": "玉山金",
    "2412.TW": "中華電", "2890.TW": "永豐金", "2357.TW": "華碩", "2883.TW": "凱基金",
    "2059.TW": "川湖", "4958.TW": "臻鼎-KY", "3231.TW": "緯創", "2301.TW": "光寶科",
    "1216.TW": "統一", "7769.TW": "鴻勁", "3008.TW": "大立光", "2892.TW": "第一金",
    "2368.TW": "金像電", "2880.TW": "華南金", "3665.TW": "貿聯-KY", "2449.TW": "京元電子",
    "3443.TW": "創意", "8046.TW": "南電", "3661.TW": "世芯-KY", "3653.TW": "健策",
    "5880.TW": "合庫金", "2395.TW": "研華", "2603.TW": "長榮", "4904.TW": "遠傳",
    "3045.TW": "台灣大", "6505.TW": "台塑化",
}

POPULAR_ETFS_TOP_50 = {
    "0050.TW": "元大台灣50", "00631L.TW": "元大台灣50正2", "00981A.TW": "主動統一台股增長",
    "00685L.TW": "群益臺灣加權正2", "00991A.TW": "主動復華未來50", "0056.TW": "元大高股息",
    "009816.TW": "凱基台灣TOP50", "00403A.TW": "主動統一升級50", "00919.TW": "群益台灣精選高息",
    "00988A.TW": "主動統一全球創新", "00927.TW": "群益半導體收益", "00632R.TW": "元大台灣50反1",
    "0052.TW": "富邦科技", "006208.TW": "富邦台50", "00830.TW": "國泰費城半導體",
    "00929.TW": "復華台灣科技優息", "00878.TW": "國泰永續高股息", "00406A.TW": "主動中信台灣收益",
    "00663L.TW": "國泰臺灣加權正2", "00990A.TW": "主動元大AI新經濟", "00713.TW": "元大台灣高息低波",
    "00675L.TW": "富邦臺灣加權正2", "00637L.TW": "元大滬深300正2", "00935.TW": "野村臺灣新科技50",
    "00662.TW": "富邦NASDAQ", "00992A.TW": "主動群益科技創新", "00665L.TW": "富邦恒生國企正2",
    "00646.TW": "元大S&P500", "00918.TW": "大華優利高填息30", "00405A.TW": "主動富邦台灣龍耀",
    "00715L.TW": "期街口布蘭特正2", "00757.TW": "統一FANG+", "00891.TW": "中信關鍵半導體",
    "00982A.TW": "主動群益台灣強棒", "00735.TW": "國泰臺韓科技", "00407A.TW": "主動凱基台灣",
    "00400A.TW": "主動國泰動能高息", "00712.TW": "復華富時不動產", "00881.TW": "國泰台灣科技龍頭",
    "00997A.TW": "主動群益美國增長", "00408A.TW": "主動第一金優股息", "00753L.TW": "中信中國50正2",
    "00953B.TW": "群益優選非投等債", "00947.TW": "台新臺灣IC設計", "00922.TW": "國泰台灣領袖50",
    "00984A.TW": "主動安聯台灣高息", "00892.TW": "富邦台灣半導體", "00961.TW": "FT臺灣永續高息",
    "00865B.TW": "國泰US短期公債", "00650L.TW": "復華香港正2",
}

TW_SYMBOLS = {
    "^TWII": "台灣加權指數",
    **TAIWAN_50_CONSTITUENTS,
    **POPULAR_ETFS_TOP_50,
}


def load_popular_etfs() -> dict[str, str]:
    """Load the latest official popularity snapshot, falling back to the reviewed built-in list."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "popular_etfs.json"
    if not path.exists():
        return dict(POPULAR_ETFS_TOP_50)
    try:
        records = json.loads(path.read_text(encoding="utf-8"))["items"]
        return {f"{item['code']}.TW": item["name"] for item in records[:50]}
    except (KeyError, TypeError, ValueError, OSError):
        return dict(POPULAR_ETFS_TOP_50)


def load_tw_symbols() -> dict[str, str]:
    return {"^TWII": "台灣加權指數", **TAIWAN_50_CONSTITUENTS, **load_popular_etfs()}

US_SYMBOLS = {
    "TSM": "台積電 ADR", "NVDA": "NVIDIA", "AMD": "AMD", "AVGO": "Broadcom", "MU": "Micron",
    "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^SOX": "費城半導體指數", "^VIX": "VIX",
    "TWD=X": "美元兌新台幣", "^TNX": "美國十年期公債殖利率",
}
