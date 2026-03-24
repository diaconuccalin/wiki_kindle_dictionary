# Profile Size Estimates

Estimates assume KindleGen flags: `-c2 -gen_ff_mobi7 -dont_append_source`

| Profile | Long tier | Short tier | Total entries | Estimated .mobi | Actual .mobi | Avg bytes/entry | Built on |
|---|---|---|---|---|---|---|---|
| Pocket | 10K | 90K | 100K | ~30 MB | — | — | — |
| Compact | 50K | 200K | 250K | ~85 MB | — | — | — |
| Standard | 100K | 400K | 500K | ~160 MB | — | — | — |
| Large | 100K | 900K | 1M | ~260 MB | — | — | — |
| Full breadth | 0 | 2M | 2M | ~400 MB | — | — | — |
| Full encyclopedia 10K | 10K | all (~6.8M) | ~6.8M | ~1.4 GB (3 vol) | — | — | — |
| Full encyclopedia 50K | 50K | all (~6.8M) | ~6.8M | ~1.45 GB (3 vol) | — | — | — |
| Full encyclopedia 100K | 100K | all (~6.8M) | ~6.8M | ~1.5 GB (3 vol) | — | — | — |

## Average bytes per entry (raw HTML)

| Content type | Average bytes |
|---|---|
| Short abstract + 5 orth tags | ~700 |
| Short abstract + 15 orth tags | ~1,100 |
| Long abstract + 5 orth tags | ~3,000 |
| Long abstract + 15 orth tags | ~3,400 |

Final `.mobi` ≈ 25–35% of raw HTML size (with `-c2 -gen_ff_mobi7 -dont_append_source`).

## Build History

*No profiles built yet. This section will be updated automatically after each successful build.*
