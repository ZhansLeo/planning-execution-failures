from __future__ import annotations

import argparse
import json

from .core import (
    aggregate_pilot_ct_b,
    create_pilot_manifest,
    inspect_environment,
    reevaluate,
    run_ct_b,
    run_pilot_ct_b,
    validate_ct_c_offline,
)
from .ct_c import (
    aggregate_pilot_ct_c,
    compare_pilot,
    create_ct_c_manifest,
    run_ct_c,
    run_development_ct_c,
    run_pilot_ct_c,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="ChinaTravel generalization smoke harness")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    ct_b = sub.add_parser("ct-b")
    ct_b.add_argument("--split", choices=["easy", "medium", "human"], default="easy")
    ct_b.add_argument("--uid")
    ct_c = sub.add_parser("ct-c")
    ct_c.add_argument("--split", choices=["easy", "medium", "human"], default="easy")
    ct_c.add_argument("--uid")
    ct_c.add_argument("--real", action="store_true")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--run", required=True)
    sub.add_parser("make-pilot")
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--baseline", choices=["ct-b", "ct-c"], default="ct-b")
    pilot.add_argument("--resume", action="store_true")
    aggregate = sub.add_parser("aggregate-pilot")
    aggregate.add_argument("--baseline", choices=["ct-b", "ct-c"], default="ct-b")
    dev = sub.add_parser("dev")
    dev.add_argument("--baseline", choices=["ct-c"], default="ct-c")
    dev.add_argument("--resume", action="store_true")
    sub.add_parser("compare-pilot")
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(inspect_environment(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "ct-b":
        print(run_ct_b(args.split, args.uid))
        return 0
    if args.command == "ct-c":
        if args.real:
            if not args.uid:
                parser.error("ct-c --real requires --uid")
            print(run_ct_c(args.split, args.uid))
            return 0
        print(json.dumps(validate_ct_c_offline(args.split, args.uid), ensure_ascii=False, indent=2))
        return 0
    if args.command == "evaluate":
        print(reevaluate(args.run))
        return 0
    if args.command == "make-pilot":
        print(json.dumps(create_pilot_manifest(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "pilot":
        runner = run_pilot_ct_b if args.baseline == "ct-b" else run_pilot_ct_c
        print(json.dumps(runner(resume=args.resume), ensure_ascii=False, indent=2))
        return 0
    if args.command == "aggregate-pilot":
        aggregator = aggregate_pilot_ct_b if args.baseline == "ct-b" else aggregate_pilot_ct_c
        print(json.dumps(aggregator(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "dev":
        print(json.dumps(run_development_ct_c(resume=args.resume), ensure_ascii=False, indent=2))
        return 0
    if args.command == "compare-pilot":
        print(json.dumps(compare_pilot(), ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
