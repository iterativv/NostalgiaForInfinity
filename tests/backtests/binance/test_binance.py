def test_20210101_20220701(backtest):
    ret = backtest(start_date="20210101", end_date="20210201")
    assert ret.results.max_drawdown < 0.475


def test_20210201_20210301(backtest):
    ret = backtest(start_date="20210201", end_date="20210301")
    assert ret.results.max_drawdown < 0.7524


def test_20210301_20210401(backtest):
    ret = backtest(start_date="20210401", end_date="20210401")
    assert ret.results.max_drawdown < 0.5029


def test_20210401_20210501(backtest):
    ret = backtest(start_date="20210401", end_date="20210501")
    assert ret.results.max_drawdown < 0.1265


def test_20210601_20210701(backtest):
    ret = backtest(start_date="20210601", end_date="20210701")
    assert ret.results.max_drawdown < 0.17
