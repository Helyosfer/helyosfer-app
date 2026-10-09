"""A DIAGNOSTIC TOOL -- NOT a permanent gate. Measures the memory profile of the backup hash.

`create_backup` and `_verify_staged` computed `finance.db`'s SHA-256 with
`hashlib.sha256(path.read_bytes())`. `read_bytes()` pulls the WHOLE file into
memory as an additional Python `bytes` object; with the package limit at
256 MiB that means a quarter of a gigabyte allocated for a single hash.

This script compares the two approaches on the same file:
  * peak Python memory allocation (`tracemalloc`),
  * wall clock time.

DELIBERATELY NOT A CI GATE: the timing depends on the machine, the disk and
the file cache. The permanent guarantee is the memory-scaling test in
`tests/test_backup_hash_streaming.py`; this only produces a reportable number.

    python scripts/audit/measure_backup_hash_memory.py --mib 64

"""

import argparse
import hashlib
import os
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def _read_bytes_digest(path):
    """The old approach -- kept here for comparison."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _measure(label, function, path):
    tracemalloc.start()
    started = time.perf_counter()
    digest = function(path)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "label": label,
        "digest": digest,
        "peak_bytes": peak,
        "seconds": elapsed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mib", type=int, default=64,
                        help="ölçüm dosyasının boyutu (MiB)")
    args = parser.parse_args()

    from services.backup_service import _sha256_file

    size = args.mib * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="helyosfer-hash-bench-") as temp:
        path = Path(temp) / "finance.db"
        chunk = os.urandom(1024 * 1024)
        with open(path, "wb") as handle:
            for _ in range(args.mib):
                handle.write(chunk)

        results = [
            _measure("read_bytes (eski)", _read_bytes_digest, path),
            _measure("streaming (_sha256_file)", _sha256_file, path),
        ]

    assert results[0]["digest"] == results[1]["digest"], \
        "hash sonuçları ayrıştı — streaming yaklaşımı aynı özeti üretmiyor"

    print(f"Dosya boyutu: {size:,} bayt ({args.mib} MiB)")
    print(f"SHA-256     : {results[0]['digest']}")
    print()
    print(f"{'yaklaşım':<28}{'tepe bellek':>16}{'oran':>10}{'süre (sn)':>12}")
    for result in results:
        ratio = result["peak_bytes"] / size
        print(f"{result['label']:<28}{result['peak_bytes']:>16,}"
              f"{ratio:>9.2f}x{result['seconds']:>12.3f}")
    saved = results[0]["peak_bytes"] - results[1]["peak_bytes"]
    print()
    print(f"Tepe bellek farkı: {saved:,} bayt "
          f"({saved / max(results[0]['peak_bytes'], 1):.1%} azalma)")


if __name__ == "__main__":
    main()
