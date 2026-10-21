"""TabPFN learns your filing system from files you already filed, then says where a new file belongs.

TabPFN is a tabular foundation model: it fits a small table in one forward pass, with no training run.
v2 weights: no account or login needed, runs on a laptop CPU or Apple GPU.
"""
import os
import random
from collections import Counter
from pathlib import Path

import numpy as np

from . import scan
from .features import CATEGORICAL, Featurizer

os.environ.setdefault("TABPFN_DISABLE_TELEMETRY", "1")
MAX_CLASSES = 10      # TabPFN's classifier handles up to 10 classes in one model
PER_FOLDER = 100      # keeps the table small and the folders balanced


def training_set(folders, per_folder=PER_FOLDER, max_classes=MAX_CLASSES, min_files=5, seed=0):
    """(paths, labels): a balanced sample of files from your biggest filing folders."""
    rng = random.Random(seed)
    files = {f: scan.walk_files(f, limit=3000) for f in folders}
    biggest = [f for f, fs in sorted(files.items(), key=lambda kv: -len(kv[1])) if len(fs) >= min_files][:max_classes]
    paths, labels = [], []
    for folder in biggest:
        sample = rng.sample(files[folder], min(per_folder, len(files[folder])))
        paths += sample
        labels += [str(folder)] * len(sample)
    return paths, labels


class FolderModel:
    def fit(self, paths, labels, meta):
        from tabpfn import TabPFNClassifier
        from tabpfn.constants import ModelVersion

        self.featurizer = Featurizer().fit(paths, meta)
        self.classes = sorted(set(labels))
        y = np.array([self.classes.index(l) for l in labels])
        self.clf = TabPFNClassifier.create_default_for_version(ModelVersion.V2, categorical_features_indices=CATEGORICAL)
        self.clf.fit(self.featurizer.transform(paths, meta), y)
        return self

    def predict(self, paths, meta):
        """[(folder, probability)] for each path."""
        if not paths:
            return []
        proba = self.clf.predict_proba(self.featurizer.transform(paths, meta))
        best = proba.argmax(axis=1)
        return [(self.classes[self.clf.classes_[b]], float(proba[i, b])) for i, b in enumerate(best)]


def evaluate(folders, test_share=0.3, thresholds=(0.5, 0.7, 0.9), seed=0):
    """Hide some already-filed files, ask TabPFN where they go, compare with where you put them."""
    paths, labels = training_set(folders, seed=seed)
    meta = scan.metadata(paths)
    rng = np.random.default_rng(seed)
    test = rng.random(len(paths)) < test_share
    train_p = [p for p, t in zip(paths, test) if not t]
    model = FolderModel().fit(train_p, [l for l, t in zip(labels, test) if not t], meta)
    test_p, test_y = [p for p, t in zip(paths, test) if t], [l for l, t in zip(labels, test) if t]
    pred = model.predict(test_p, meta)
    right = np.array([f == y for (f, _), y in zip(pred, test_y)])
    conf = np.array([c for _, c in pred])

    # Baseline a person would write: "files with this extension usually live in folder X".
    by_ext = {}
    for p, l in zip(train_p, [l for l, t in zip(labels, test) if not t]):
        by_ext.setdefault(Path(p).suffix.lower(), Counter())[l] += 1
    majority = Counter(labels).most_common(1)[0][0]
    rule = np.array([(by_ext[Path(p).suffix.lower()].most_common(1)[0][0] if Path(p).suffix.lower() in by_ext else majority) == y
                     for p, y in zip(test_p, test_y)])
    return {
        "folders": len(model.classes), "train_files": len(train_p), "test_files": len(test_p),
        "accuracy": float(right.mean()), "extension_rule_accuracy": float(rule.mean()),
        "at_threshold": {str(t): {"coverage": float((conf >= t).mean()),
                                  "accuracy": float(right[conf >= t].mean()) if (conf >= t).any() else None} for t in thresholds},
    }
