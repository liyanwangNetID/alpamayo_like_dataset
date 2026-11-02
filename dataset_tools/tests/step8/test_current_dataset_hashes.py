from step8.contract import EXPECTED_SHA256


def test_step8_expected_hashes_match_current_dataset():
    assert EXPECTED_SHA256 == {
        "keyframes": "ab23cfe96037f35eef6bd3d687e01c2b8ca724403dd2306ae26f4d2480d7b841",
        "meta_actions": "4c95d382ae94534953ae250cdd4331c3fe538583222f5a89b4623a51c9aaa42b",
        "navigation": "6a8754e20d0e261b716326d49987570e35255661e44388d10b8e31780ee9229f",
        "scene_facts": "3d844c16f302b3529b196de5524ffbd86717718a63e7513df92d04126c4c3ad3",
    }
