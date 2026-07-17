# Frozen 2023 Population-Top-20 Run

This archive preserves the original, unmodified outputs of the first complete
canonical 2023 population-top-20 research and judging cycle.

- Research run: `2023-population-top20-canonical-full-v1`
- Judge run: `2023-population-top20-canonical-full-judges-v1`
- Batch manifest: `configs/research-batches/2023-population-top20-canonical.yaml`
- Archive: `2023-population-top20-canonical-complete-original.tar.zst`
- SHA-256: `c110716ce38f74922b61efda9eb292a3c7f4d91b17dfd4e5bc9d0c23a0d684cc`
- Uncompressed archive size: 93,542,400 bytes
- Compressed archive size: approximately 4.1 MiB

The archive was tested successfully with `zstd -t`. Repairs, reformatting, and
rejudgment must use new run identifiers and must not modify these original run
directories or this archive.

Restore from the repository root with:

```bash
tar --use-compress-program=unzstd -xf \
  research/archives/2023-population-top20-canonical-complete-original.tar.zst
```
