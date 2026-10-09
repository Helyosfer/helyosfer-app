import multiprocessing
import sys

PRICE_WORKER_FLAG = "--price-worker"
PACKAGE_CHECK_FLAG = "--check-package"


def main() -> int:
    # A packaged build starts itself again to fetch prices; that copy must
    # never open a window or load the interface.
    if len(sys.argv) >= 3 and sys.argv[1] == PRICE_WORKER_FLAG:
        from services import asset_price_worker

        sys.argv = [sys.argv[0], sys.argv[2]]
        asset_price_worker.main()
        return 0

    if len(sys.argv) >= 2 and sys.argv[1] == PACKAGE_CHECK_FLAG:
        from app import selfcheck

        return selfcheck.run()

    from app.main import run

    return run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
