===================
pytest-import-check
===================

Description
===========
pytest-import-check is a pytest plugin that enables checking whether
Python modules installed by your package are importable.  This is mostly
useful to quickly check packages that do not have tests at all or do not
have all their modules covered by tests.

To enable it, pass ``--import-check`` option to pytest, e.g.:

    pytest --import-check foo


Thanks
======
While writing this plugin, I've looked at the following linter plugins
for inspiration on how to use the API:

- pytest-flakes_ by Florian Schulze, Holger Krekel and Ronny Pfannschmidt
- pytest-mypy_ by Daniel Bader


.. _pytest-flakes: https://pypi.org/project/pytest-flakes/
.. _pytest-mypy: https://pypi.org/project/pytest-mypy/
