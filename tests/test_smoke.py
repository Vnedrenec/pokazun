from datetime import UTC

import pokazun
from pokazun.clock import utcnow


def test_package_has_version():
    assert pokazun.__version__ == "0.1.0"


def test_utcnow_is_aware_utc():
    now = utcnow()
    assert now.tzinfo is UTC
