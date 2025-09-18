"""支持 python -m xyz_dl 运行方式"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
