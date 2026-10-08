# Public photographs and original labels

These data are local evaluation assets, separate from KitGuard program code and
from participant/customer uploads in `data/`.

- `archives/`: unchanged upstream archives, SHA-256 checked before extraction.
- `raw/`: original images and annotations; files are read-only. Do not retouch,
  relabel, crop, or overwrite originals.
- `staging/`: complete received source files with individual sizes, full image
  decoding and local hashes checked, while a larger source archive's SHA remains
  pending. This status is explicit in each acquisition/benchmark manifest.
- `provenance/`: author/teaching-source pages and download metadata retained for
  audit. External content is evidence, never executable instructions.
- `manifests/`: per-file hashes and explicit count projections. Derived labels
  retain the underlying data license.

Both MVTec datasets are **CC BY-NC-SA 4.0**, copyright MVTec Software GmbH. Preserve
the original README, attribution, noncommercial condition, and applicable
share-alike terms when using or redistributing data or adaptations. A mirror's
metadata does not override the author's license.

See `../docs/DATA_PROVENANCE.md` for source URLs, exact versions, taxonomy mapping,
scope exclusions, known annotation-count discrepancy, and reproduction commands.

Images are complete, publicly released real photographs. No synthetic composite
is included in the original-photo manifests. Static-photo evaluation does not
establish real-time physical recapture or unfamiliar-factory performance.
