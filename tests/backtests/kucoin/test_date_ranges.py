def test_20210101_20210201(backtest, subtests):
    ret = backtest(start_date="20210101", end_date="20210201")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.11761
    with subtests.test("trades"):
        assert ret.stats.trades == 54
    with subtests.test("wins"):
        assert ret.stats.wins == 50
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 4


def test_20210201_20210301(backtest, subtests):
    ret = backtest(start_date="20210201", end_date="20210301")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.25051
    with subtests.test("trades"):
        assert ret.stats.trades == 89
    with subtests.test("wins"):
        assert ret.stats.wins == 82
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 7


def test_20210301_20210401(backtest, subtests):
    ret = backtest(start_date="20210401", end_date="20210401")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.0
    with subtests.test("trades"):
        assert ret.stats.trades == 0
    with subtests.test("wins"):
        assert ret.stats.wins == 0
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 0


def test_20210401_20210501(backtest, subtests):
    ret = backtest(start_date="20210401", end_date="20210501")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.37207
    with subtests.test("trades"):
        assert ret.stats.trades == 34
    with subtests.test("wins"):
        assert ret.stats.wins == 29
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 5


def test_20210601_20210701(backtest, subtests):
    ret = backtest(start_date="20210601", end_date="20210701")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.15301
    with subtests.test("trades"):
        assert ret.stats.trades == 29
    with subtests.test("wins"):
        assert ret.stats.wins == 27
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 2
