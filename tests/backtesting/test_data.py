from tradingagents.backtesting.types import Bar, InstrumentKind
from tradingagents.backtesting.data import FakeBarProvider, get_spec


def test_get_spec_known_forex_is_forex():
    spec = get_spec("XAUUSD")
    assert spec.kind == InstrumentKind.FOREX
    assert spec.point > 0


def test_get_spec_unknown_defaults_to_equity():
    spec = get_spec("AAPL")
    assert spec.kind == InstrumentKind.EQUITY


def test_fake_provider_filters_and_sorts_by_date():
    bars = [Bar("2024-01-03", 3, 3, 3, 3), Bar("2024-01-01", 1, 1, 1, 1),
            Bar("2024-01-02", 2, 2, 2, 2)]
    provider = FakeBarProvider({"AAPL": bars})
    out = provider.get_bars("AAPL", "2024-01-01", "2024-01-02", "1d")
    assert [b.date for b in out] == ["2024-01-01", "2024-01-02"]
