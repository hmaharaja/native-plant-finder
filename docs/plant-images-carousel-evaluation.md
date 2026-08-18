# Plant images carousel evaluation

**Recommendation: DEFER / NO-GO for Phase 5 carousel UI.**

The current image buckets prove that many plants have a second accepted image, but they do not prove that the second image adds a distinct visual role. Under the Phase 5 decision rule, carousel UX needs explicit evidence such as flower, foliage, fruit, whole plant, bark, seed, or similar classification. URL, dimensions, publisher, and occurrence metadata are not enough.

## Audit summary

- Image-backed plants: 3,453
- Plants with `secondaryImage`: 2,997 (86.8%)
- Accepted image records: 6,450
- Primary/secondary duplicate URL pairs: 0
- Repeated accepted image URL slots across the index: 11
- Primary/secondary pairs with the same `gbifId`: 2,136
- Accepted images missing explicit visual classification: 6,450
- Secondary pairs missing visual classification on one or both images: 2,997
- Classified secondary pairs with complementary roles: 0

## Source and license breakdown

| Source / license | Accepted images |
|---|---:|
| `gbif / CC BY` | 3,032 |
| `gbif / CC BY-SA` | 25 |
| `gbif / CC0` | 3,133 |
| `wikimedia_commons / CC BY` | 49 |
| `wikimedia_commons / CC BY-SA` | 99 |
| `wikimedia_commons / CC0` | 3 |
| `wikimedia_commons / Public Domain` | 109 |

## Review artifact

- Secondary-image review CSV: `docs/plant-images-secondary-variety-review.csv`
- The CSV is keyed by `usageKey`, includes plant names when available, primary/secondary image URLs, source links, source/license metadata, duplicate/same-occurrence flags, and empty reviewer fields for manual visual-variety classification.

## Decision

Phase 5 should not ship carousel UI from the current data alone. Secondary-image coverage is high enough to investigate further, but the strict visual-variety evidence is absent. A later phase can move to `GO` only after accepted records or a manual review layer contains explicit complementary visual roles for most image-backed plants with two images.

