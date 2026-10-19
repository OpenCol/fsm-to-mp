from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fsm_to_mp import __version__
from fsm_to_mp.convert import convert_map, encode_plane0
from fsm_to_mp.fsm.reader import read_fsm, summarize_fsm
from fsm_to_mp.model import ConversionResult
from fsm_to_mp.mp.reader import read_mp
from fsm_to_mp.mp.writer import write_mp
from fsm_to_mp.mpx.writer import write_mpx
from fsm_to_mp.resample import MAX_SIDE, resample
from fsm_to_mp.validation import validate_written_mp, warning_counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert FreeCol .fsm maps to Colonization .MP maps.")
    parser.add_argument("input", type=Path, help="FreeCol .fsm input map")
    parser.add_argument("output", type=Path, nargs="?", help="Colonization .MP output path")
    parser.add_argument("--summary", action="store_true", help="print a JSON summary of the .fsm and exit")
    parser.add_argument("--mpx", type=Path, metavar="PATH", help="also write OpenCol's .MPX: the terrain plus the map's resources, rumours and villages")
    parser.add_argument("--info", action="append", default=[], metavar="KEY=VALUE", help="a line of the .MPX's INFO (title, author, source, license, ...); repeatable")
    parser.add_argument("--copy-tiles", action="store_true", help="copy FreeCol tile (x, y) to square (x, y), as 0.1 did, instead of resampling (stretches the map)")
    parser.add_argument("--max-side", type=int, default=MAX_SIDE, help=f"scale a resampled map down to fit this many squares a side (default {MAX_SIDE})")
    parser.add_argument("--warnings", choices=("summary", "all", "none"), default="summary")
    parser.add_argument("--version", action="version", version=f"fsm-to-mp {__version__}")
    args = parser.parse_args(argv)

    if args.summary:
        print(json.dumps(summarize_fsm(args.input), indent=2, sort_keys=True))
        return 0

    if args.output is None and args.mpx is None:
        parser.error("an output .MP or --mpx is required unless --summary is used")
    info = {"title": args.input.stem}
    for line in args.info:
        key, sep, value = line.partition("=")
        if not sep:
            parser.error(f"--info {line!r} is not KEY=VALUE")
        info[key.strip()] = value.strip()
    info.setdefault("converter", f"fsm-to-mp {__version__}")

    source = read_fsm(args.input)
    # the warnings are the FreeCol tiles', one per tile, whatever the resampling does with them
    warnings = list(convert_map(source).warnings)
    squares = source
    if not args.copy_tiles:
        squares, resampled = resample(source, args.max_side)
        warnings += resampled
    converted = convert_map(squares).map
    plane0 = encode_plane0(converted)
    if args.output is not None:
        write_mp(args.output, converted, plane0)
        validate_written_mp(read_mp(args.output), converted.width, converted.height)
    if args.mpx is not None:
        # the .MPX carries the resources (each one it cannot is its own warning)
        warnings = [w for w in warnings if w.code != "resource-lost"]
        warnings += write_mpx(args.mpx, converted, plane0, info)
    result = ConversionResult(converted, tuple(warnings))

    if args.warnings == "summary":
        counts = warning_counts(result)
        if counts:
            print(json.dumps(counts, indent=2, sort_keys=True), file=sys.stderr)
    elif args.warnings == "all":
        for warning in result.warnings:
            print(f"{warning.x},{warning.y}: {warning.code}: {warning.message}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
