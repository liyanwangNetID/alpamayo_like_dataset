from step8.contract import EXPECTED_SHA256


def test_step8_expected_hashes_match_current_dataset():
    assert EXPECTED_SHA256 == {
        "keyframes": "ab23cfe96037f35eef6bd3d687e01c2b8ca724403dd2306ae26f4d2480d7b841",
        "meta_actions": "4c95d382ae94534953ae250cdd4331c3fe538583222f5a89b4623a51c9aaa42b",
        "navigation": "6a8754e20d0e261b716326d49987570e35255661e44388d10b8e31780ee9229f",
        "scene_facts": "d9f1c772d1538b33153a06af492f3afe873255d57bf8a9606698e98cad3586bc",
    }
