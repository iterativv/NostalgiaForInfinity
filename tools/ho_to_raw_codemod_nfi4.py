import ast
import re
from freqtrade.configuration import Configuration
from freqtrade.resolvers import StrategyResolver
from freqtrade.strategy.interface import IStrategy
import os

pattern = re.compile(
  r"(?:CategoricalParameter|DecimalParameter|IntParameter|RealParameter)\(.+?default=(?P<value>[^,\n]+) ([^\)]|\n)*?\)",
  re.MULTILINE | re.DOTALL | re.IGNORECASE | re.VERBOSE,
)


def validate_syntax(src: str):
  ast.parse(src)  # Throw if syntax is not valid


def transform_code(src: str):
  def repl(matchobj):
    return matchobj.group(1)

  return pattern.subn(repl, src)


def replace_references(source: str, references_to_replace: list[str]):
  """
  Replace references from transformed code

  :param transformed_code: Transformed code
  :param references_to_replace: A list of variables to remove its references
  """
  modified_source = source
  for reference_to_replace in references_to_replace:
    modified_source = modified_source.replace(f"{reference_to_replace}.value", reference_to_replace)
  return modified_source


def replace_classname(source: str, old_name, new_name: str):
  """
  Optional renaming of the NFI class in the generated RAW file.
  For example, for the NostalgiaForInfinityX4_Raw.py file,
  this could be the NostalgiaForInfinityX4_Raw class.
  Requires a change in the FT configuration

    NostalgiaForInfinityX4 ==> NostalgiaForInfinityX4_Raw
  """
  # class NostalgiaForInfinityX4(IStrategy):
  old_code = f"class {old_name}(IStrategy):"
  # class NostalgiaForInfinityX4_Raw(IStrategy):
  new_code = f"class {new_name}(IStrategy):"
  print(f"Replacing strategy class name '{old_name}' => '{new_name}' ...")
  return source.replace(old_code, new_code)


def replace_all_references(strategy: IStrategy, source: str):
  params = strategy.detect_all_parameters()
  buy_params = [param[0] for param in params["buy"]]
  sell_params = [param[0] for param in params["sell"]]
  if len(buy_params) > 0:
    print("Replacing references of 'buy' hyperopting params...")
    new_source = replace_references(source, buy_params)
  if len(sell_params) > 0:
    print("Replacing references of 'sell' hyperopting params...")
    new_source = replace_references(new_source, sell_params)

  print("Replacing 'references' of 'buy_protection_params' hyperopting params...")
  new_source, bp = re.subn(r"(buy_protection_params\[([\"\'])[\w\_]+\2\]).value", r"\1", new_source)
  if bp > 0:
    print(f"{bp} references transformed.")

  return new_source


# Abnormal termination
def args_error(err_msg=None):
  if err_msg != None:
    print(f"ERROR: {err_msg}")

  exit(1)


if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--strategy",
    "-s",
    metavar="STRATEGY",
    help="Name of the strategy in original NFI file",
    type=str,
    default="NostalgiaForInfinityX4",
  )
  parser.add_argument(
    "--output",
    "-o",
    metavar="OUTPUT_PATH",
    help="Output of transformed raw NFI file",
    type=str,
    # default="NostalgiaForInfinityX4_Raw.py",
  )
  parser.add_argument(
    "--cname",
    "-c",
    nargs="?",
    metavar="OUTPUT_CLASSNAME",
    help="Optional new strategy class name in raw file, if set to no value, this class name is derived from the output file name",
    type=str,
    const=":D:E:F:A:U:L:T:",
  )

  args = parser.parse_args()
  # print('ARGS=', args)

  if args.output == None:
    args.output = args.strategy + "_Raw.py"

  if os.path.splitext(args.output)[1] == "":
    args.output += ".py"  # python file

  config = Configuration.from_files([])
  config["strategy"] = args.strategy
  strategy = StrategyResolver.load_strategy(config)

  source = ""
  with open(strategy.__file__, mode="r", encoding="utf-8") as f:
    source = f.read()

  validate_syntax(source)

  new_source = replace_all_references(strategy, source)
  print("Transforming all hyperopt values to raw...")
  transformed, t_count = transform_code(new_source)
  print(f"{t_count} hyperopt values transformed.")

  if args.cname != None:
    if args.cname == ":D:E:F:A:U:L:T:" or len(args.cname) == 0:
      # NostalgiaForInfinityX4_Raw.py ==> class NostalgiaForInfinityX4_Raw()(IStrategy):
      args.cname = os.path.splitext(args.output)[0]
    transformed = replace_classname(transformed, args.strategy, args.cname)

  with open(args.output, mode="w", encoding="utf-8") as f:
    f.write(transformed)
  print(f"Path of the transformed file: {args.output}")
