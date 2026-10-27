from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

SPLIT_RATIOS = {"train": 0.8, "validation": 0.1, "test": 0.1}
SPLIT_NAMES = tuple(SPLIT_RATIOS)
SPLIT_SEED = 11


def stable_rank(value: str, seed: int = SPLIT_SEED) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def sample_features(row: Mapping[str, Any]) -> tuple[str, ...]:
    selection_sources = tuple(sorted(str(value) for value in row["selection"]["selection_sources"]))
    values = [
        f"lateral={row['supervision']['driving_decision']['joint_action']['lateral']}",
        f"longitudinal={row['supervision']['driving_decision']['joint_action']['longitudinal']}",
        f"meta_quality={row['quality']['meta_action']}",
        f"navigation={row['model_input']['navigation']['navigation']['action']}",
        f"road={row['supervision']['scene_facts']['road_context']['type']}",
        f"coc_quality={row['quality']['structured_causality']}",
    ]
    values.extend(f"selection={source}" for source in selection_sources)
    return tuple(values)


@dataclass(frozen=True)
class ClipGroup:
    clip_id: str
    anchor_ids: tuple[str, ...]
    feature_counts: Counter[str]

    @property
    def sample_count(self) -> int:
        return len(self.anchor_ids)


def build_clip_groups(rows: Iterable[Mapping[str, Any]]) -> tuple[ClipGroup, ...]:
    anchors: dict[str, list[str]] = defaultdict(list)
    features: dict[str, Counter[str]] = defaultdict(Counter)
    seen = set()
    for row in rows:
        anchor_id = str(row["anchor_id"])
        clip_id = str(row["clip_id"])
        if anchor_id in seen:
            raise ValueError(f"duplicate anchor_id: {anchor_id}")
        seen.add(anchor_id)
        anchors[clip_id].append(anchor_id)
        features[clip_id].update(sample_features(row))
    return tuple(
        ClipGroup(
            clip_id=clip_id,
            anchor_ids=tuple(sorted(anchors[clip_id])),
            feature_counts=features[clip_id],
        )
        for clip_id in sorted(anchors)
    )


def _global_counts(groups: Iterable[ClipGroup]) -> tuple[int, Counter[str]]:
    samples = 0
    features: Counter[str] = Counter()
    for group in groups:
        samples += group.sample_count
        features.update(group.feature_counts)
    return samples, features


def _score(assignments: Mapping[str, str], groups_by_id: Mapping[str, ClipGroup]) -> float:
    total_samples, global_features = _global_counts(groups_by_id.values())
    split_samples = Counter()
    split_features = {name: Counter() for name in SPLIT_NAMES}
    split_clips = Counter()
    for clip_id, split in assignments.items():
        group = groups_by_id[clip_id]
        split_samples[split] += group.sample_count
        split_features[split].update(group.feature_counts)
        split_clips[split] += 1

    score = 0.0
    for split, ratio in SPLIT_RATIOS.items():
        target_samples = total_samples * ratio
        score += 25.0 * ((split_samples[split] - target_samples) / max(1.0, target_samples)) ** 2
        if split_clips[split] == 0:
            score += 1000.0
        for feature, total in global_features.items():
            target = total * ratio
            weight = 1.0 + 4.0 / max(1.0, total ** 0.5)
            score += weight * ((split_features[split][feature] - target) / max(1.0, target)) ** 2
    return score


def deterministic_grouped_split(rows: list[Mapping[str, Any]], seed: int = SPLIT_SEED) -> dict[str, str]:
    groups = build_clip_groups(rows)
    groups_by_id = {group.clip_id: group for group in groups}
    total_samples, global_features = _global_counts(groups)

    def rarity(group: ClipGroup) -> float:
        return sum(count / max(1, global_features[feature]) for feature, count in group.feature_counts.items())

    ordered = sorted(
        groups,
        key=lambda group: (-rarity(group), -group.sample_count, stable_rank(group.clip_id, seed), group.clip_id),
    )
    assignments: dict[str, str] = {}
    split_samples = Counter()
    split_features = {name: Counter() for name in SPLIT_NAMES}
    split_clips = Counter()

    for group in ordered:
        candidates = []
        for split, ratio in SPLIT_RATIOS.items():
            sample_target = total_samples * ratio
            sample_after = split_samples[split] + group.sample_count
            sample_term = 25.0 * ((sample_after - sample_target) / max(1.0, sample_target)) ** 2
            feature_term = 0.0
            for feature, count in group.feature_counts.items():
                target = global_features[feature] * ratio
                after = split_features[split][feature] + count
                weight = 1.0 + 4.0 / max(1.0, global_features[feature] ** 0.5)
                feature_term += weight * ((after - target) / max(1.0, target)) ** 2
            fill = sample_after / max(1.0, sample_target)
            candidates.append((sample_term + feature_term, fill, split_clips[split], stable_rank(f"{group.clip_id}:{split}", seed), split))
        selected = min(candidates)[-1]
        assignments[group.clip_id] = selected
        split_samples[selected] += group.sample_count
        split_features[selected].update(group.feature_counts)
        split_clips[selected] += 1

    # Deterministic local improvement by single-clip moves. Clip integrity is never broken.
    current = _score(assignments, groups_by_id)
    for _ in range(12):
        improved = False
        for clip_id in sorted(assignments, key=lambda value: (stable_rank(value, seed), value)):
            source = assignments[clip_id]
            if sum(value == source for value in assignments.values()) <= 1:
                continue
            best = (current, source)
            for target in SPLIT_NAMES:
                if target == source:
                    continue
                assignments[clip_id] = target
                candidate = _score(assignments, groups_by_id)
                if candidate + 1e-12 < best[0]:
                    best = (candidate, target)
            assignments[clip_id] = best[1]
            if best[1] != source:
                current = best[0]
                improved = True
        if not improved:
            break

    if set(assignments) != set(groups_by_id):
        raise RuntimeError("split assignment does not close to Clip groups")
    return assignments
