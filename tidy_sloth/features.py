"""Turn files into a small table TabPFN can learn from. Cheap signals only: no file contents are read here."""
import math
import re
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

FAMILIES = {
    "image": ".jpg .jpeg .png .heic .gif .webp .tiff .bmp .svg .raw .dng",
    "video": ".mp4 .mov .m4v .avi .mkv .webm",
    "audio": ".mp3 .m4a .wav .aac .flac .ogg",
    "pdf": ".pdf",
    "doc": ".doc .docx .odt .rtf .pages .tex .md",
    "sheet": ".xls .xlsx .csv .numbers .ods",
    "slides": ".ppt .pptx .key .odp",
    "ebook": ".epub .mobi .azw3",
    "archive": ".zip .rar .7z .tar .gz .tgz .dmg .pkg",
    "text": ".txt .json .xml .html .log",
}
FAMILY_OF = {ext: i for i, exts in enumerate(FAMILIES.values()) for ext in exts.split()}
NAME_DIMS = 8
CATEGORICAL = [0, 1, 6]  # extension, family, download-source domain
COLUMNS = ["extension", "family", "log_size", "created_days", "lat", "lon", "source"] + [f"name_{i}" for i in range(NAME_DIMS)]


def name_text(path):
    """'IMG_20240512_1403.HEIC' -> 'img # #': words and shapes of the name, not its exact digits."""
    stem = Path(path).stem.lower()
    return " ".join(re.sub(r"\d+", "#", re.sub(r"[_\-.()\[\]]+", " ", stem)).split())


class Featurizer:
    def fit(self, paths, meta):
        exts = [Path(p).suffix.lower() for p in paths]
        self.ext_codes = {e: i for i, e in enumerate(sorted(set(exts)))}
        self.source_codes = {s: i for i, s in enumerate(sorted({meta[p]["source"] for p in paths}))}
        texts = [name_text(p) or "_" for p in paths]
        self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), max_features=4000).fit(texts)
        n = min(NAME_DIMS, max(1, len(self.tfidf.vocabulary_) - 1))
        self.svd = TruncatedSVD(n_components=n, random_state=0).fit(self.tfidf.transform(texts))
        return self

    def transform(self, paths, meta):
        names = self.svd.transform(self.tfidf.transform([name_text(p) or "_" for p in paths]))
        names = np.pad(names, ((0, 0), (0, NAME_DIMS - names.shape[1])))
        rows = []
        for p, name_vec in zip(paths, names):
            m, ext = meta[p], Path(p).suffix.lower()
            rows.append([self.ext_codes.get(ext, -1), FAMILY_OF.get(ext, len(FAMILIES)), math.log1p(m["size"]),
                         m["created_days"], m["lat"], m["lon"], self.source_codes.get(m["source"], -1), *name_vec])
        return np.array(rows, dtype=np.float32)
