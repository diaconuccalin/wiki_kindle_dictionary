# Profile Size Estimates

Estimates assume KindleGen flags: `-c2 -gen_ff_mobi7 -dont_append_source`

| Profile | Long tier | Short tier | Total entries | Estimated .mobi | Actual .mobi | Avg bytes/entry | Built on |
|---|---|---|---|---|---|---|---|
| Pocket | 10K | 90K | 100K | ~90 MB | 89.9 MB | 946 | 2026-03-27 |
| Compact | 50K | 200K | 250K | ~270 MB | — | — | — |
| Standard | 100K | 400K | 500K | ~540 MB | — | — | — |
| Large | 100K | 900K | 1M | ~900 MB | — | — | — |
| Full breadth | 0 | 2M | 2M | ~1.4 GB | — | — | — |
| Full encyclopedia 10K | 10K | all (~6.8M) | ~6.8M | ~4.6 GB | — | — | — |
| Full encyclopedia 50K | 50K | all (~6.8M) | ~6.8M | ~4.7 GB | — | — | — |
| Full encyclopedia 100K | 100K | all (~6.8M) | ~6.8M | ~4.8 GB | — | — | — |

## Average bytes per entry (raw HTML)

| Content type | Average bytes |
|---|---|
| Short abstract + 5 orth tags | ~700 |
| Short abstract + 15 orth tags | ~1,100 |
| Long abstract + 5 orth tags | ~3,000 |
| Long abstract + 15 orth tags | ~3,400 |

Final `.mobi` ≈ 74% of raw HTML size (with `-c2 -gen_ff_mobi7 -dont_append_source`).

This is higher than typical ebook compression because dictionary indexes (word lookup tables)
are large relative to content — for the Pocket build: 61.5 MB indexes vs 31.8 MB compressed text.
Text alone compresses to ~35% of original, but indexes add ~2x on top.

## Build History

| Date | Profile | Entries | HTML size | .mobi size | KindleGen passes | Flags |
|---|---|---|---|---|---|---|
| 2026-03-27 | pocket | 100K | 121.9 MB | 89.9 MB | 11 | `-c2 -gen_ff_mobi7 -dont_append_source` |
