import ast
from pathlib import Path

import pytest
from freqtrade.configuration import Configuration
from freqtrade.resolvers import StrategyResolver

from codemods.ho_to_raw_codemod import replace_all_references
from codemods.ho_to_raw_codemod import transform_code
from tests.unit.conftest import REPO_ROOT


def test_transform_code_categorical_param():
    categorical_param = (
        "CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True)"
    )
    categorical_param_edge = (
        "CategoricalParameter([True, False], space='buy', optimize=False, load=True, default=False)"
    )
    assert transform_code(categorical_param) == "True"
    assert transform_code(categorical_param_edge) == "False"
    # Should leave it untouched
    assert transform_code("CategoricalParameter") == "CategoricalParameter"


def test_transform_code_decimal_param():
    decimal_param = "DecimalParameter(0.001, 0.05, default=0.015, space='buy', decimals=3, optimize=False, load=True)"
    decimal_param_edge = "DecimalParameter(0.001, 0.05, space='buy', decimals=3, optimize=False, load=True, default=0.12)"
    assert transform_code(decimal_param) == "0.015"
    assert transform_code(decimal_param_edge) == "0.12"
    assert transform_code("DecimalParameter") == "DecimalParameter"


def test_transform_code_int_param():
    int_param = "IntParameter(700, 2000, default=900, space='sell', optimize=False, load=True)"
    int_param_edge = "IntParameter(700, 2000, space='sell', optimize=False, load=True,default=413)"
    assert transform_code(int_param) == "900"
    assert transform_code(int_param_edge) == "413"
    assert transform_code("IntParameter") == "IntParameter"


def test_transform_code_real_param():
    real_param = (
        "RealParameter(20.542, 75.123,default=90.23, space='sell', optimize=False, load=True)"
    )
    real_param_edge = (
        "RealParameter(20.542, 75.123, space='sell', optimize=False, load=True, default=95.2311)"
    )
    assert transform_code(real_param) == "90.23"
    assert transform_code(real_param_edge) == "95.2311"
    assert transform_code("RealParameter") == "RealParameter"


def test_transform_code_dict():
    code_input = """
buy_protection_params = {
    1: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="26", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="28", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="80", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="70", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
    }
}
    """

    expected_output = """
buy_protection_params = {
    1: {
            "enable"                    : True,
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : True,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips"                 : True,
            "safe_dips_type"            : "80",
            "safe_pump"                 : True,
            "safe_pump_type"            : "70",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False
    }
}
"""
    assert transform_code(code_input.strip()) == expected_output.strip()


def test_transform_code_syntax():
    source = ""
    with open(REPO_ROOT.joinpath("NostalgiaForInfinityNext.py")) as f:
        source = f.read()

    is_valid = True
    try:
        ast.parse(transform_code(source))
    except SyntaxError:
        is_valid = False

    assert is_valid is True


def test_transform_and_replace_references():
    test_data_dir = REPO_ROOT.joinpath("tests/unit/test_data")
    config = Configuration.from_files([])
    config["strategy"] = "Strategy1"
    config["strategy_path"] = test_data_dir.joinpath("input")
    strategy = StrategyResolver.load_strategy(config)
    source_input = ""
    with open(config["strategy_path"].joinpath("Strategy1.py")) as f:
        source_input = f.read()
    transformed_input = transform_code(replace_all_references(strategy, source_input))

    expected_source = ""
    with open(test_data_dir.joinpath("output/Strategy1.py")) as f:
        expected_source = f.read()

    assert transformed_input.strip() == expected_source.strip()

    # assert transformed_input.strip() == expected_output.strip()
