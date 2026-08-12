"""Short-prompt UX contracts for Korean equity comprehensive analysis."""

from src.agent.context import ContextBuilder, expand_short_analysis_prompt


def test_expands_samsung_short_prompt_into_standard_korean_analysis_mode():
    expanded = expand_short_analysis_prompt("005930.KS 종합 분석")

    assert expanded.startswith("005930.KS 종합 분석\n")
    assert "대상 종목: 005930.KS" in expanded
    assert 'get_market_data(..., market="kr")' in expanded
    assert "pykrx source-lock" in expanded
    assert "yfinance" in expanded
    assert "non-price fallback" in expanded
    assert "derived" in expanded
    assert "단 한 번의" in expanded
    assert 'fields=["ohlcv", "derived", "fundamentals", "market_cap", "investor_flow"]' in expanded
    assert "MA20/60/120/200" in expanded
    assert "1주/1개월/3개월/6개월/요청기간 수익률" in expanded
    assert "20/60/120일 및 요청기간 평균 거래량" in expanded
    assert "PER/PBR/EPS/BPS" in expanded
    assert "시가총액" in expanded
    assert "investor flow" in expanded
    assert "provenance" in expanded
    assert "unavailable" in expanded
    assert "주문 또는 증권사 API는 사용하지 않는다" in expanded
    assert "사실성 정책" in expanded
    assert "점수 분리/산정 보류 정책" in expanded
    assert "요약, 시장데이터/기술 분석" in expanded


def test_expands_bare_korean_ticker_and_compact_intent():
    expanded = expand_short_analysis_prompt("005930 종합분석")

    assert "대상 종목: 005930" in expanded
    assert 'market="kr"' in expanded


def test_expands_any_explicit_korean_board_symbol():
    for prompt, symbol in (
        ("000660.KS 종합 분석", "000660.KS"),
        ("035720.KQ 종합 분석", "035720.KQ"),
    ):
        assert f"대상 종목: {symbol}" in expand_short_analysis_prompt(prompt)


def test_does_not_expand_detailed_or_unrelated_prompts():
    prompts = (
        "005930.KS 종합 분석하되 2024년 이후만 봐줘",
        "AAPL 종합 분석",
        "005930.KS 기술 분석",
        "삼성전자 종합 분석",
    )

    for prompt in prompts:
        assert expand_short_analysis_prompt(prompt) == prompt


def test_samsung_short_prompt_smoke_reaches_final_agent_message():
    class _Registry:
        _tools = {}

    class _Memory:
        @staticmethod
        def to_summary():
            return "empty"

    class _Skills:
        skills = {}

        @staticmethod
        def get_descriptions():
            return "(none)"

    messages = ContextBuilder(_Registry(), _Memory(), _Skills()).build_messages(
        "005930.KS 종합 분석"
    )

    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"].startswith("005930.KS 종합 분석\n")
    assert "[자동 확장: 한국 주식 표준 종합 분석]" in messages[-1]["content"]
    assert "대상 종목: 005930.KS" in messages[-1]["content"]


def test_memory_recall_preserves_short_prompt_expansion():
    class _Registry:
        _tools = {}

    class _Memory:
        @staticmethod
        def to_summary():
            return "empty"

    class _Skills:
        skills = {}

        @staticmethod
        def get_descriptions():
            return "(none)"

    class _Recall:
        title = "preference"
        memory_type = "user"
        body = "Korean reports"

    class _PersistentMemory:
        snapshot = "saved"

        @staticmethod
        def find_relevant(_message, max_results):
            assert max_results == 3
            return [_Recall()]

    messages = ContextBuilder(
        _Registry(), _Memory(), _Skills(), _PersistentMemory()
    ).build_messages("005930.KS 종합 분석")

    assert "<recalled-memories>" in messages[-1]["content"]
    assert "[자동 확장: 한국 주식 표준 종합 분석]" in messages[-1]["content"]
    assert "대상 종목: 005930.KS" in messages[-1]["content"]
