from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aks_fleet_efficiency.collectors import azure_resource_graph as inventory_module
from aks_fleet_efficiency.collectors.azure_resource_graph import (
    AzureResourceGraphCollector,
    AzureSdkInventoryReader,
    InventoryPage,
    InventoryReadError,
)
from aks_fleet_efficiency.config import OnboardingConfig
from aks_fleet_efficiency.models import AzureInventorySnapshot

TENANT = "00000000-0000-0000-0000-000000000000"
SUBSCRIPTION = "00000000-0000-0000-0000-000000000000"
OTHER_SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"
CLUSTER = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
    "providers/Microsoft.ContainerService/managedClusters/aks-synthetic"
)
AS_OF = datetime(2026, 10, 29, 12, tzinfo=UTC)


def profile(*, subscriptions: list[str] | None = None) -> OnboardingConfig:
    return OnboardingConfig.model_validate(
        {
            "scope": {"tenant_id": TENANT, "subscription_ids": subscriptions or [SUBSCRIPTION]},
            "report_directory": "reports",
        }
    )


def cluster_row(resource_id: str = CLUSTER) -> dict[str, Any]:
    return {
        "id": resource_id,
        "type": "microsoft.containerservice/managedclusters",
        "name": "aks-synthetic",
        "subscriptionId": SUBSCRIPTION,
        "resourceGroup": "rg-synthetic",
        "location": "eastus2",
        "kubernetesVersion": "1.34.1",
        "skuTier": "Standard",
        "nodeProvisioningMode": "Manual",
        "managedPrometheusEnabled": True,
        "costAnalysisEnabled": False,
        "kedaEnabled": True,
        "vpaEnabled": False,
        "tags": {"environment": "nonproduction"},
        "agentPoolProfiles": [
            {
                "name": "apps",
                "vmSize": "Standard_D4s_v5",
                "mode": "User",
                "count": 3,
                "enableAutoScaling": True,
                "minCount": 2,
                "maxCount": 6,
                "availabilityZones": ["1", "2", "3"],
                "scaleSetPriority": "Regular",
                "osType": "Linux",
            }
        ],
    }


class FakeInventoryReader:
    tenant_id = TENANT

    def __init__(self, pages: list[InventoryPage | InventoryReadError]) -> None:
        self.pages = list(pages)
        self.calls: list[tuple[str, str | None, str]] = []

    def query(
        self, *, subscription_id: str, query: str, skip_token: str | None, page_size: int
    ) -> InventoryPage:
        self.calls.append((subscription_id, skip_token, query))
        response = self.pages.pop(0)
        if isinstance(response, InventoryReadError):
            raise response
        return response


def test_inventory_pages_preserve_exact_ids_pools_and_feature_state() -> None:
    fleet = (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-synthetic/"
        "providers/Microsoft.ContainerService/fleets/synthetic-fleet"
    )
    reader = FakeInventoryReader(
        [
            InventoryPage(rows=[cluster_row()], skip_token="second-page"),
            InventoryPage(
                rows=[
                    {
                        "id": f"{fleet}/members/synthetic-member",
                        "type": "microsoft.containerservice/fleets/members",
                        "clusterResourceId": CLUSTER,
                        "subscriptionId": SUBSCRIPTION,
                    }
                ]
            ),
        ]
    )
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert [call[1] for call in reader.calls] == [None, "second-page"]
    assert result.collection.status == "complete"
    assert result.collection.completed_scope == [SUBSCRIPTION]
    assert result.clusters[0].resource_id == CLUSTER
    assert result.clusters[0].fleet_ids == [fleet]
    assert result.clusters[0].keda_enabled is True
    assert result.clusters[0].vpa_enabled is False
    pool = result.clusters[0].node_pools[0]
    assert pool.resource_id == f"{CLUSTER}/agentPools/apps"
    assert pool.zones == ["1", "2", "3"]
    assert pool.autoscaling_enabled is True
    assert pool.node_count == 3


def test_inventory_is_not_a_fabricated_full_fleet_snapshot() -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()])])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    serialized = result.model_dump_json()
    assert "metric_window" not in serialized
    assert "allocatable_cpu" not in serialized
    assert "workloads" not in serialized
    assert result.tenant_id == TENANT


def test_denied_subscription_is_retained_as_a_partial_failure() -> None:
    reader = FakeInventoryReader(
        [
            InventoryPage(rows=[cluster_row()]),
            InventoryReadError("forbidden"),
        ]
    )
    result = AzureResourceGraphCollector(
        profile(subscriptions=[SUBSCRIPTION, OTHER_SUBSCRIPTION]),
        reader=reader,
        clock=lambda: AS_OF,
    ).collect()
    assert result.collection.status == "partial"
    assert result.collection.completed_scope == [SUBSCRIPTION]
    assert result.collection.errors[0].scope == OTHER_SUBSCRIPTION
    assert result.collection.errors[0].code == "forbidden"
    assert len(result.clusters) == 1


def test_throttling_retries_are_bounded_and_counted() -> None:
    reader = FakeInventoryReader(
        [
            InventoryReadError("throttled", retry_after_seconds=1),
            InventoryPage(rows=[cluster_row()]),
        ]
    )
    waits: list[float] = []
    result = AzureResourceGraphCollector(
        profile(), reader=reader, clock=lambda: AS_OF, sleep=waits.append, max_retries=1
    ).collect()
    assert result.collection.status == "complete"
    assert result.collection.retry_count == 1
    assert waits == [1]


def test_exhausted_throttling_never_reports_complete() -> None:
    reader = FakeInventoryReader([InventoryReadError("throttled"), InventoryReadError("throttled")])
    result = AzureResourceGraphCollector(
        profile(), reader=reader, clock=lambda: AS_OF, sleep=lambda _: None, max_retries=1
    ).collect()
    assert result.collection.status == "failed"
    assert not result.collection.completed_scope
    assert result.collection.errors[0].code == "throttled"


def test_tenant_mismatch_is_rejected_before_any_query() -> None:
    reader = FakeInventoryReader([])
    reader.tenant_id = OTHER_SUBSCRIPTION
    with pytest.raises(ValueError, match="tenant"):
        AzureResourceGraphCollector(profile(), reader=reader)
    assert not reader.calls


@pytest.mark.parametrize(
    "page",
    [
        InventoryPage(rows=[], truncated=True),
        InventoryPage(rows=[], skip_token=""),
        InventoryPage(rows=[cluster_row(), cluster_row()]),
        InventoryPage(rows=[{"id": "invalid-id", "type": "unknown-resource"}]),
    ],
)
def test_incomplete_or_duplicate_pages_never_claim_complete(page: InventoryPage) -> None:
    reader = FakeInventoryReader([page])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.status != "complete"
    assert not result.collection.completed_scope
    assert result.collection.errors


def test_cursor_loops_are_bounded_and_keep_partial_evidence() -> None:
    reader = FakeInventoryReader(
        [
            InventoryPage(rows=[cluster_row()], skip_token="cursor"),
            InventoryPage(rows=[], skip_token="cursor"),
        ]
    )
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert len(reader.calls) == 2
    assert result.collection.status == "partial"
    assert result.clusters[0].resource_id == CLUSTER
    assert not result.collection.pagination_complete


def test_page_limit_is_not_a_successful_partial_scan() -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()], skip_token="more")])
    result = AzureResourceGraphCollector(
        profile(), reader=reader, clock=lambda: AS_OF, max_pages=1
    ).collect()
    assert result.collection.status == "partial"
    assert not result.collection.completed_scope


def test_unknown_pool_fields_are_not_fabricated() -> None:
    row = cluster_row()
    pool = row["agentPoolProfiles"][0]
    for field in ["count", "enableAutoScaling", "scaleSetPriority", "availabilityZones"]:
        del pool[field]
    reader = FakeInventoryReader([InventoryPage(rows=[row])])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    normalized = result.clusters[0].node_pools[0]
    assert normalized.node_count is None
    assert normalized.autoscaling_enabled is None
    assert normalized.spot is None
    assert normalized.zones is None
    assert result.clusters[0].fleet_ids is None
    assert result.collection.source_observed_at is None


def test_duplicate_pool_identities_are_rejected() -> None:
    row = cluster_row()
    row["agentPoolProfiles"].append(row["agentPoolProfiles"][0].copy())
    reader = FakeInventoryReader([InventoryPage(rows=[row])])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.status == "failed"
    assert not result.clusters


def test_missing_pool_metadata_is_visible_in_the_receipt() -> None:
    row = cluster_row()
    del row["agentPoolProfiles"]
    reader = FakeInventoryReader([InventoryPage(rows=[row])])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.status == "failed"
    assert any("agentPoolProfiles" in field for field in result.collection.missing_fields)


def test_response_cannot_escape_subscription_scope() -> None:
    row = cluster_row(CLUSTER.replace(SUBSCRIPTION, OTHER_SUBSCRIPTION))
    reader = FakeInventoryReader([InventoryPage(rows=[row])])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.status == "failed"
    assert result.collection.errors[0].code == "identity-mismatch"
    assert not result.clusters


def test_unknown_extra_metadata_is_not_serialized() -> None:
    row = cluster_row()
    row["servicePrincipalProfile"] = {"secret": "synthetic-secret"}
    row["privateFqdn"] = "private.example.invalid"
    row["agentPoolProfiles"][0]["credentials"] = "synthetic-secret"
    reader = FakeInventoryReader([InventoryPage(rows=[row])])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    serialized = result.model_dump_json()
    assert "synthetic-secret" not in serialized
    assert "private.example.invalid" not in serialized
    assert "credentials" not in serialized


def test_query_is_projected_ordered_and_does_not_limit_pagination() -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[])])
    AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    query = reader.calls[0][2]
    assert "| project id, type" in query
    assert "| order by id asc" in query
    assert "| take " not in query
    assert "| limit " not in query
    assert "servicePrincipalProfile" not in query
    assert "privateFqdn" not in query


def test_naive_clock_is_rejected_without_querying() -> None:
    reader = FakeInventoryReader([])
    with pytest.raises(ValueError, match="timezone-aware"):
        AzureResourceGraphCollector(
            profile(), reader=reader, clock=lambda: datetime(2026, 10, 29)
        ).collect()
    assert not reader.calls


def fake_sdk(monkeypatch: pytest.MonkeyPatch, *, token_tenant: str = TENANT) -> SimpleNamespace:
    claims = (
        base64.urlsafe_b64encode(json.dumps({"tid": token_tenant}).encode()).decode().rstrip("=")
    )
    state = SimpleNamespace(
        requests=[], client_options={}, credential_options={}, token_options={}, closed=False
    )

    class Credential:
        def __init__(self, **kwargs: Any) -> None:
            state.credential_options = kwargs

        def get_token(self, *scopes: str, **kwargs: Any) -> SimpleNamespace:
            state.token_options = kwargs
            return SimpleNamespace(token=f"synthetic.{claims}.signature", expires_on=9999999999)

        def close(self) -> None:
            state.closed = True

    class HttpError(Exception):
        def __init__(self, status_code: int) -> None:
            super().__init__("synthetic-secret-response-body")
            self.status_code = status_code
            self.response = SimpleNamespace(headers={"Retry-After": "2"})

    class GraphClient:
        def __init__(self, credential: Any, **kwargs: Any) -> None:
            self.credential = credential
            state.client_options = kwargs

        def resources(self, request: Any, **kwargs: Any) -> SimpleNamespace:
            self.credential.get_token("https://management.azure.com/.default")
            state.requests.append(request)
            if hasattr(state, "error_status"):
                raise HttpError(state.error_status)
            kwargs["raw_response_hook"](
                SimpleNamespace(
                    http_response=SimpleNamespace(headers={"Date": "Thu, 29 Oct 2026 12:00:00 GMT"})
                )
            )
            return SimpleNamespace(
                data=[cluster_row()],
                count=1,
                total_records=getattr(state, "total_records", 1),
                result_truncated="false",
                skip_token=None,
            )

        def close(self) -> None:
            state.closed = True

    modules = {
        "azure.identity": SimpleNamespace(DefaultAzureCredential=Credential),
        "azure.mgmt.resourcegraph": SimpleNamespace(ResourceGraphClient=GraphClient),
        "azure.mgmt.resourcegraph.models": SimpleNamespace(
            QueryRequest=SimpleNamespace, QueryRequestOptions=SimpleNamespace
        ),
        "azure.core.exceptions": SimpleNamespace(
            HttpResponseError=HttpError,
            ClientAuthenticationError=type("AuthenticationError", (Exception,), {}),
            ServiceRequestError=type("RequestError", (Exception,), {}),
            ServiceResponseError=type("ResponseError", (Exception,), {}),
        ),
    }
    monkeypatch.setattr(inventory_module, "import_module", lambda name: modules[name])
    return state


def test_sdk_reader_uses_bounded_projected_resource_graph_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = fake_sdk(monkeypatch)
    with AzureSdkInventoryReader(profile()) as reader:
        page = reader.query(
            subscription_id=SUBSCRIPTION,
            query="Resources | project id",
            skip_token="cursor",
            page_size=100,
        )
    request = state.requests[0]
    assert request.subscriptions == [SUBSCRIPTION]
    assert request.options.skip_token == "cursor"
    assert request.options.result_format == "objectArray"
    assert request.options.allow_partial_scopes is False
    assert state.client_options["retry_total"] == 0
    assert state.credential_options["exclude_interactive_browser_credential"] is True
    assert state.token_options["tenant_id"] == TENANT
    assert page.observed_at == AS_OF
    assert state.closed is True


def test_sdk_reader_rejects_a_token_from_another_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    state = fake_sdk(monkeypatch, token_tenant=OTHER_SUBSCRIPTION)
    with AzureSdkInventoryReader(profile()) as reader:
        with pytest.raises(InventoryReadError) as error:
            reader.query(
                subscription_id=SUBSCRIPTION, query="Resources", skip_token=None, page_size=100
            )
    assert error.value.code == "unauthorized"
    assert not state.requests


@pytest.mark.parametrize(
    ("status_code", "code"),
    [(401, "unauthorized"), (403, "forbidden"), (429, "throttled"), (503, "unavailable")],
)
def test_sdk_errors_are_structured_without_raw_response_text(
    monkeypatch: pytest.MonkeyPatch, status_code: int, code: str
) -> None:
    state = fake_sdk(monkeypatch)
    state.error_status = status_code
    with AzureSdkInventoryReader(profile()) as reader:
        with pytest.raises(InventoryReadError) as error:
            reader.query(
                subscription_id=SUBSCRIPTION, query="Resources", skip_token=None, page_size=100
            )
    assert error.value.code == code
    assert "synthetic-secret" not in str(error.value)
    assert error.value.retry_after_seconds == 2


def test_sdk_reader_never_requests_an_unapproved_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = fake_sdk(monkeypatch)
    with AzureSdkInventoryReader(profile()) as reader:
        with pytest.raises(InventoryReadError):
            reader.query(
                subscription_id=OTHER_SUBSCRIPTION,
                query="Resources",
                skip_token=None,
                page_size=100,
            )
    assert not state.requests


def test_sdk_total_record_count_cannot_hide_a_truncated_first_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = fake_sdk(monkeypatch)
    state.total_records = 2
    with AzureSdkInventoryReader(profile()) as reader:
        with pytest.raises(InventoryReadError) as error:
            reader.query(
                subscription_id=SUBSCRIPTION, query="Resources", skip_token=None, page_size=100
            )
    assert error.value.code == "invalid-response"


@pytest.mark.parametrize("observed_at", [AS_OF + timedelta(seconds=1), datetime(2026, 10, 29)])
def test_invalid_source_timestamps_produce_a_receipt_not_an_unhandled_error(
    observed_at: datetime,
) -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()], observed_at=observed_at)])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.status != "complete"
    assert result.collection.errors[0].code == "invalid-response"


def test_known_source_timestamp_is_preserved_instead_of_local_clock_substitution() -> None:
    observed_at = AS_OF - timedelta(hours=2)
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()], observed_at=observed_at)])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.source_observed_at == observed_at


def test_server_cannot_exceed_the_requested_page_bound() -> None:
    second = cluster_row(CLUSTER.replace("aks-synthetic", "aks-other"))
    second["name"] = "aks-other"
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row(), second])])
    result = AzureResourceGraphCollector(
        profile(), reader=reader, clock=lambda: AS_OF, page_size=1
    ).collect()
    assert result.collection.status == "failed"


def test_selected_cluster_filter_is_in_the_server_query() -> None:
    scoped = profile().model_dump(mode="json")
    scoped["clusters"] = [{"resource_id": CLUSTER}]
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()])])
    result = AzureResourceGraphCollector(
        OnboardingConfig.model_validate(scoped), reader=reader, clock=lambda: AS_OF
    ).collect()
    assert result.collection.status == "complete"
    assert f"id in~ ({json.dumps(CLUSTER)})" in reader.calls[0][2]


def test_missing_explicit_cluster_is_not_a_complete_empty_subscription() -> None:
    scoped = profile().model_dump(mode="json")
    scoped["clusters"] = [{"resource_id": CLUSTER}]
    reader = FakeInventoryReader([InventoryPage(rows=[])])
    result = AzureResourceGraphCollector(
        OnboardingConfig.model_validate(scoped), reader=reader, clock=lambda: AS_OF
    ).collect()
    assert result.collection.status == "failed"


def test_retry_delay_is_capped() -> None:
    reader = FakeInventoryReader(
        [InventoryReadError("throttled", retry_after_seconds=99999), InventoryPage(rows=[])]
    )
    waits: list[float] = []
    result = AzureResourceGraphCollector(
        profile(), reader=reader, clock=lambda: AS_OF, sleep=waits.append
    ).collect()
    assert result.collection.status == "complete"
    assert waits == [30]


def test_inventory_contract_round_trips_and_matches_committed_schema() -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()], total_records=1)])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert AzureInventorySnapshot.model_validate_json(result.model_dump_json()) == result
    committed = json.loads(Path("schemas/azure-inventory.schema.json").read_text(encoding="utf-8"))
    assert committed == AzureInventorySnapshot.model_json_schema()


@pytest.mark.parametrize("total", [0, 2])
def test_total_record_mismatch_is_not_complete_inventory(total: int) -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()], total_records=total)])
    result = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF).collect()
    assert result.collection.status != "complete"


def test_collector_can_query_again_without_retaining_prior_results() -> None:
    reader = FakeInventoryReader([InventoryPage(rows=[cluster_row()]), InventoryPage(rows=[])])
    collector = AzureResourceGraphCollector(profile(), reader=reader, clock=lambda: AS_OF)
    first = collector.collect()
    second = collector.collect()
    assert len(first.clusters) == 1
    assert second.clusters == []
