import argparse

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    # suppress default so it doesn't overwrite
    common.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser()
    # default here
    parser.add_argument("--format", choices=["text", "json"], default="text")

    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", parents=[common])
    
    return parser

p = build_parser()
print("before:", getattr(p.parse_args(["--format", "json", "list"]), "format", "missing"))
print("after:", getattr(p.parse_args(["list", "--format", "json"]), "format", "missing"))
print("none:", getattr(p.parse_args(["list"]), "format", "missing"))
