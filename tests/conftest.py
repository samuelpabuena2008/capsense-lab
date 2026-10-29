from pathlib import Path

import pytest

from capsense.domain.models import Calibracion

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cal() -> Calibracion:
    return Calibracion()


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
