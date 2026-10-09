"""检查 Python 函数的非空、非注释行数，不计算文档字符串。"""

import argparse
import ast
import io
import tokenize
from pathlib import Path


TRIVIA = {
    tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
    tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING,
}


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", [])
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        if isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def _code_lines(source: str, tree: ast.AST) -> set[int]:
    lines = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type not in TRIVIA:
            lines.update(range(token.start[0], token.end[0] + 1))
    nonempty = {number for number, line in enumerate(source.splitlines(), 1) if line.strip()}
    return (lines & nonempty) - _docstring_lines(tree)


def measure_functions(source: str) -> list[dict]:
    """统计源码各函数的有效行数。

    Args:
        source: 合法 Python 源码字符串。
    Returns:
        按源码顺序排列的函数名、起始行和有效行数。
    Raises:
        SyntaxError: 源码无法解析。无文件写入副作用。
    """
    tree = ast.parse(source)
    code = _code_lines(source, tree)
    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return [
        {"name": node.name, "line": node.lineno,
         "length": len(code & set(range(node.lineno, node.end_lineno + 1)))}
        for node in sorted(functions, key=lambda item: item.lineno)
    ]


def _python_files(paths: list[str]):
    for value in paths:
        path = Path(value)
        if path.is_dir():
            yield from sorted(path.rglob("*.py"))
        elif path.suffix == ".py":
            yield path


def main() -> int:
    """读取命令行中的文件或目录；超限返回 1，通过返回 0，不修改文件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    count = 0
    failed = 0
    for path in _python_files(args.paths):
        for function in measure_functions(path.read_text(encoding="utf-8")):
            count += 1
            if function["length"] > args.limit:
                failed += 1
                print(f"{path}:{function['line']} {function['name']}: {function['length']} > {args.limit}")
    print(f"Checked {count} functions; {failed} over limit.")
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
