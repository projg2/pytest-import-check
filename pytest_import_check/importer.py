# (c) 2024 Michał Górny
# SPDX-License-Identifier: GPL-2.0-or-later
#
# copied from https://github.com/pytest-dev/pytest
# src/_pytest/pathlib.py
# (c) 2004-2024 Bruno Oliveira and others
# originally licensed MIT

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import itertools
import os
import sys

from enum import Enum
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType


class ImportMode(Enum):
    """Possible values for `mode` parameter of `import_path`."""

    prepend = "prepend"
    append = "append"
    importlib = "importlib"


class ImportPathMismatchError(ImportError):
    """Raised on import_path() if there is a mismatch of __file__'s.

    This can happen when `import_path` is called multiple times with different filenames that has
    the same basename but reside in packages
    (for example "/tests1/test_foo.py" and "/tests2/test_foo.py").
    """


def strip_suffix(path: Path) -> str:
    """Return module name without suffixes"""
    if path.suffix == ".so":
        path = path.with_suffix("")
    return path.with_suffix("")


def import_path(
    path: str | os.PathLike[str],
    *,
    mode: str | ImportMode = ImportMode.prepend,
    root: Path,
    consider_namespace_packages: bool,
) -> ModuleType:
    """
    Import and return a module from the given path, which can be a file (a module) or
    a directory (a package).

    :param path:
        Path to the file to import.

    :param mode:
        Controls the underlying import mechanism that will be used:

        * ImportMode.prepend: the directory containing the module (or package, taking
          `__init__.py` files into account) will be put at the *start* of `sys.path` before
          being imported with `importlib.import_module`.

        * ImportMode.append: same as `prepend`, but the directory will be appended
          to the end of `sys.path`, if not already in `sys.path`.

        * ImportMode.importlib: uses more fine control mechanisms provided by `importlib`
          to import the module, which avoids having to muck with `sys.path` at all. It effectively
          allows having same-named test modules in different places.

    :param root:
        Used as an anchor when mode == ImportMode.importlib to obtain
        a unique name for the module being imported so it can safely be stored
        into ``sys.modules``.

    :param consider_namespace_packages:
        If True, consider namespace packages when resolving module names.

    :raises ImportPathMismatchError:
        If after importing the given `path` and the module `__file__`
        are different. Only raised in `prepend` and `append` modes.
    """
    path = Path(path)
    mode = ImportMode(mode)

    if not path.exists():
        raise ImportError(path)

    if mode is ImportMode.importlib:
        # Try to import this module using the standard import mechanisms, but
        # without touching sys.path.
        try:
            pkg_root, module_name = resolve_pkg_root_and_module_name(
                path, consider_namespace_packages=consider_namespace_packages
            )
        except CouldNotResolvePathError:
            pass
        else:
            # If the given module name is already in sys.modules, do not import it again.
            with contextlib.suppress(KeyError):
                return sys.modules[module_name]

            mod = _import_module_using_spec(
                module_name, path, pkg_root, insert_modules=False
            )
            if mod is not None:
                return mod

        # Could not import the module with the current sys.path, so we fall back
        # to importing the file as a single module, not being a part of a package.
        module_name = module_name_from_path(path, root)
        with contextlib.suppress(KeyError):
            return sys.modules[module_name]

        mod = _import_module_using_spec(
            module_name, path, path.parent, insert_modules=True
        )
        if mod is None:
            raise ImportError(f"Can't find module {module_name} at location {path}")
        return mod

    try:
        pkg_root, module_name = resolve_pkg_root_and_module_name(
            path, consider_namespace_packages=consider_namespace_packages
        )
    except CouldNotResolvePathError:
        path_without_suffix = strip_suffix(path)
        pkg_root, module_name = (path_without_suffix.parent,
                                 path_without_suffix.name)

    # Change sys.path permanently: restoring it at the end of this function would cause surprising
    # problems because of delayed imports: for example, a conftest.py file imported by this function
    # might have local imports, which would fail at runtime if we restored sys.path.
    if mode is ImportMode.append:
        if str(pkg_root) not in sys.path:
            sys.path.append(str(pkg_root))
    elif mode is ImportMode.prepend:
        if str(pkg_root) != sys.path[0]:
            sys.path.insert(0, str(pkg_root))
    else:
        assert False, f"invalid import mode: {mode}"

    importlib.import_module(module_name)

    mod = sys.modules[module_name]
    if path.name == "__init__.py":
        return mod

    ignore = os.environ.get("PY_IGNORE_IMPORTMISMATCH", "")
    if ignore != "1":
        module_file = mod.__file__
        if module_file is None:
            raise ImportPathMismatchError(module_name, module_file, path)

        if module_file.endswith((".pyc", ".pyo")):
            module_file = module_file[:-1]
        if module_file.endswith(os.sep + "__init__.py"):
            module_file = module_file[: -(len(os.sep + "__init__.py"))]

        try:
            is_same = _is_same(str(path), module_file)
        except FileNotFoundError:
            is_same = False

        if not is_same:
            raise ImportPathMismatchError(module_name, module_file, path)

    return mod


def _import_module_using_spec(
    module_name: str, module_path: Path, module_location: Path, *, insert_modules: bool
) -> ModuleType | None:
    """
    Tries to import a module by its canonical name, path to the .py file, and its
    parent location.

    :param insert_modules:
        If True, will call insert_missing_modules to create empty intermediate modules
        for made-up module names (when importing test files not reachable from sys.path).
    """
    # Checking with sys.meta_path first in case one of its hooks can import this module,
    # such as our own assertion-rewrite hook.
    for meta_importer in sys.meta_path:
        spec = meta_importer.find_spec(module_name, [str(module_location)])
        if spec_matches_module_path(spec, module_path):
            break
    else:
        spec = importlib.util.spec_from_file_location(module_name, str(module_path))

    if spec_matches_module_path(spec, module_path):
        assert spec is not None
        # Attempt to import the parent module, seems is our responsibility:
        # https://github.com/python/cpython/blob/73906d5c908c1e0b73c5436faeff7d93698fc074/Lib/importlib/_bootstrap.py#L1308-L1311
        parent_module_name, _, name = module_name.rpartition(".")
        parent_module: ModuleType | None = None
        if parent_module_name:
            parent_module = sys.modules.get(parent_module_name)
            if parent_module is None:
                # Find the directory of this module's parent.
                parent_dir = (
                    module_path.parent.parent
                    if module_path.name == "__init__.py"
                    else module_path.parent
                )
                # Consider the parent module path as its __init__.py file, if it has one.
                parent_module_path = (
                    parent_dir / "__init__.py"
                    if (parent_dir / "__init__.py").is_file()
                    else parent_dir
                )
                parent_module = _import_module_using_spec(
                    parent_module_name,
                    parent_module_path,
                    parent_dir,
                    insert_modules=insert_modules,
                )

        # Find spec and import this module.
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        # Set this module as an attribute of the parent module (#12194).
        if parent_module is not None:
            setattr(parent_module, name, mod)

        if insert_modules:
            insert_missing_modules(sys.modules, module_name)
        return mod

    return None


def spec_matches_module_path(module_spec: ModuleSpec | None, module_path: Path) -> bool:
    """Return true if the given ModuleSpec can be used to import the given module path."""
    if module_spec is None or module_spec.origin is None:
        return False

    return Path(module_spec.origin) == module_path


# Implement a special _is_same function on Windows which returns True if the two filenames
# compare equal, to circumvent os.path.samefile returning False for mounts in UNC (#7678).
if sys.platform.startswith("win"):

    def _is_same(f1: str, f2: str) -> bool:
        return Path(f1) == Path(f2) or os.path.samefile(f1, f2)

else:

    def _is_same(f1: str, f2: str) -> bool:
        return os.path.samefile(f1, f2)


def module_name_from_path(path: Path, root: Path) -> str:
    """
    Return a dotted module name based on the given path, anchored on root.

    For example: path="projects/src/tests/test_foo.py" and root="/projects", the
    resulting module name will be "src.tests.test_foo".
    """
    path = strip_suffix(path)
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        # If we can't get a relative path to root, use the full path, except
        # for the first part ("d:\\" or "/" depending on the platform, for example).
        path_parts = path.parts[1:]
    else:
        # Use the parts for the relative path to the root path.
        path_parts = relative_path.parts

    # Module name for packages do not contain the __init__ file, unless
    # the `__init__.py` file is at the root.
    if len(path_parts) >= 2 and path_parts[-1] == "__init__":
        path_parts = path_parts[:-1]

    # Module names cannot contain ".", normalize them to "_". This prevents
    # a directory having a "." in the name (".env.310" for example) causing extra intermediate modules.
    # Also, important to replace "." at the start of paths, as those are considered relative imports.
    path_parts = tuple(x.replace(".", "_") for x in path_parts)

    return ".".join(path_parts)


def insert_missing_modules(modules: dict[str, ModuleType], module_name: str) -> None:
    """
    Used by ``import_path`` to create intermediate modules when using mode=importlib.

    When we want to import a module as "src.tests.test_foo" for example, we need
    to create empty modules "src" and "src.tests" after inserting "src.tests.test_foo",
    otherwise "src.tests.test_foo" is not importable by ``__import__``.
    """
    module_parts = module_name.split(".")
    while module_name:
        parent_module_name, _, child_name = module_name.rpartition(".")
        if parent_module_name:
            parent_module = modules.get(parent_module_name)
            if parent_module is None:
                try:
                    # If sys.meta_path is empty, calling import_module will issue
                    # a warning and raise ModuleNotFoundError. To avoid the
                    # warning, we check sys.meta_path explicitly and raise the error
                    # ourselves to fall back to creating a dummy module.
                    if not sys.meta_path:
                        raise ModuleNotFoundError
                    parent_module = importlib.import_module(parent_module_name)
                except ModuleNotFoundError:
                    parent_module = ModuleType(
                        module_name,
                        doc="Empty module created by pytest's importmode=importlib.",
                    )
                modules[parent_module_name] = parent_module

            # Add child attribute to the parent that can reference the child
            # modules.
            if not hasattr(parent_module, child_name):
                setattr(parent_module, child_name, modules[module_name])

        module_parts.pop(-1)
        module_name = ".".join(module_parts)


def resolve_package_path(path: Path) -> Path | None:
    """Return the Python package path by looking for the last
    directory upwards which still contains an __init__.py.

    Returns None if it cannot be determined.
    """
    result = None
    for parent in itertools.chain((path,), path.parents):
        if parent.is_dir():
            if not (parent / "__init__.py").is_file():
                break
            if not parent.name.isidentifier():
                break
            result = parent
    return result


def resolve_pkg_root_and_module_name(
    path: Path, *, consider_namespace_packages: bool = False
) -> tuple[Path, str]:
    """
    Return the path to the directory of the root package that contains the
    given Python file, and its module name:

        src/
            app/
                __init__.py
                core/
                    __init__.py
                    models.py

    Passing the full path to `models.py` will yield Path("src") and "app.core.models".

    If consider_namespace_packages is True, then we additionally check upwards in the hierarchy
    for namespace packages:

    https://packaging.python.org/en/latest/guides/packaging-namespace-packages

    Raises CouldNotResolvePathError if the given path does not belong to a package (missing any __init__.py files).
    """
    pkg_root: Path | None = None
    pkg_path = resolve_package_path(path)
    if pkg_path is not None:
        pkg_root = pkg_path.parent
    if consider_namespace_packages:
        start = pkg_root if pkg_root is not None else path.parent
        for candidate in (start, *start.parents):
            module_name = compute_module_name(candidate, path)
            if module_name and is_importable(module_name, path):
                # Point the pkg_root to the root of the namespace package.
                pkg_root = candidate
                break

    if pkg_root is not None:
        module_name = compute_module_name(pkg_root, path)
        if module_name:
            return pkg_root, module_name

    raise CouldNotResolvePathError(f"Could not resolve for {path}")


def is_importable(module_name: str, module_path: Path) -> bool:
    """
    Return if the given module path could be imported normally by Python, akin to the user
    entering the REPL and importing the corresponding module name directly, and corresponds
    to the module_path specified.

    :param module_name:
        Full module name that we want to check if is importable.
        For example, "app.models".

    :param module_path:
        Full path to the python module/package we want to check if is importable.
        For example, "/projects/src/app/models.py".
    """
    try:
        # Note this is different from what we do in ``_import_module_using_spec``, where we explicitly search through
        # sys.meta_path to be able to pass the path of the module that we want to import (``meta_importer.find_spec``).
        # Using importlib.util.find_spec() is different, it gives the same results as trying to import
        # the module normally in the REPL.
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError, ImportWarning):
        return False
    else:
        return spec_matches_module_path(spec, module_path)


def compute_module_name(root: Path, module_path: Path) -> str | None:
    """Compute a module name based on a path and a root anchor."""
    try:
        path_without_suffix = strip_suffix(module_path)
    except ValueError:
        # Empty paths (such as Path.cwd()) might break meta_path hooks (like our own assertion rewriter).
        return None

    try:
        relative = path_without_suffix.relative_to(root)
    except ValueError:  # pragma: no cover
        return None
    names = list(relative.parts)
    if not names:
        return None
    if names[-1] == "__init__":
        names.pop()
    return ".".join(names)


class CouldNotResolvePathError(Exception):
    """Custom exception raised by resolve_pkg_root_and_module_name."""

