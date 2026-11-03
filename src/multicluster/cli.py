"""``mc``: run FirecREST jobs on any registered cluster from one entry point.

mc doctor                                  # can every cluster be reached?
mc run jobs/probe.toml                     # on every cluster
mc run jobs/probe.toml --arch amd          # wherever the architecture fits
mc run jobs/probe.toml --clusters mock-nv,clariden --max-wait 300
mc --fault mock-amd=0.3 run jobs/probe.toml   # simulate a flaky instance
mc status mock-amd:12345
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from multicluster.arch import Arch
from multicluster.clients import ClientPool
from multicluster.experiment import ClusterResult, Outcome, run_on_clusters
from multicluster.jobs import ClusterJobs, QualifiedJobId
from multicluster.profiles import ClusterProfile, ProfileError, load_profiles
from multicluster.router import ClusterRouter, RoutingError
from multicluster.spec import load_job_spec

DEFAULT_CONFIG = Path("clusters.toml")


def _parse_faults(values: Sequence[str]) -> dict[str, float]:
    faults: dict[str, float] = {}
    for value in values:
        cluster, sep, rate = value.partition("=")
        if not sep:
            raise argparse.ArgumentTypeError(f"--fault expects CLUSTER=RATE, got {value!r}")
        faults[cluster] = float(rate)
    return faults


def _load_router(args: argparse.Namespace) -> ClusterRouter:
    profiles = load_profiles(args.config, os.environ)
    for cluster, rate in _parse_faults(args.fault).items():
        if cluster not in profiles:
            raise RoutingError(f"--fault names unknown cluster {cluster!r}")
        profiles[cluster] = profiles[cluster].model_copy(update={"fault_rate": rate})
    return ClusterRouter(profiles, ClientPool())


def _selected(router: ClusterRouter, args: argparse.Namespace) -> list[ClusterProfile]:
    names = args.clusters.split(",") if args.clusters else None
    return router.select(names, Arch(args.arch) if args.arch else None)


async def _doctor(router: ClusterRouter, args: argparse.Namespace) -> int:
    report = await router.health(_selected(router, args))
    for health in report:
        mark = "up  " if health.up else "DOWN"
        print(f"{mark} {health.cluster:<12} {health.latency_sec:6.2f}s  {health.detail}")
    return 0 if all(health.up for health in report) else 1


def _print_results(results: list[ClusterResult]) -> None:
    for r in results:
        job = str(r.job) if r.job else "-"
        print(f"{r.outcome!s:<12} {r.cluster:<12} {job:<22} {r.wall_sec:7.1f}s  {r.detail}")


async def _run(router: ClusterRouter, args: argparse.Namespace) -> int:
    spec = load_job_spec(args.job)
    results = await run_on_clusters(
        router, spec, _selected(router, args), poll_sec=args.poll, max_wait_sec=args.max_wait
    )
    if args.json:
        print(json.dumps([{**asdict(r), "job": str(r.job) if r.job else None} for r in results]))
    else:
        _print_results(results)
    return 0 if all(r.outcome is Outcome.COMPLETED for r in results) else 1


async def _status(router: ClusterRouter, args: argparse.Namespace) -> int:
    job = QualifiedJobId.parse(args.job)
    (profile,) = router.select([job.cluster])
    print(f"{job} {await ClusterJobs(profile, router.client(profile)).state(job)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mc", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="cluster registry TOML")
    parser.add_argument(
        "--fault", action="append", default=[], metavar="CLUSTER=RATE", help="answer RATE of requests 503"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_selection(command: argparse.ArgumentParser) -> None:
        command.add_argument("--clusters", help="comma-separated cluster names (default: all)")
        command.add_argument(
            "--arch", choices=[str(a) for a in Arch], help="only clusters of this architecture"
        )

    doctor = commands.add_parser("doctor", help="check that each cluster's instance answers")
    add_selection(doctor)
    doctor.set_defaults(handler=_doctor)

    run = commands.add_parser("run", help="run a job spec on the selected clusters")
    run.add_argument("job", type=Path, help="job spec TOML, e.g. jobs/probe.toml")
    add_selection(run)
    run.add_argument("--poll", type=float, default=5.0, help="seconds between status checks")
    run.add_argument(
        "--max-wait",
        type=float,
        metavar="SECONDS",
        help="cancel a job not finished after this long, e.g. stuck in the queue (default: wait)",
    )
    run.add_argument("--json", action="store_true", help="print results as JSON")
    run.set_defaults(handler=_run)

    status = commands.add_parser("status", help="state of a job given as CLUSTER:JOBID")
    status.add_argument("job")
    status.set_defaults(handler=_status)
    return parser


async def _main(args: argparse.Namespace) -> int:
    router = _load_router(args)
    try:
        code: int = await args.handler(router, args)
        return code
    finally:
        await router.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_main(args))
    except (ProfileError, RoutingError, ValueError, argparse.ArgumentTypeError, FileNotFoundError) as exc:
        print(f"mc: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
