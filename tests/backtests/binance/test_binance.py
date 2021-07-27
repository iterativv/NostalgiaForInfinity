def test_20210601_20210701(backtest):
    ret = backtest(start_date="20210601", end_date="20210701")
    assert ret.results.max_drawdown < 0.17
