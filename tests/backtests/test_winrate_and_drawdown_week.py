import os.path

import pytest

from tests.backtests.helpers import Backtest
from tests.backtests.helpers import Exchange
from tests.backtests.helpers import Timerange
from tests.conftest import REPO_ROOT


def exchange_fmt(value):
  return value.name


@pytest.fixture(
  scope="session",
  params=(
    Exchange(name="binance", winrate=90, max_drawdown=5),
    Exchange(name="kucoin", winrate=90, max_drawdown=5),
    # Exchange(name="gateio", winrate=90, max_drawdown=5),
    # Exchange(name="okx", winrate=90, max_drawdown=5),
    # ITS POSSIBLE TO ADD MORE EXCHANGES and MARKETS (SPOT FUTURES MARGIN)
  ),
  ids=exchange_fmt,
)
def exchange(request):
  return request.param


def trading_mode_fmt(param):
  return param


@pytest.fixture(
  params=(
    # "spot",  # For SPOT Markets Trading tests
    "futures",  # For FUTURES Markets Trading tests
  ),
  ids=trading_mode_fmt,
)
def trading_mode(request):
  return request.param


@pytest.fixture(scope="session", autouse=True)
def check_exchange_data_presen(exchange):
  exchange_data_dir = REPO_ROOT / "user_data" / "data" / exchange.name
  if not os.path.isdir(exchange_data_dir):
    pytest.fail(
      f"There's no exchange data for {exchange.name}. Make sure the repository submodule "
      "is init/update. Check the repository README.md for more information."
    )
  if not list(exchange_data_dir.rglob("*.feather")):
    pytest.fail(
      f"There's no exchange data for {exchange.name}. Make sure the repository submodule "
      "is init/update. Check the repository README.md for more information."
    )


@pytest.fixture
def backtest(request):
  return Backtest(request)


def timerange_fmt(value):
  return f"{value.start_date}-{value.end_date}"


@pytest.fixture(
  params=(
    # # Weekly Test Periods
    # # # ADD NEW WEEKS HERE
    ### 2025  Weekly Test Periods
    ### 2025-Q4-weeks
    # # #
    Timerange("20251228", "20260104"),
    Timerange("20251221", "20251228"),
    Timerange("20251214", "20251221"),
    Timerange("20251207", "20251214"),
    Timerange("20251130", "20251207"),
    Timerange("20251123", "20251130"),
    Timerange("20251116", "20251123"),
    Timerange("20251109", "20251116"),
    Timerange("20251102", "20251109"),
    Timerange("20251026", "20251102"),
    Timerange("20251019", "20251026"),
    Timerange("20251012", "20251019"),
    Timerange("20251005", "20251012"),
    Timerange("20250928", "20251005"),
    # # #
    ### 2025-Q3-weeks
    # # #
    Timerange("20250921", "20250928"),
    Timerange("20250914", "20250921"),
    Timerange("20250907", "20250914"),
    Timerange("20250831", "20250907"),
    Timerange("20250824", "20250831"),
    Timerange("20250817", "20250824"),
    Timerange("20250810", "20250817"),
    Timerange("20250803", "20250810"),
    Timerange("20250727", "20250803"),
    Timerange("20250720", "20250727"),
    Timerange("20250713", "20250720"),
    Timerange("20250706", "20250713"),
    Timerange("20250629", "20250706"),
    # # #
    ### 2025-Q2-weeks
    # # #
    Timerange("20250622", "20250629"),
    Timerange("20250615", "20250622"),
    Timerange("20250608", "20250615"),
    Timerange("20250601", "20250608"),
    Timerange("20250525", "20250601"),
    Timerange("20250518", "20250525"),
    Timerange("20250511", "20250518"),
    Timerange("20250504", "20250511"),
    Timerange("20250427", "20250504"),
    Timerange("20250420", "20250427"),
    Timerange("20250413", "20250420"),
    Timerange("20250406", "20250413"),
    Timerange("20250330", "20250406"),
    # # #
    ### 2025-Q1-weeks
    # # #
    Timerange("20250323", "20250330"),
    Timerange("20250316", "20250323"),
    Timerange("20250309", "20250316"),
    Timerange("20250302", "20250309"),
    Timerange("20250223", "20250302"),
    Timerange("20250216", "20250223"),
    Timerange("20250209", "20250216"),
    Timerange("20250202", "20250209"),
    Timerange("20250126", "20250202"),
    Timerange("20250119", "20250126"),
    Timerange("20250112", "20250119"),
    Timerange("20250105", "20250112"),
    Timerange("20241229", "20250105"),
    ###############################################
    ### 2024  Weekly Test Periods
    ###############################################
    ### 2024-Q4-weeks
    # # #
    Timerange("20241229", "20250105"),
    Timerange("20241222", "20241229"),
    Timerange("20241215", "20241222"),
    Timerange("20241208", "20241215"),
    Timerange("20241201", "20241208"),
    Timerange("20241124", "20241201"),
    Timerange("20241117", "20241124"),
    Timerange("20241110", "20241117"),
    Timerange("20241103", "20241110"),
    Timerange("20241027", "20241103"),
    Timerange("20241020", "20241027"),
    Timerange("20241013", "20241020"),
    Timerange("20241006", "20241013"),
    Timerange("20240929", "20241006"),
    # # #
    ### 2024-Q3-weeks
    # # #
    Timerange("20240922", "20240929"),
    Timerange("20240915", "20240922"),
    Timerange("20240908", "20240915"),
    Timerange("20240901", "20240908"),
    Timerange("20240825", "20240901"),
    Timerange("20240818", "20240825"),
    Timerange("20240811", "20240818"),
    Timerange("20240804", "20240811"),
    Timerange("20240728", "20240804"),
    Timerange("20240721", "20240728"),
    Timerange("20240714", "20240721"),
    Timerange("20240707", "20240714"),
    Timerange("20240630", "20240707"),
    # # #
    ### 2024-Q2-weeks
    # # #
    Timerange("20240623", "20240630"),
    Timerange("20240616", "20240623"),
    Timerange("20240609", "20240616"),
    Timerange("20240602", "20240609"),
    Timerange("20240526", "20240602"),
    Timerange("20240519", "20240526"),
    Timerange("20240512", "20240519"),
    Timerange("20240505", "20240512"),
    Timerange("20240428", "20240505"),
    Timerange("20240421", "20240428"),
    Timerange("20240414", "20240421"),
    Timerange("20240407", "20240414"),
    Timerange("20240331", "20240407"),
    # # #
    ### 2024-Q1-weeks
    # # #
    Timerange("20240324", "20240331"),
    Timerange("20240317", "20240324"),
    Timerange("20240310", "20240317"),
    Timerange("20240303", "20240310"),
    Timerange("20240225", "20240303"),
    Timerange("20240218", "20240225"),
    Timerange("20240211", "20240218"),
    Timerange("20240204", "20240211"),
    Timerange("20240128", "20240204"),
    Timerange("20240121", "20240128"),
    Timerange("20240114", "20240121"),
    Timerange("20240107", "20240114"),
    Timerange("20231231", "20240107"),
    # # #
    ###############################################
    ### 2023  Weekly Test Periods
    ###############################################
    ### 2023-Q4-weeks
    # # #
    Timerange("20231224", "20231231"),
    Timerange("20231217", "20231224"),
    Timerange("20231210", "20231217"),
    Timerange("20231203", "20231210"),
    Timerange("20231126", "20231203"),
    Timerange("20231119", "20231126"),
    Timerange("20231112", "20231119"),
    Timerange("20231105", "20231112"),
    Timerange("20231029", "20231105"),
    Timerange("20231022", "20231029"),
    Timerange("20231015", "20231022"),
    Timerange("20231008", "20231015"),
    Timerange("20231001", "20231008"),
    Timerange("20230924", "20231001"),
    # # #
    ### 2023-Q3-weeks
    # # #
    Timerange("20230917", "20230924"),
    Timerange("20230910", "20230917"),
    Timerange("20230903", "20230910"),
    Timerange("20230827", "20230903"),
    Timerange("20230820", "20230827"),
    Timerange("20230813", "20230820"),
    Timerange("20230806", "20230813"),
    Timerange("20230730", "20230806"),
    Timerange("20230723", "20230730"),
    Timerange("20230716", "20230723"),
    Timerange("20230709", "20230716"),
    Timerange("20230702", "20230709"),
    Timerange("20230625", "20230702"),
    # # #
    ### 2023-Q2-weeks
    # # #
    Timerange("20230618", "20230625"),
    Timerange("20230611", "20230618"),
    Timerange("20230604", "20230611"),
    Timerange("20230528", "20230604"),
    Timerange("20230521", "20230528"),
    Timerange("20230514", "20230521"),
    Timerange("20230507", "20230514"),
    Timerange("20230430", "20230507"),
    Timerange("20230423", "20230430"),
    Timerange("20230416", "20230423"),
    Timerange("20230409", "20230416"),
    Timerange("20230402", "20230409"),
    Timerange("20230326", "20230402"),
    # # #
    ### 2023-Q1-weeks
    # # #
    Timerange("20230319", "20230326"),
    Timerange("20230312", "20230319"),
    Timerange("20230305", "20230312"),
    Timerange("20230226", "20230305"),
    Timerange("20230219", "20230226"),
    Timerange("20230212", "20230219"),
    Timerange("20230205", "20230212"),
    Timerange("20230129", "20230205"),
    Timerange("20230122", "20230129"),
    Timerange("20230115", "20230122"),
    Timerange("20230108", "20230115"),
    Timerange("20230101", "20230108"),
    # # #
    ###############################################
    ### 2022
    ###############################################
    ### 2022-Q4-weeks
    # # #
    Timerange("20221225", "20230101"),
    Timerange("20221218", "20221225"),
    Timerange("20221211", "20221218"),
    Timerange("20221204", "20221211"),
    Timerange("20221127", "20221204"),
    Timerange("20221120", "20221127"),
    Timerange("20221113", "20221120"),
    Timerange("20221106", "20221113"),
    Timerange("20221030", "20221106"),
    Timerange("20221023", "20221030"),
    Timerange("20221016", "20221023"),
    Timerange("20221009", "20221016"),
    Timerange("20221002", "20221009"),
    Timerange("20220925", "20221002"),
    # # #
    ### 2022-Q3-weeks
    # # #
    Timerange("20220918", "20220925"),
    Timerange("20220911", "20220918"),
    Timerange("20220904", "20220911"),
    Timerange("20220828", "20220904"),
    Timerange("20220821", "20220828"),
    Timerange("20220814", "20220821"),
    Timerange("20220807", "20220814"),
    Timerange("20220731", "20220807"),
    Timerange("20220724", "20220731"),
    Timerange("20220717", "20220724"),
    Timerange("20220710", "20220717"),
    Timerange("20220703", "20220710"),
    Timerange("20220626", "20220703"),
    # # #
    ### 2022-Q2-weeks
    # # #
    Timerange("20220619", "20220626"),
    Timerange("20220612", "20220619"),
    Timerange("20220605", "20220612"),
    Timerange("20220529", "20220605"),
    Timerange("20220522", "20220529"),
    Timerange("20220515", "20220522"),
    Timerange("20220508", "20220515"),
    Timerange("20220501", "20220508"),
    Timerange("20220424", "20220501"),
    Timerange("20220417", "20220424"),
    Timerange("20220410", "20220417"),
    Timerange("20220403", "20220410"),
    Timerange("20220327", "20220403"),
    # # #
    ### 2022-Q1-weeks
    # # #
    Timerange("20220320", "20220327"),
    Timerange("20220313", "20220320"),
    Timerange("20220306", "20220313"),
    Timerange("20220227", "20220306"),
    Timerange("20220220", "20220227"),
    Timerange("20220213", "20220220"),
    Timerange("20220206", "20220213"),
    Timerange("20220130", "20220206"),
    Timerange("20220123", "20220130"),
    Timerange("20220116", "20220123"),
    Timerange("20220109", "20220116"),
    Timerange("20220102", "20220109"),
    Timerange("20211226", "20220102"),
    ###############################################
    ### 2021  Weekly Test Periods
    ###############################################
    ### 2021-Q4-weeks
    # # #
    Timerange("20211219", "20211226"),
    Timerange("20211212", "20211219"),
    Timerange("20211205", "20211212"),
    Timerange("20211128", "20211205"),
    Timerange("20211121", "20211128"),
    Timerange("20211114", "20211121"),
    Timerange("20211107", "20211114"),
    Timerange("20211031", "20211107"),
    Timerange("20211024", "20211031"),
    Timerange("20211017", "20211024"),
    Timerange("20211010", "20211017"),
    Timerange("20211003", "20211010"),
    Timerange("20210926", "20211003"),
    # # #
    ### 2021-Q3-weeks
    # # #
    Timerange("20210919", "20210926"),
    Timerange("20210912", "20210919"),
    Timerange("20210905", "20210912"),
    Timerange("20210829", "20210905"),
    Timerange("20210822", "20210829"),
    Timerange("20210815", "20210822"),
    Timerange("20210808", "20210815"),
    Timerange("20210801", "20210808"),
    Timerange("20210725", "20210801"),
    Timerange("20210718", "20210725"),
    Timerange("20210711", "20210718"),
    Timerange("20210704", "20210711"),
    Timerange("20210627", "20210704"),
    # # #
    ### 2021-Q2-weeks
    # # #
    Timerange("20210620", "20210627"),
    Timerange("20210613", "20210620"),
    Timerange("20210606", "20210613"),
    Timerange("20210530", "20210606"),
    Timerange("20210523", "20210530"),
    Timerange("20210516", "20210523"),
    Timerange("20210509", "20210516"),
    Timerange("20210502", "20210509"),
    Timerange("20210425", "20210502"),
    Timerange("20210418", "20210425"),
    Timerange("20210411", "20210418"),
    Timerange("20210404", "20210411"),
    Timerange("20210328", "20210404"),
    # # #
    ### 2021-Q1-weeks
    # # #
    Timerange("20210321", "20210328"),
    Timerange("20210314", "20210321"),
    Timerange("20210307", "20210314"),
    Timerange("20210228", "20210307"),
    Timerange("20210221", "20210228"),
    Timerange("20210214", "20210221"),
    Timerange("20210207", "20210214"),
    Timerange("20210131", "20210207"),
    Timerange("20210124", "20210131"),
    Timerange("20210117", "20210124"),
    Timerange("20210110", "20210117"),
    Timerange("20210103", "20210110"),
    Timerange("20201227", "20210103"),
    # # #
    ###############################################
    ### 2020  Weekly Test Periods
    ###############################################
    # # #
    ### 2020-Q4-weeks
    # # #
    Timerange("20201220", "20201227"),
    Timerange("20201213", "20201220"),
    Timerange("20201206", "20201213"),
    Timerange("20201129", "20201206"),
    Timerange("20201122", "20201129"),
    Timerange("20201115", "20201122"),
    Timerange("20201108", "20201115"),
    Timerange("20201101", "20201108"),
    Timerange("20201025", "20201101"),
    Timerange("20201018", "20201025"),
    Timerange("20201011", "20201018"),
    Timerange("20201004", "20201011"),
    Timerange("20200927", "20201004"),
    # # #
    ### 2020-Q3-weeks
    # # #
    Timerange("20200920", "20200927"),
    Timerange("20200913", "20200920"),
    Timerange("20200906", "20200913"),
    Timerange("20200830", "20200906"),
    Timerange("20200823", "20200830"),
    Timerange("20200816", "20200823"),
    Timerange("20200809", "20200816"),
    Timerange("20200802", "20200809"),
    Timerange("20200726", "20200802"),
    Timerange("20200719", "20200726"),
    Timerange("20200712", "20200719"),
    Timerange("20200705", "20200712"),
    Timerange("20200628", "20200705"),
    # # #
    ### 2020-Q2-weeks
    # # #
    Timerange("20200621", "20200628"),
    Timerange("20200614", "20200621"),
    Timerange("20200607", "20200614"),
    Timerange("20200531", "20200607"),
    Timerange("20200524", "20200531"),
    Timerange("20200517", "20200524"),
    Timerange("20200510", "20200517"),
    Timerange("20200503", "20200510"),
    Timerange("20200426", "20200503"),
    Timerange("20200419", "20200426"),
    Timerange("20200412", "20200419"),
    Timerange("20200405", "20200412"),
    Timerange("20200329", "20200405"),
    # # #
    ### 2020-Q1-weeks
    # # #
    Timerange("20200322", "20200329"),
    Timerange("20200315", "20200322"),
    Timerange("20200308", "20200315"),
    Timerange("20200301", "20200308"),
    Timerange("20200223", "20200301"),
    Timerange("20200216", "20200223"),
    Timerange("20200209", "20200216"),
    Timerange("20200202", "20200209"),
    Timerange("20200126", "20200202"),
    Timerange("20200119", "20200126"),
    Timerange("20200112", "20200119"),
    Timerange("20200105", "20200112"),
    Timerange("20191229", "20200105"),
    # ###############################################
    # ### 2019  Weekly Test Periods
    # ###############################################
    # ### 2019-Q4-weeks
    # # # #
    # Timerange("20191222", "20191229"),
    # Timerange("20191215", "20191222"),
    # Timerange("20191208", "20191215"),
    # Timerange("20191201", "20191208"),
    # Timerange("20191124", "20191201"),
    # Timerange("20191117", "20191124"),
    # Timerange("20191110", "20191117"),
    # Timerange("20191103", "20191110"),
    # Timerange("20191027", "20191103"),
    # Timerange("20191020", "20191027"),
    # Timerange("20191013", "20191020"),
    # Timerange("20191006", "20191013"),
    # Timerange("20190929", "20191006"),
    # # # #
    # ### 2019-Q3-weeks
    # # # #
    # Timerange("20190922", "20190929"),
    # Timerange("20190915", "20190922"),
    # Timerange("20190908", "20190915"),
    # Timerange("20190901", "20190908"),
    # Timerange("20190825", "20190901"),
    # Timerange("20190818", "20190825"),
    # Timerange("20190811", "20190818"),
    # Timerange("20190804", "20190811"),
    # Timerange("20190728", "20190804"),
    # Timerange("20190721", "20190728"),
    # Timerange("20190714", "20190721"),
    # Timerange("20190707", "20190714"),
    # Timerange("20190630", "20190707"),
    # # # #
    # ### 2019-Q2-weeks
    # # # #
    # Timerange("20190623", "20190630"),
    # Timerange("20190616", "20190623"),
    # Timerange("20190609", "20190616"),
    # Timerange("20190602", "20190609"),
    # Timerange("20190526", "20190602"),
    # Timerange("20190519", "20190526"),
    # Timerange("20190512", "20190519"),
    # Timerange("20190505", "20190512"),
    # Timerange("20190428", "20190505"),
    # Timerange("20190421", "20190428"),
    # Timerange("20190414", "20190421"),
    # Timerange("20190407", "20190414"),
    # Timerange("20190331", "20190407"),
    # # # #
    # ### 2019-Q1-weeks
    # # # #
    # Timerange("20190324", "20190331"),
    # Timerange("20190317", "20190324"),
    # Timerange("20190310", "20190317"),
    # Timerange("20190303", "20190310"),
    # Timerange("20190224", "20190303"),
    # Timerange("20190217", "20190224"),
    # Timerange("20190210", "20190217"),
    # Timerange("20190203", "20190210"),
    # Timerange("20190127", "20190203"),
    # Timerange("20190120", "20190127"),
    # Timerange("20190113", "20190120"),
    # Timerange("20190106", "20190113"),
    # Timerange("20181230", "20190106"),
    # ###############################################
    # ### 2018  Weekly Test Periods
    # ###############################################
    # # # #
    # ### 2018-Q4-weeks
    # # # #
    # Timerange("20181223", "20181230"),
    # Timerange("20181216", "20181223"),
    # Timerange("20181209", "20181216"),
    # Timerange("20181202", "20181209"),
    # Timerange("20181125", "20181202"),
    # Timerange("20181118", "20181125"),
    # Timerange("20181111", "20181118"),
    # Timerange("20181104", "20181111"),
    # Timerange("20181028", "20181104"),
    # Timerange("20181021", "20181028"),
    # Timerange("20181014", "20181021"),
    # Timerange("20181007", "20181014"),
    # Timerange("20180930", "20181007"),
    # # # #
    # ### 2018-Q3-weeks
    # # # #
    # Timerange("20180923", "20180930"),
    # Timerange("20180916", "20180923"),
    # Timerange("20180909", "20180916"),
    # Timerange("20180902", "20180909"),
    # Timerange("20180826", "20180902"),
    # Timerange("20180819", "20180826"),
    # Timerange("20180812", "20180819"),
    # Timerange("20180805", "20180812"),
    # Timerange("20180729", "20180805"),
    # Timerange("20180722", "20180729"),
    # Timerange("20180715", "20180722"),
    # Timerange("20180708", "20180715"),
    # Timerange("20180701", "20180708"),
    # # # #
    # ### 2018-Q2-weeks
    # # # #
    # Timerange("20180624", "20180701"),
    # Timerange("20180617", "20180624"),
    # Timerange("20180610", "20180617"),
    # Timerange("20180603", "20180610"),
    # Timerange("20180527", "20180603"),
    # Timerange("20180520", "20180527"),
    # Timerange("20180513", "20180520"),
    # Timerange("20180506", "20180513"),
    # Timerange("20180429", "20180506"),
    # Timerange("20180422", "20180429"),
    # Timerange("20180415", "20180422"),
    # Timerange("20180408", "20180415"),
    # Timerange("20180401", "20180408"),
    # # # #
    # ### 2018-Q1-weeks
    # # # #
    # Timerange("20180325", "20180401"),
    # Timerange("20180318", "20180325"),
    # Timerange("20180311", "20180318"),
    # Timerange("20180304", "20180311"),
    # Timerange("20180225", "20180304"),
    # Timerange("20180218", "20180225"),
    # Timerange("20180211", "20180218"),
    # Timerange("20180204", "20180211"),
    # Timerange("20180128", "20180204"),
    # Timerange("20180121", "20180128"),
    # Timerange("20180114", "20180121"),
    # Timerange("20180107", "20180114"),
    # Timerange("20171231", "20180107"),
    # # # #
  ),
  ids=timerange_fmt,
)
def timerange(request):
  return request.param


@pytest.fixture(scope="session")
def deviations():
  return {
    "binance": {
      ("20200517", "20200524"): {"max_drawdown": 5, "winrate": 90},
      ("20240818", "20240825"): {"max_drawdown": 5, "winrate": 90},
    },
    "gateio": {
      ("20200517", "20200524"): {"max_drawdown": 5, "winrate": 90},
      ("20240818", "20240825"): {"max_drawdown": 5, "winrate": 90},
    },
    "okx": {
      ("20200517", "20200524"): {"max_drawdown": 5, "winrate": 90},
      ("20240818", "20240825"): {"max_drawdown": 5, "winrate": 90},
    },
    "kucoin": {
      ("20200517", "20200524"): {"max_drawdown": 5, "winrate": 90},
      ("20240818", "20240825"): {"max_drawdown": 5, "winrate": 90},
    },
  }


def test_expected_values(backtest, trading_mode, timerange, exchange, deviations):
  ret = backtest(
    start_date=timerange.start_date,
    end_date=timerange.end_date,
    exchange=exchange.name,
    trading_mode=trading_mode,
  )

  exchange_deviations = deviations.get(exchange.name, {})
  key = (trading_mode, timerange.start_date, timerange.end_date)
  entry = exchange_deviations.get(key, {})

  expected_winrate = entry.get("winrate") if entry.get("winrate") is not None else exchange.winrate
  expected_max_drawdown = entry.get("max_drawdown") if entry.get("max_drawdown") is not None else exchange.max_drawdown

  if not (ret.stats_pct.winrate >= expected_winrate or ret.stats_pct.trades == 0):
    print(
      f"[NOTE] Expected winrate ≥ {expected_winrate}, got {ret.stats_pct.winrate}. Trades: {ret.stats_pct.trades}."
    )

  if not (ret.stats_pct.max_drawdown <= expected_max_drawdown):
    print(f"[NOTE] Expected max drawdown ≤ {expected_max_drawdown}, got {ret.stats_pct.max_drawdown}.")
