"""Step 2: stratified train/test split.

The test set is held out of the 'train' index so evaluation never retrieves
the incident it is being asked about. Stratifying by category keeps the rare
classes (memory_leak, concurrency_race_condition) represented in both halves.

    python -m rag.split
"""
import json
import random
from collections import Counter, defaultdict

from .config import CLEAN_PATH, SPLIT_PATH, SPLIT_SEED, TEST_FRACTION


def stratified_split(entries, test_fraction=TEST_FRACTION, seed=SPLIT_SEED):
    by_category = defaultdict(list)
    for entry in entries:
        by_category[entry["category"]].append(entry["id"])
    rng = random.Random(seed)
    train, test = [], []
    for category in sorted(by_category):
        ids = sorted(by_category[category])
        rng.shuffle(ids)
        n_test = max(1, round(len(ids) * test_fraction)) if len(ids) > 1 else 0
        test += ids[:n_test]
        train += ids[n_test:]
    return sorted(train), sorted(test)


def main():
    entries = json.loads(CLEAN_PATH.read_text())
    train, test = stratified_split(entries)
    SPLIT_PATH.write_text(json.dumps(
        {"seed": SPLIT_SEED, "test_fraction": TEST_FRACTION, "train": train, "test": test},
        indent=1,
    ))
    category = {e["id"]: e["category"] for e in entries}
    train_counts = Counter(category[i] for i in train)
    test_counts = Counter(category[i] for i in test)
    print(f"train {len(train)}  test {len(test)}  -> {SPLIT_PATH}")
    for name, n in train_counts.most_common():
        print(f"  {name:28s} train {n:4d}  test {test_counts[name]:3d}")


if __name__ == "__main__":
    main()
