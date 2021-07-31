import re
import ast

pattern = re.compile(
    r"(CategoricalParameter|DecimalParameter|IntParameter|RealParameter).*(default=)(?P<value>.+?)[,|\)].*"
)


def validate_syntax(src: str):
    ast.parse(src)  # Throw if syntax is not valid


def transform_code(src: str):
    def repl(matchobj):
        groupdict = matchobj.groupdict()
        return groupdict["value"]

    return pattern.sub(repl, src)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', metavar="INPUT_PATH",  help="Strategy path",
                        type=str, default="NostalgiaForInfinityNext.py")
    parser.add_argument('--output', '-o', metavar="OUTPUT_PATH", help="Output of transformed file",
                        type=str, default="NostalgiaForInfinityNext_Raw.py")

    args = parser.parse_args()
    filename = args.input
    source = ""
    with open(filename) as f:
        source = f.read()
    validate_syntax(source)
    transformed = transform_code(source)
    with open(args.output, 'w') as f:
        f.write(transformed)
