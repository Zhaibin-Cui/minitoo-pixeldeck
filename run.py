"""Source-checkout entry point; installed users can run `pixeldeck`."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from pixeldeck.cli import main
if __name__ == "__main__":
    main()
