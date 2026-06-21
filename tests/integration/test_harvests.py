# -*- coding: utf-8 -*-
"""Integration tests for Harvest APIs and Cron synchronization."""

from __future__ import annotations

import pytest

_HARVEST_HTTP_TIMEOUT = 20.0


def _harvest_spec(name: str) -> dict:
    return {
        "name": name,
        "template_id": "integration",
        "emoji": "H",
        "enabled": True,
        "prompt": "Create a short integration harvest briefing.",
        "schedule": {
            "type": "cron",
            "cron": "0 0 1 1 *",
            "timezone": "UTC",
        },
        "target": {
            "channel": "console",
            "user_id": "harvest-integ",
            "session_id": "console:harvest-integ",
        },
        "runtime": {
            "max_concurrency": 1,
            "timeout_seconds": 120,
            "misfire_grace_seconds": 60,
            "share_session": True,
        },
    }


@pytest.mark.integration
@pytest.mark.p1
def test_agent_scoped_harvest_lifecycle_syncs_cron(app_server) -> None:
    """Create/update-control/delete Harvest and verify Cron backing job."""
    agent_id = "integ_harvest_lifecycle_01"
    base = f"/api/agents/{agent_id}"
    harvest_id: str | None = None

    create_agent = app_server.api_request(
        "POST",
        "/api/agents",
        json={
            "id": agent_id,
            "name": "Harvest lifecycle agent",
            "description": "",
        },
        timeout=_HARVEST_HTTP_TIMEOUT,
    )
    assert create_agent.status_code == 201, app_server.logs_tail()

    try:
        create_resp = app_server.api_request(
            "POST",
            f"{base}/harvests",
            json=_harvest_spec("integration harvest"),
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert create_resp.status_code == 200, app_server.logs_tail()
        created = create_resp.json()
        harvest_id = created.get("id")
        cron_job_id = created.get("cron_job_id")
        assert isinstance(harvest_id, str) and harvest_id
        assert isinstance(cron_job_id, str) and cron_job_id.startswith(
            "harvest:",
        )

        list_resp = app_server.api_request(
            "GET",
            f"{base}/harvests",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert list_resp.status_code == 200, app_server.logs_tail()
        assert harvest_id in {item.get("id") for item in list_resp.json()}

        cron_resp = app_server.api_request(
            "GET",
            f"{base}/cron/jobs/{cron_job_id}",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert cron_resp.status_code == 200, app_server.logs_tail()
        cron_spec = cron_resp.json()["spec"]
        assert cron_spec["meta"]["source"] == "harvest"
        assert cron_spec["meta"]["harvest_id"] == harvest_id
        assert cron_spec["save_result_to_inbox"] is True

        pause_resp = app_server.api_request(
            "POST",
            f"{base}/harvests/{harvest_id}/pause",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert pause_resp.status_code == 200, app_server.logs_tail()
        assert pause_resp.json()["enabled"] is False
        assert pause_resp.json()["status"] == "paused"

        resume_resp = app_server.api_request(
            "POST",
            f"{base}/harvests/{harvest_id}/resume",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert resume_resp.status_code == 200, app_server.logs_tail()
        assert resume_resp.json()["enabled"] is True

        delete_resp = app_server.api_request(
            "DELETE",
            f"{base}/harvests/{harvest_id}",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert delete_resp.status_code == 200, app_server.logs_tail()
        harvest_id = None

        cron_after_delete = app_server.api_request(
            "GET",
            f"{base}/cron/jobs/{cron_job_id}",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
        assert cron_after_delete.status_code == 404, app_server.logs_tail()
    finally:
        if harvest_id:
            app_server.api_request(
                "DELETE",
                f"{base}/harvests/{harvest_id}",
                timeout=_HARVEST_HTTP_TIMEOUT,
            )
        app_server.api_request(
            "DELETE",
            f"/api/agents/{agent_id}",
            timeout=_HARVEST_HTTP_TIMEOUT,
        )
