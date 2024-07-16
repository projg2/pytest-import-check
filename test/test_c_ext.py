# (c) 2024 Michał Górny
# SPDX-License-Identifier: GPL-2.0-or-later

import subprocess
import sys

import pytest


@pytest.fixture(params=[False, True])
def py_limited_api(request):
    yield request.param


@pytest.fixture
def build_c_ext(pytester, py_limited_api):
    def inner():
        pytester.makefile(".c", test="""
            #define PY_SSIZE_T_CLEAN
            #include <Python.h>

            static struct PyModuleDef testmodule = {
                PyModuleDef_HEAD_INIT,
                .m_name = "test",
                .m_doc = NULL,
                .m_size = -1,
                .m_methods = NULL,
            };

            PyMODINIT_FUNC
            PyInit_test(void)
            {
                return PyModule_Create(&testmodule);
            }
        """)
        pytester.makepyfile(setup=f"""
            from setuptools import setup, Extension

            setup(name="test",
                  version="0",
                  ext_modules=[
                      Extension(name="test",
                                sources=["test.c"],
                                py_limited_api={py_limited_api}),
                  ])
        """)
        subprocess.run([sys.executable, "setup.py", "build_ext", "-i"],
                       check=True)
    yield inner


def test_c_ext(run, build_c_ext):
    build_c_ext()
    result = run("--ignore=setup.py")
    result.assert_outcomes(passed=1)
