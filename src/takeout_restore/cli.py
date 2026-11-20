import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="takeout-restore",
        description="Restore metadata from Google Takeout JSON sidecars into photos and videos.",
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0
