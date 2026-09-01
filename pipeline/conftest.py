"""Makes `import geo`, `import ingest`, `import match` etc. work when pytest
is invoked from anywhere, the same way running `python -m ...` from this
directory does (see README.md's quickstart) -- pipeline/ itself is not a
package (no __init__.py at this level, by design, so each top-level module
stays independently importable), so pytest's own rootdir-based sys.path
insertion doesn't put it on sys.path automatically.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
