import multiprocessing
import sys

from app.main import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(run())
