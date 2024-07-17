# (c) 2024 Michał Górny
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib
from pathlib import Path

import pytest

import pytest_import_check.importer
from pytest_import_check.importer import (import_path,
                                          SUFFIXES,
                                          )


def pytest_addoption(parser):
    group = parser.getgroup("import-check", "import checks")
    group.addoption("--import-check",
                    action="store_true",
                    help="Check whether all Python modules that can be found "
                         "are importable")


def pytest_configure(config):
    config.addinivalue_line("markers", "importcheck: Import checking tests")


def pytest_collect_file(file_path, parent):
    if not parent.config.option.import_check:
        return None
    if not file_path.name.endswith(SUFFIXES):
        return None
    return ImportCheckFile.from_parent(parent=parent, path=file_path)


class ImportCheckFile(pytest.File):
    def collect(self):
        return [ImportCheckItem.from_parent(self, name="import-check")]


class ImportCheckItem(pytest.Item):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_marker("importcheck")

    def runtest(self):
        import_path(self.fspath,
                    mode=self.config.getoption("--import-mode"),
                    root=self.config.rootpath,
                    consider_namespace_packages=
                        self.config.getini("consider_namespace_packages"))

    def repr_failure(self, exc_info):
        importer_path = Path(pytest_import_check.importer.__file__)
        done = []
        def filter_cb(entry):
            if done:
                return True
            if isinstance(entry.path, Path):
                if entry.path == importer_path:
                    return False
                if entry.path.is_relative_to(importlib.__file__):
                    return False
            if isinstance(entry.path, str) and "importlib" in entry.path:
                return False
            done.append(True)
            return True

        exc_info.traceback = exc_info.traceback.cut(
            importer_path).filter(filter_cb)

        return super().repr_failure(exc_info)

    def reportinfo(self):
        return (
            self.fspath,
            None,
            self.config.invocation_dir.bestrelpath(self.fspath),
        )

