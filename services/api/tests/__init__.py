# Marks `tests` as a package so sibling imports like
# `from tests.test_importer import ...` resolve identically under pytest's
# prepend mode locally AND in CI (where the modern editable-install finder
# only exposes the `app` package, not the repository root).
