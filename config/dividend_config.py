"""Taiwan dividend calculator rules kept outside UI components."""

SHARES_PER_LOT = 1_000

# Taiwan NHI supplementary premium rules. Review when the authority changes them.
NHI_SUPPLEMENTARY_PREMIUM_RATE = 0.0211
NHI_DIVIDEND_PAYMENT_THRESHOLD = 20_000.0
NHI_DIVIDEND_PAYMENT_CAP = 10_000_000.0

DIVIDEND_DISCLAIMER = (
    "股息及稅費試算僅供參考，實際股利、所得稅及二代健保補充保費，"
    "應依公司公告、個人所得狀況及台灣當年度相關規定為準。"
)

REINVESTMENT_DISCLAIMER = (
    "本功能為情境模擬，計算結果不代表未來實際股價、股息或投資報酬。"
)
