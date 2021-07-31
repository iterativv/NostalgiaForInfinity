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
    filename = "NostalgiaForInfinityNext.py"
    source = ""
    with open(filename) as f:
        source = f.read()
    validate_syntax(source)
    transformed = transform(source)
    with open(f"{filename.replace('.py', '')}_Raw.py", 'w') as f:
        f.write(transformed)
