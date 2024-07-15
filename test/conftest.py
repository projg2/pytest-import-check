# (c) 2024 Michał Górny
# SPDX-License-Identifier: GPL-2.0-or-later

import functools

import pytest


pytest_plugins = ["pytester"]


@pytest.fixture(params=["importlib", "prepend"])
def import_mode(request):
    yield request.param


@pytest.fixture(params=["false", "true"])
def consider_namespace_packages(request):
    yield request.param


@pytest.fixture
def run(pytester, import_mode, consider_namespace_packages):
    pytester.syspathinsert()
    yield functools.partial(pytester.runpytest,
                            "-vv", "--tb=long", "--import-check",
                            f"--import-mode={import_mode}",
                            "--override-ini=consider_namespace_packages="
                            f"{consider_namespace_packages}")


