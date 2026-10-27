from step10.contract import canonical_sha256, index_by_anchor, without_identity


def test_canonical_sha256_is_order_independent():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_index_and_identity_removal():
    row = {"anchor_id": "a", "clip_id": "c", "anchor_ns": 1, "value": 2}
    assert index_by_anchor([row], "x")["a"] == row
    assert without_identity(row) == {"value": 2}
