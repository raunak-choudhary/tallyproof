import importlib


def test_core_package_imports_without_side_effects():
    module = importlib.import_module("tallyproof_core")
    assert module.__all__ == []
