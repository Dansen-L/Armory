"""Minimal smoke tests — verify package imports without crashing."""


def test_package_importable():
    """armory package is importable after pip install."""
    import armory
    assert armory.__version__ == "0.1.0"


def test_db_module_importable():
    """armory.db module is importable."""
    from armory import db
    assert callable(db.init_db)
    assert callable(db.get_connection)


def test_ai_module_importable():
    """armory.ai module is importable and returns False without key."""
    from armory import ai
    import os
    # Ensure key is not set for this test
    key = os.environ.pop("ARMORY_CLAUDE_API_KEY", None)
    assert ai.is_ai_available() is False
    if key:
        os.environ["ARMORY_CLAUDE_API_KEY"] = key


def test_loader_module_importable():
    """armory.loader module is importable."""
    from armory import loader
    assert callable(loader.load_all_classes)


def test_export_module_importable():
    """armory.export module is importable with correct constants."""
    from armory import export
    assert "json" in export.SUPPORTED_FORMATS
    assert "burp" in export.SUPPORTED_FORMATS
    assert "markdown" in export.SUPPORTED_FORMATS


def test_search_module_importable():
    """armory.search module is importable."""
    from armory import search
    assert callable(search.search_payloads)
