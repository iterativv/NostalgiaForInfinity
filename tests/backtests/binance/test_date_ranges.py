def test_20210101_20210201(backtest, subtests):
    ret = backtest(start_date="20210101", end_date="20210201")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.47411
    with subtests.test("trades"):
        assert ret.stats.trades == 187
    with subtests.test("wins"):
        assert ret.stats.wins == 169
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 18


def test_20210201_20210301(backtest, subtests):
    ret = backtest(start_date="20210201", end_date="20210301")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.75234
    with subtests.test("trades"):
        assert ret.stats.trades == 223
    with subtests.test("wins"):
        assert ret.stats.wins == 201
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 22


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
        assert round(ret.results.max_drawdown, 5) == 0.12640
    with subtests.test("trades"):
        assert ret.stats.trades == 254
    with subtests.test("wins"):
        assert ret.stats.wins == 248
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 6


def test_20210601_20210701(backtest, subtests):
    ret = backtest(start_date="20210601", end_date="20210701")
    with subtests.test("max_drawdown"):
        assert round(ret.results.max_drawdown, 5) == 0.16666
    with subtests.test("trades"):
        assert ret.stats.trades == 128
    with subtests.test("wins"):
        assert ret.stats.wins == 120
    with subtests.test("draws"):
        assert ret.stats.draws == 0
    with subtests.test("losses"):
        assert ret.stats.losses == 8
