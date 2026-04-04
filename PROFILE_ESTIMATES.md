# Profile Size Estimates

Estimates assume KindleGen flags: `-c2 -gen_ff_mobi7 -dont_append_source`

| Profile | Long tier | Short tier | Total entries | Estimated .mobi | Actual .mobi | Avg bytes/entry | Built on |
|---|---|---|---|---|---|---|---|
| Pocket | 100K | 0 | 100K | ~55 MB | 114.9 MB | 1204 | 2026-03-30 |
| Complete | all | 0 | ~6.8M | — | — | — | — |

The Complete profile produces 68 volumes (see [ENCYCLOPEDIA_VOLUMES.md](ENCYCLOPEDIA_VOLUMES.md)).

## Average bytes per entry (raw HTML)

| Content type | Average bytes |
|---|---|
| Short abstract + 5 orth tags | ~700 |
| Short abstract + 15 orth tags | ~1,100 |
| Long abstract + 5 orth tags | ~3,000 |
| Long abstract + 15 orth tags | ~3,400 |

Final `.mobi` ≈ 43% of raw HTML size (with `-c2 -gen_ff_mobi7 -dont_append_source`, `max_orth_variants=100`).

The ratio improved significantly (from ~74%) when `max_orth_variants` was raised from 30 to 100:
more orth variants create more shared content patterns, which Huffdic exploits for better text
compression (31.3% vs 35.3% of raw text). Larger profiles may compress slightly better still.

## Build History

| Date | Profile | Entries | Orth variants (avg) | HTML size | .mobi size | KindleGen passes | Flags |
|---|---|---|---|---|---|---|---|
| 2026-03-27 | pocket | 100K | — (avg ~12.5) | 121.9 MB | 89.9 MB | 11 | `-c2 -gen_ff_mobi7 -dont_append_source` |
| 2026-03-27 | pocket | 100K | 1,248,818 (avg 12.5) | 120.5 MB | 88.9 MB | 11 | `-c2 -gen_ff_mobi7 -dont_append_source` |
| 2026-03-29 | pocket | 100K | 1,683,665 (avg 16.8) | 134.6 MB | 57.7 MB | 10 | `-c2 -gen_ff_mobi7 -dont_append_source` |
| 2026-03-29 | pocket | 100K | 1,683,665 (avg 16.8) | 134.4 MB | 55.0 MB | 11 | `-c2 -gen_ff_mobi7 -dont_append_source` |
| 2026-03-30 | pocket | 100K | — | 202.1 MB | 114.9 MB | — | `-c2 -gen_ff_mobi7 -dont_append_source` |
