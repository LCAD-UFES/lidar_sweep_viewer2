import multiprocessing, sys
from lsv2.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()   # the frozen executable is re-invoked by forkserver/resource_tracker; this handles those calls
    sys.exit(main())
