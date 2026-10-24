"""Codeforces sync pipeline: fetch pages, upsert idempotently, derive solves.

Consistency model:
- Problem/submission upserts commit per page, so an interrupted run leaves
  only already-verified data (all writes are idempotent — a re-run costs
  refetching, not repairing).
- The account cursor and job success commit ONLY after the last page, in the
  same transaction — a partial import is never marked complete.
- first_solved_at derives from the earliest accepted submission and can only
  move EARLIER as older data appears; it is never overwritten by later data.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.codeforces.client import CfApiError, CfHandleNotFound, CodeforcesApiClient
from app.integrations.codeforces.normalizer import problem_from_cf, submission_from_cf
from app.models import CfAccount, SyncJob
from app.models.base import utcnow
from app.repositories import codeforces as repo

logger = logging.getLogger(__name__)


@dataclass
class ImportStats:
    pages_fetched: int = 0
    submissions_seen: int = 0
    new_submissions: int = 0
    problems_touched: set[uuid.UUID] = field(default_factory=set)
    max_seen_submission_id: int | None = None

    def as_progress(self) -> dict[str, int]:
        return {
            "pages_fetched": self.pages_fetched,
            "submissions_seen": self.submissions_seen,
            "new_submissions": self.new_submissions,
        }


class SyncImporter:
    def __init__(
        self,
        db: Session,
        account: CfAccount,
        client: CodeforcesApiClient,
        *,
        page_size: int,
        historical_max_pages: int,
        incremental_max_pages: int,
    ):
        self.db = db
        self.account = account
        self.client = client
        self.page_size = page_size
        self.historical_max_pages = historical_max_pages
        self.incremental_max_pages = incremental_max_pages

    # ------------------------------------------------------------------ run

    def run(self, job: SyncJob) -> ImportStats:
        stats = ImportStats()
        mode = job.job_type
        try:
            self._validate_handle(mode)
            repo.lock_account(self.db, self.account)
            self._guard_concurrent(job)

            max_pages = (
                self.historical_max_pages
                if mode in ("historical", "reconcile")
                else self.incremental_max_pages
            )
            self._walk_pages(job, mode, max_pages, stats)
            self._finalize_success(job, stats)
            return stats
        except _Superseded:
            # Job was already marked cancelled by the concurrency guard.
            return stats
        except CfHandleNotFound:
            self._finalize_failure(job, f"handle not found: {self.account.handle}", stats)
            raise
        except CfApiError as exc:
            self._finalize_failure(job, str(exc), stats)
            raise
        except Exception as exc:  # noqa: BLE001 — job must record any failure
            self.db.rollback()
            self._finalize_failure(job, f"{type(exc).__name__}: {exc}", stats)
            raise

    # ------------------------------------------------------------ internals

    def _validate_handle(self, mode: str) -> None:
        if mode in ("historical", "reconcile") or self.account.verified_at is None:
            self.client.get_user_info(self.account.handle)
            if self.account.verified_at is None:
                self.account.verified_at = utcnow()
                self.db.commit()

    def _guard_concurrent(self, job: SyncJob) -> None:
        other = repo.other_running_job(self.db, self.account.id, exclude_job_id=job.id)
        if other is not None:
            repo.finish_job(
                self.db, job.id, status="cancelled", error_summary="superseded: concurrent sync"
            )
            raise _Superseded()

    def _walk_pages(self, job: SyncJob, mode: str, max_pages: int, stats: ImportStats) -> None:
        offset = 1
        for _ in range(max_pages):
            page = self.client.fetch_status_page(self.account.handle, offset, self.page_size)
            if not page:
                break
            stats.pages_fetched += 1
            new_count = self._process_page(page, stats)
            repo.update_job_progress(self.db, job.id, stats.as_progress())

            if len(page) < self.page_size:
                break  # reached the end of history
            if mode == "incremental" and new_count == 0:
                # Page 1 already served as the overlap: known items in it had
                # their verdicts refreshed. Nothing new means we've reached
                # fully-known territory.
                break
            offset += len(page)
        else:
            raise CfApiError(
                f"{mode} sync exceeded {max_pages} pages for {self.account.handle!r}; "
                "increase the page cap or run reconciliation"
            )

    def _process_page(self, page: list[dict[str, Any]], stats: ImportStats) -> int:
        problems = repo.upsert_problems(
            self.db, [problem_from_cf(item["problem"]) for item in page]
        )
        submission_dicts = []
        for item in page:
            data = submission_from_cf(item)
            data["canonical_key"] = problem_from_cf(item["problem"])["canonical_key"]
            submission_dicts.append(data)
            cf_id = data["cf_submission_id"]
            if stats.max_seen_submission_id is None or cf_id > stats.max_seen_submission_id:
                stats.max_seen_submission_id = cf_id

        new_count = repo.upsert_submissions(
            self.db,
            account_id=self.account.id,
            problems=problems,
            submission_dicts=submission_dicts,
        )
        stats.submissions_seen += len(page)
        stats.new_submissions += new_count
        stats.problems_touched.update(problems[k].id for k in problems)
        self.db.commit()  # page-local durability; idempotent on re-run
        return new_count

    def _finalize_success(self, job: SyncJob, stats: ImportStats) -> None:
        repo.recompute_user_problems(
            self.db, user_id=self.account.user_id, problem_ids=list(stats.problems_touched)
        )
        previous = self.account.sync_cursor or {}
        previous_max = previous.get("last_seen_submission_id")
        max_id = stats.max_seen_submission_id
        if max_id is None:
            max_id = previous_max  # empty history: keep cursor as-is
        elif previous_max is not None:
            max_id = max(int(previous_max), int(max_id))
        self.account.sync_cursor = {"last_seen_submission_id": max_id}
        self.account.last_synced_at = utcnow()
        self.account.last_sync_error = None
        repo.finish_job(self.db, job.id, status="succeeded", progress=stats.as_progress())

    def _finalize_failure(self, job: SyncJob, message: str, stats: ImportStats) -> None:
        try:
            self.db.rollback()
            self.account.last_sync_error = message[:2000]
            repo.finish_job(
                self.db,
                job.id,
                status="failed",
                error_summary=message,
                progress=stats.as_progress(),
            )
        except Exception:  # noqa: BLE001 — never mask the original failure
            logger.exception("failed to record sync failure for job %s", job.id)


class _Superseded(Exception):
    """Internal control flow: this job yielded to a concurrent sync."""
