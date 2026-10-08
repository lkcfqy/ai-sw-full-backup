# KitGuard acquisition record — InO-10-190

These are author-published photographs and annotations from the fixed source repository commit below. No model inference, image relabeling, or ROI creation was performed during acquisition. This file is a KitGuard acquisition note, not an author-supplied dataset statement.

- Author project: https://www.danielhorvath.eu/sim2real/index.html
- Author repository: https://git.sztaki.hu/emi/sim2real-object-detection
- Commit: `c733a3543157135c591cbe3f9de27e209964af63`
- Source subtree: `test/test_datasets/test_01`
- Author repository license: MIT; preserved in `LICENSE` alongside `AUTHOR_README.md` and `CITATION.bib`.
- Original author archive: `author-test_01.tar.gz`, 254,962,260 bytes.
- Archive SHA-256: `6cd26e12957cd870b4c456fb0be3647b2a9000bcb543baf3b8fd6123befaea34`.
- Extracted author data: `data/`, 1,141 files totaling 288,401,627 bytes.
- `SOURCE_MANIFEST.json`: per-file paths, bytes and SHA-256. Every image matches the author's LFS object digest; text files match the pinned metadata archive.
- `SOURCE_GROUPS.json`: 190 original source IDs linking origin/cropped representations; neither representation creates a new independent sample.
- `ANNOTATION_STATISTICS.json`: read-only annotation counts. Each representation contains 919 boxes in the acquired version, versus the author's README claim of 920. Do not invent the missing box.

`origin` and `cropped` each include 190 color PNGs, 190 depth PNGs, and 190 annotation text files. The class names file is shared. Numeric class 0 means `L-bracket`; class 1 `U-bracket` and class 2 `angle_bracket` must not automatically be merged into KitGuard's L-shaped-support definition.

All PNG headers were readable; origin color dimensions were 1280×720. Full visual quality or truth correctness has not been certified. Author annotations include 15 out-of-bounds boxes in 12 origin photographs; this acquisition preserves them unchanged. Any future derived samples need a declared rule, source grouping, and exclusions before model evaluation.
