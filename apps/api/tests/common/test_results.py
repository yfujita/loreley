import dataclasses

import pytest

from loreley_api.common.results import Failed, Ok


def test_ok_and_failed_are_distinguished_by_type() -> None:
    results = [Ok(1), Failed("timeout", "store", "ConnectionTimeout")]

    assert [isinstance(result, Ok) for result in results] == [True, False]
    assert results[0].value == 1


def test_a_result_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Ok(1).value = 2  # type: ignore[misc]
