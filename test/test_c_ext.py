# (c) 2024 Michał Górny
# SPDX-License-Identifier: GPL-2.0-or-later

import subprocess
import sys


def build_c_ext(pytester):
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
    pytester.makepyfile(setup="""
        from setuptools import setup, Extension

        setup(name="test",
              version="0",
              ext_modules=[
                  Extension(name="test",
                            sources=["test.c"]),
              ])
    """)
    subprocess.run([sys.executable, "setup.py", "build_ext", "-i"],
                   check=True)


def test_c_ext(run, pytester):
    build_c_ext(pytester)
    result = run("--ignore=setup.py")
    result.assert_outcomes(passed=1)
