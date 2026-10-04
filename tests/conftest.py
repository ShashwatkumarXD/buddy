import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # tests never open real windows


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
