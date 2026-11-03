from __future__ import annotations

import inspect

import step8.contract as contract


def test_step8_does_not_freeze_dataset_instance_hashes_in_source():
    source = inspect.getsource(contract)
    assert "EXPECTED_SHA256" not in source
    assert hasattr(contract, "collect_source_hashes")


def test_collect_source_hashes_uses_current_artifacts(tmp_path):
    paths = contract.Step8Paths.from_data_root(tmp_path)
    expected = {}
    for index, (name, path) in enumerate(paths.inputs().items(), start=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"name":"{name}","index":{index}}}\n', encoding="utf-8")
        expected[name] = contract.sha256_file(path)

    assert contract.collect_source_hashes(paths) == expected
