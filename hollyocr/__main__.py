"""Entry point for `python -m hollyocr`.

Encaminha para o mesmo comportamento da interface e da linha de comando usado
por ``python hollyocr/app.py`` e pelo aplicativo empacotado.
"""

import sys


def main():
    # The actual CLI/GUI dispatch lives in cli.main.main(), which handles both
    # the no-arg case (opens GUI) and explicit -i/-o flags (CLI batch mode).
    from hollyocr.cli.main import main as cli_main

    cli_main()


if __name__ == "__main__":
    sys.exit(main())
