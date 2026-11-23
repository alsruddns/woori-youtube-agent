import pytest

from woori_youtube.models import JobStatus
from woori_youtube.store import JobStore


def test_job_state_machine_and_upload_dedup(tmp_path):
    store = JobStore(tmp_path / "state.db")
    job_id = store.create_job("us-economy", "2026-11-23")
    store.transition(job_id, JobStatus.RUNNING)
    store.transition(job_id, JobStatus.SUCCEEDED, result={"verified": True})
    assert store.get_job(job_id)["status"] == "succeeded"
    with pytest.raises(ValueError):
        store.transition(job_id, JobStatus.RUNNING)
    store.record_upload("us-economy", "2026-11-23", "video123", "private")
    assert store.has_upload("us-economy", "2026-11-23")
    with pytest.raises(Exception):
        store.record_upload("us-economy", "2026-11-23", "duplicate", "private")


def test_running_job_is_recovered_after_restart(tmp_path):
    store = JobStore(tmp_path / "state.db")
    job_id = store.create_job("us-economy", "2026-11-23")
    store.transition(job_id, JobStatus.RUNNING)
    assert store.recover_interrupted() == 1
    assert store.get_job(job_id)["status"] == "retry"


def test_failed_job_reuses_channel_date_for_safe_retry(tmp_path):
    store = JobStore(tmp_path / "state.db")
    job_id = store.create_job("us-economy", "2026-11-23")
    store.transition(job_id, JobStatus.RUNNING)
    store.transition(job_id, JobStatus.FAILED, error="temporary failure")
    assert store.create_job("us-economy", "2026-11-23") == job_id
    store.transition(job_id, JobStatus.PENDING)
    store.transition(job_id, JobStatus.RUNNING)
    assert store.get_job(job_id)["attempts"] == 2
    assert store.get_job(job_id)["status"] == "running"
