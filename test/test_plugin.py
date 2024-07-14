# (c) 2024 Michał Górny
# SPDX-License-Identifier: GPL-2.0-or-later

pytest_plugins = ["pytester"]


def run(pytester, *args, **kwargs):
    pytester.syspathinsert()
    return pytester.runpytest(
        "-vv", "--tb=long", "--import-check", "--import-mode=importlib",
        *args, **kwargs)


def test_no_imports(pytester):
    pytester.makepyfile(good="print('Hello world')")
    result = run(pytester)
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["good.py::import-check*PASSED*"])


def test_stdlib_import(pytester):
    pytester.makepyfile(
        good="""
        import sys

        if __name__ == "__main__":
            sys.exit(0)
        """)
    result = run(pytester)
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["good.py::import-check*PASSED*"])


def test_pytest_import(pytester):
    pytester.makepyfile(good="import pytest")
    result = run(pytester)
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["good.py::import-check*PASSED*"])


def test_samedir_import(pytester):
    pytester.makepyfile(good="import other", other="")
    result = run(pytester)
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines([
        "good.py::import-check*PASSED*",
        "other.py::import-check*PASSED*",
    ])


def test_samedir_cyclic_import(pytester):
    pytester.makepyfile(good="import other", other="import good")
    result = run(pytester)
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines([
        "good.py::import-check*PASSED*",
        "other.py::import-check*PASSED*",
    ])


def test_package_absolute_imports(pytester):
    foo = pytester.mkpydir("foo")
    (foo / "foo.py").write_text("import foo.bar")
    (foo / "bar.py").write_text("import foo")
    result = run(pytester)
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines([
        "foo/__init__.py::import-check*PASSED*",
        "foo/bar.py::import-check*PASSED*",
        "foo/foo.py::import-check*PASSED*",
    ])


def test_package_relative_imports(pytester):
    foo = pytester.mkpydir("foo")
    (foo / "foo.py").write_text("from . import bar")
    (foo / "bar.py").write_text("from . import *")
    result = run(pytester)
    result.assert_outcomes(passed=3)
    result.stdout.fnmatch_lines([
        "foo/__init__.py::import-check*PASSED*",
        "foo/bar.py::import-check*PASSED*",
        "foo/foo.py::import-check*PASSED*",
    ])


def test_namespace_package_absolute_imports(pytester):
    foo = pytester.mkdir("foo")
    (foo / "foo.py").write_text("import foo.bar")
    (foo / "bar.py").write_text("import foo")
    result = run(pytester)
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines([
        "foo/bar.py::import-check*PASSED*",
        "foo/foo.py::import-check*PASSED*",
    ])


def test_namespace_package_relative_imports(pytester):
    foo = pytester.mkdir("foo")
    (foo / "foo.py").write_text("from . import bar")
    (foo / "bar.py").write_text("from . import *")
    result = run(pytester)
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines([
        "foo/bar.py::import-check*PASSED*",
        "foo/foo.py::import-check*PASSED*",
    ])


def test_bad_import(pytester):
    pytester.makepyfile(bad="import this_package_really_shouldnt_exist")
    result = run(pytester)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([
        "bad.py::import-check*FAILED*",
        ">*import this_package_really_shouldnt_exist",
        "E*ModuleNotFoundError:*",
        "bad.py:1: ModuleNotFoundError",
    ])
    # check whether we got nicely stripped traceback
    result.stdout.no_fnmatch_line("*/_pytest/*")
    result.stdout.no_fnmatch_line("*importlib*")


def test_other_exception(pytester):
    pytester.makepyfile(bad="1 / 0")
    result = run(pytester)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([
        "bad.py::import-check*FAILED*",
        ">*1 / 0",
        "E*ZeroDivisionError:*",
        "bad.py:1: ZeroDivisionError",
    ])
    # check whether we got nicely stripped traceback
    result.stdout.no_fnmatch_line("*/_pytest/*")
    result.stdout.no_fnmatch_line("*importlib*")


def test_syntax_error(pytester):
    pytester.makepyfile(bad="/ / /")
    result = run(pytester)
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([
        "bad.py::import-check*FAILED*",
        "*File*/bad.py*line 1",
        "*/ / /",
        "SyntaxError:*",
    ])
    # check whether we got nicely stripped traceback
    result.stdout.no_fnmatch_line("*/_pytest/*")
    #result.stdout.no_fnmatch_line("*importlib*")


def test_warning(pytester):
    pytester.makepyfile(
        warn="""
        import warnings

        warnings.warn("test warning")
        """)
    result = run(pytester, "-Wdefault")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines([
        "warn.py::import-check*PASSED*",
        "*warn.py:3: UserWarning: test warning*",
    ])


def test_werror(pytester):
    pytester.makepyfile(
        warn="""
        import warnings

        warnings.warn("test warning")
        """)
    result = run(pytester, "-Werror")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([
        "warn.py::import-check*FAILED*",
        ">*warnings.warn(\"test warning\")",
        "E*UserWarning: test warning",
        "warn.py:3: UserWarning",
    ])
