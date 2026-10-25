import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.job_registry import registered_jobs, run_job


class Command(BaseCommand):
    help = "Run registered background jobs once (cron-friendly) or in a simple loop."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("names", nargs="*", help="Jobs to run (default: all)")
        parser.add_argument("--list", action="store_true", help="List registered jobs and exit")
        parser.add_argument("--loop", action="store_true", help="Repeat forever")
        parser.add_argument("--interval", type=int, default=300, help="Seconds between loops")

    def handle(self, *args: Any, **options: Any) -> None:
        jobs = registered_jobs()
        if options["list"]:
            for name in sorted(jobs):
                self.stdout.write(name)
            return
        names = options["names"] or sorted(jobs)
        unknown = [n for n in names if n not in jobs]
        if unknown:
            raise CommandError(f"Unknown job(s): {', '.join(unknown)}")
        while True:
            failed = [n for n in names if not run_job(n)]
            if not options["loop"]:
                if failed:
                    raise CommandError(f"Failed job(s): {', '.join(failed)}")
                return
            time.sleep(options["interval"])
