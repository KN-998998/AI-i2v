from web.services.task_contract import is_recoverable, retry_plan, task_metadata, update_task


def test_task_contract_records_canonical_phase_and_history():
    job = {"status": "queued"}
    job.update(task_metadata("kling_generation"))

    update_task(job, status="polling", stage="等待 Kling 任务完成", task_id="task-1")
    update_task(job, status="downloading", stage="下载视频")
    update_task(job, status="analyzing", stage="分析视频")
    update_task(job, status="done", stage="片段已入库")

    assert job["task_type"] == "kling_generation"
    assert job["phase"] == "completed"
    assert [event["status"] for event in job["events"]] == ["queued", "polling", "downloading", "analyzing", "done"]
    assert job["task_id"] == "task-1"
    assert not is_recoverable(job["status"])


def test_task_contract_allows_restart_recovery_states():
    assert all(is_recoverable(status) for status in ("queued", "running", "polling", "downloading", "analyzing", "retrying"))
    assert not is_recoverable("done")
    assert not is_recoverable("error")


def test_task_contract_retry_budget_is_bounded_and_exponential():
    job = {**task_metadata("kling_generation"), "retry_count": 0}
    first = retry_plan(job)
    assert first is not None
    assert first["retry_count"] == 1
    assert first["delay_seconds"] == 1

    job["retry_count"] = 2
    assert retry_plan(job) is None

    compose_job = task_metadata("video_composition")
    assert retry_plan(compose_job)["delay_seconds"] == 1
