"""新代码的函数长度约束验证。"""

import subprocess
import sys
from pathlib import Path

from tools.check_function_lengths import measure_functions


def test_ignores_comments_empty_lines_and_docstrings():
    source = '''def example():
    """用途。
    第二行说明。
    """

    # 不计算注释
    value = 1
    return value
'''
    assert measure_functions(source) == [
        {"name": "example", "line": 1, "length": 3},
    ]


def test_counts_multiline_calls_as_physical_code_lines():
    source = """def example():
    value = calculate(
        1,
        2,
    )
    return value
"""
    assert measure_functions(source)[0]["length"] == 6


def test_measures_nested_and_async_functions():
    source = """async def outer():
    def inner():
        return 1
    return inner()
"""
    assert measure_functions(source) == [
        {"name": "outer", "line": 1, "length": 4},
        {"name": "inner", "line": 2, "length": 2},
    ]


def run_checker(path: Path):
    script = Path(__file__).parents[1] / "tools" / "check_function_lengths.py"
    return subprocess.run(
        [sys.executable, str(script), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_rejects_a_function_over_fifty_lines(tmp_path):
    source = "def too_long():\n" + "".join(f"    value_{index} = 1\n" for index in range(50))
    path = tmp_path / "example.py"
    path.write_text(source, encoding="utf-8")

    result = run_checker(path)

    assert result.returncode == 1
    assert "too_long: 51 > 50" in result.stdout


def test_cli_does_not_report_missing_files_as_passing(tmp_path):
    result = run_checker(tmp_path / "missing.py")

    assert result.returncode != 0
    assert "Checked 0 functions; 0 over limit." not in result.stdout
