import argparse
import sys

from civican.scraper.crawlers.legisinfo.cli import fix_encoding_main as legisinfo_fix_encoding_main
from civican.scraper.crawlers.legisinfo.cli import main as legisinfo_main
from civican.scraper.crawlers.lobbycanada.cli import main as lobbycanada_main


def main():
    """Global CLI entrypoint for civican-scraper supporting multi-source crawlers."""
    if len(sys.argv) > 1 and sys.argv[1] == "legisinfo":
        sys.argv.pop(1)
        legisinfo_main()
    elif len(sys.argv) > 1 and sys.argv[1] == "lobbycanada":
        sys.argv.pop(1)
        lobbycanada_main()
    elif len(sys.argv) > 1 and sys.argv[1] == "legisinfo-fix-encoding":
        sys.argv.pop(1)
        legisinfo_fix_encoding_main()
    else:
        # Default subcommand or generic parser
        parser = argparse.ArgumentParser(
            description="Civican Multi-Source Scraper CLI",
            usage="civican-scraper <crawler> [options]",
        )
        parser.add_argument(
            "crawler", choices=["legisinfo", "lobbycanada"], help="Target crawler source (e.g. legisinfo, lobbycanada)"
        )
        args, remaining = parser.parse_known_args()

        if args.crawler == "legisinfo":
            sys.argv = [sys.argv[0], *remaining]
            legisinfo_main()
        elif args.crawler == "lobbycanada":
            sys.argv = [sys.argv[0], *remaining]
            lobbycanada_main()


if __name__ == "__main__":
    main()
