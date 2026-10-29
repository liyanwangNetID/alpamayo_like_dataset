import pytest

from step9.contract import Step9ContractError
from step9.format_check import check_response_format


def test_accepts_summary_only_response():
    value = {"reasoning_summary": "The vehicle is keeping its current direction."}
    assert check_response_format(value) == value


def test_rejects_extra_fields():
    with pytest.raises(Step9ContractError):
        check_response_format({"reasoning_summary": "Valid.", "limitations": []})


def test_rejects_more_than_five_sentences():
    with pytest.raises(Step9ContractError):
        check_response_format({"reasoning_summary": "One. Two. Three. Four. Five. Six."})
