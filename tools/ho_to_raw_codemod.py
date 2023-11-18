import ast
import re

from freqtrade.configuration import Configuration
from freqtrade.resolvers import StrategyResolver
from freqtrade.strategy.interface import IStrategy

pattern = re.compile(
  r"(CategoricalParameter|DecimalParameter|IntParameter|RealParameter).*((default=)(?P<value>.+?),.*\)|(default=)(?P<edge_value>.+?)\))"
)


def validate_syntax(src: str):
  ast.parse(src)  # Throw if syntax is not valid


def transform_code(src: str):
  def repl(matchobj):
    groupdict = matchobj.groupdict()
    return groupdict["value"] or groupdict["edge_value"]

  return pattern.sub(repl, src)


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


def replace_all_references(strategy: IStrategy, source: str):
  params = strategy.detect_all_parameters()
  buy_params = [param[0] for param in params["buy"]]
  sell_params = [param[0] for param in params["sell"]]
  print("Replacing references of 'buy' hyperopting params...")
  new_source = replace_references(source, buy_params)
  print("Replacing references of 'sell' hyperopting params...")
  new_source = replace_references(new_source, sell_params)

  print("Replacing 'references' of 'buy_protection_params' hyperopting params...")
  new_source = re.sub(r"(global_buy_protection_params\[([\"\'])[\w\_]+\2\]).value", r"\1", new_source)

  return new_source


if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--strategy",
    "-s",
    metavar="STRATEGY",
    help="Name of the strategy",
    type=str,
    default="NostalgiaForInfinityNext",
  )
  parser.add_argument(
    "--output",
    "-o",
    metavar="OUTPUT_PATH",
    help="Output of transformed file",
    type=str,
    default="NostalgiaForInfinityNext_Raw.py",
  )
  args = parser.parse_args()
  config = Configuration.from_files([])
  config["strategy"] = args.strategy
  strategy = StrategyResolver.load_strategy(config)
  source = ""
  with open(strategy.__file__) as f:
    source = f.read()
  validate_syntax(source)
  new_source = replace_all_references(strategy, source)
  print("Transforming all hyperopt values to raw...")
  transformed = transform_code(new_source)
  with open(args.output, "w") as f:
    f.write(transformed)
  print(f"Path of the transformed file: {args.output}")
