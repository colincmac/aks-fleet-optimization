from __future__ import annotations

import base64
import binascii
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib import import_module
from math import isfinite
from types import TracebackType
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError

from aks_fleet_efficiency.config import ClusterTarget, OnboardingConfig
from aks_fleet_efficiency.models import (
    AzureClusterInventory,
    AzureInventorySnapshot,
    AzureNodePoolInventory,
    CollectionError,
    CollectionErrorCode,
    CollectionStatus,
    CollectorResult,
)

CLUSTER_TYPE = "microsoft.containerservice/managedclusters"
MEMBER_TYPE = "microsoft.containerservice/fleets/members"
QUERY = """Resources
| where type in~ (
    'microsoft.containerservice/managedclusters', 'microsoft.containerservice/fleets/members')
| project id, type, name, subscriptionId, resourceGroup, location, tags,
    kubernetesVersion=coalesce(properties.currentKubernetesVersion, properties.kubernetesVersion),
    skuTier=sku.tier, agentPoolProfiles=properties.agentPoolProfiles,
    nodeProvisioningMode=properties.nodeProvisioningProfile.mode,
    managedPrometheusEnabled=properties.azureMonitorProfile.metrics.enabled,
    costAnalysisEnabled=properties.metricsProfile.costAnalysis.enabled,
    kedaEnabled=properties.workloadAutoScalerProfile.keda.enabled,
    vpaEnabled=properties.workloadAutoScalerProfile.verticalPodAutoscaler.enabled,
    clusterResourceId=tostring(properties.clusterResourceId)
"""


def inventory_query(targets: set[str]) -> str:
    query = QUERY
    if targets:
        literals = ", ".join(json.dumps(value) for value in sorted(targets))
        query += f"| where id in~ ({literals}) or clusterResourceId in~ ({literals})\n"
    return query + "| order by id asc"


@dataclass(frozen=True)
class InventoryPage:
    rows: list[dict[str, Any]]
    skip_token: str | None = None
    truncated: bool = False
    observed_at: datetime | None = None
    total_records: int | None = None


class InventoryReadError(Exception):
    def __init__(
        self,
        code: CollectionErrorCode,
        *,
        retry_after_seconds: float | None = None,
        missing_fields: tuple[str, ...] = (),
    ) -> None:
        super().__init__(code)
        self.code: CollectionErrorCode = code
        self.retry_after_seconds = retry_after_seconds
        self.missing_fields = missing_fields


class InventoryReader(Protocol):
    tenant_id: str

    def query(
        self, *, subscription_id: str, query: str, skip_token: str | None, page_size: int
    ) -> InventoryPage: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _TenantBoundCredential:
    def __init__(self, credential: Any, tenant_id: str) -> None:
        self.credential = credential
        self.tenant_id = tenant_id

    def get_token(self, *scopes: str, **kwargs: Any) -> Any:
        hint = kwargs.pop("tenant_id", None)
        if hint is not None and str(hint) != self.tenant_id:
            raise InventoryReadError("unauthorized")
        token = self.credential.get_token(*scopes, tenant_id=self.tenant_id, **kwargs)
        try:
            parts = token.token.split(".")
            if len(parts) != 3:
                raise ValueError("unsupported token format")
            payload = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
            claims = json.loads(payload)
            if not isinstance(claims, dict) or UUID(str(claims.get("tid"))) != UUID(self.tenant_id):
                raise ValueError("tenant mismatch")
        except (AttributeError, binascii.Error, TypeError, ValueError):
            raise InventoryReadError("unauthorized") from None
        return token


class AzureSdkInventoryReader:
    def __init__(
        self,
        profile: OnboardingConfig,
        *,
        credential: Any = None,
        request_timeout_seconds: float = 30,
    ) -> None:
        if not isfinite(request_timeout_seconds) or not 0 < request_timeout_seconds <= 120:
            raise ValueError("inventory request timeout must be between zero and 120 seconds")
        try:
            identity = import_module("azure.identity")
            graph = import_module("azure.mgmt.resourcegraph")
            self.models = import_module("azure.mgmt.resourcegraph.models")
            self.errors = import_module("azure.core.exceptions")
        except ImportError:
            raise RuntimeError(
                "Install the project's azure optional dependencies to collect inventory."
            ) from None
        self.tenant_id = str(profile.scope.tenant_id)
        self.subscriptions = {str(value) for value in profile.scope.subscription_ids}
        self.timeout = request_timeout_seconds
        self.owns_credential = credential is None
        self.credential = (
            credential
            if credential is not None
            else identity.DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
                exclude_broker_credential=True,
                process_timeout=10,
                connection_timeout=request_timeout_seconds,
                read_timeout=request_timeout_seconds,
                retry_total=0,
            )
        )
        self.client = graph.ResourceGraphClient(
            _TenantBoundCredential(self.credential, self.tenant_id),
            base_url="https://management.azure.com",
            retry_total=0,
            logging_enable=False,
        )

    def query(
        self, *, subscription_id: str, query: str, skip_token: str | None, page_size: int
    ) -> InventoryPage:
        if subscription_id not in self.subscriptions or not 1 <= page_size <= 1000:
            raise InventoryReadError("identity-mismatch")
        observed_at = None

        def capture_date(response: Any) -> None:
            nonlocal observed_at
            value = response.http_response.headers.get("Date")
            if value:
                try:
                    parsed = parsedate_to_datetime(value)
                    if parsed.tzinfo is not None:
                        observed_at = parsed.astimezone(UTC)
                except (TypeError, ValueError, OverflowError):
                    observed_at = None

        request = self.models.QueryRequest(
            subscriptions=[subscription_id],
            query=query,
            options=self.models.QueryRequestOptions(
                top=page_size,
                skip_token=skip_token,
                result_format="objectArray",
                allow_partial_scopes=False,
            ),
        )
        try:
            response = self.client.resources(
                request,
                raw_response_hook=capture_date,
                connection_timeout=self.timeout,
                read_timeout=self.timeout,
                logging_enable=False,
            )
        except self.errors.ClientAuthenticationError:
            raise InventoryReadError("unauthorized") from None
        except self.errors.HttpResponseError as error:
            codes: dict[int, CollectionErrorCode] = {
                401: "unauthorized",
                403: "forbidden",
                408: "timeout",
                429: "throttled",
                500: "unavailable",
                502: "unavailable",
                503: "unavailable",
                504: "timeout",
            }
            delay = None
            if error.response is not None:
                try:
                    parsed_delay = float(error.response.headers.get("Retry-After", ""))
                    delay = parsed_delay if isfinite(parsed_delay) else None
                except (TypeError, ValueError):
                    delay = None
            raise InventoryReadError(
                codes.get(error.status_code, "invalid-response"), retry_after_seconds=delay
            ) from None
        except (self.errors.ServiceRequestError, self.errors.ServiceResponseError):
            raise InventoryReadError("unavailable") from None
        except TimeoutError:
            raise InventoryReadError("timeout") from None
        rows = response.data
        if (
            not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
            or response.count != len(rows)
            or not isinstance(response.total_records, int)
            or response.total_records < len(rows)
            or (
                skip_token is None
                and response.skip_token is None
                and response.total_records != len(rows)
            )
            or response.result_truncated not in {"true", "false", True, False}
            or (response.skip_token is not None and not isinstance(response.skip_token, str))
        ):
            raise InventoryReadError("invalid-response")
        return InventoryPage(
            rows=rows,
            skip_token=response.skip_token,
            truncated=response.result_truncated in {"true", True},
            observed_at=observed_at,
            total_records=response.total_records,
        )

    def close(self) -> None:
        self.client.close()
        if self.owns_credential:
            self.credential.close()

    def __enter__(self) -> AzureSdkInventoryReader:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _required_text(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InventoryReadError("invalid-response", missing_fields=(field,))
    return value


def _pool_inventory(pool: dict[str, Any], cluster_id: str) -> AzureNodePoolInventory:
    name = pool.get("name")
    if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9]{0,11}", name) is None:
        raise InventoryReadError("invalid-response")
    priority = pool.get("scaleSetPriority")
    return AzureNodePoolInventory(
        resource_id=f"{cluster_id}/agentPools/{name}",
        name=name,
        vm_size=_required_text(pool, "vmSize"),
        mode=pool.get("mode"),
        node_count=pool.get("count"),
        min_count=pool.get("minCount"),
        max_count=pool.get("maxCount"),
        autoscaling_enabled=pool.get("enableAutoScaling"),
        spot=True if priority == "Spot" else False if priority == "Regular" else None,
        zones=pool.get("availabilityZones"),
        os_type=pool.get("osType"),
    )


def _cluster_inventory(row: dict[str, Any], subscription_id: str) -> AzureClusterInventory:
    target = ClusterTarget(resource_id=_required_text(row, "id"))
    if (
        target.subscription_id != UUID(subscription_id)
        or row.get("subscriptionId") != subscription_id
    ):
        raise InventoryReadError("identity-mismatch")
    segments = target.resource_id.split("/")
    if row.get("name") != segments[-1] or row.get("resourceGroup") != segments[4]:
        raise InventoryReadError("identity-mismatch")
    pools = row.get("agentPoolProfiles")
    if not isinstance(pools, list) or not all(isinstance(pool, dict) for pool in pools):
        raise InventoryReadError("invalid-response", missing_fields=("agentPoolProfiles",))
    normalized_pools = [_pool_inventory(pool, target.resource_id) for pool in pools]
    identities = {pool.resource_id.casefold() for pool in normalized_pools}
    if len(identities) != len(normalized_pools):
        raise InventoryReadError("identity-mismatch")
    return AzureClusterInventory(
        resource_id=target.resource_id,
        name=_required_text(row, "name"),
        subscription_id=subscription_id,
        resource_group=_required_text(row, "resourceGroup"),
        location=_required_text(row, "location"),
        kubernetes_version=row.get("kubernetesVersion"),
        sku_tier=row.get("skuTier"),
        node_provisioning_mode=row.get("nodeProvisioningMode"),
        cost_analysis_enabled=row.get("costAnalysisEnabled"),
        managed_prometheus_enabled=row.get("managedPrometheusEnabled"),
        keda_enabled=row.get("kedaEnabled"),
        vpa_enabled=row.get("vpaEnabled"),
        tags=row.get("tags") or {},
        node_pools=normalized_pools,
    )


class AzureResourceGraphCollector:
    """Collect a metadata-only inventory fragment through an explicit read-only reader."""

    def __init__(
        self,
        profile: OnboardingConfig,
        *,
        reader: InventoryReader,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        max_pages: int = 100,
        page_size: int = 1000,
    ) -> None:
        if reader.tenant_id != str(profile.scope.tenant_id):
            raise ValueError("reader tenant does not match the approved tenant")
        if not 0 <= max_retries <= 10 or not 1 <= max_pages <= 10000 or not 1 <= page_size <= 1000:
            raise ValueError("invalid inventory retry, page, or result-size bound")
        self.profile = profile
        self.reader = reader
        self.clock = clock
        self.sleep = sleep
        self.max_retries = max_retries
        self.max_pages = max_pages
        self.page_size = page_size

    def collect(self) -> AzureInventorySnapshot:
        started = self.clock()
        if started.tzinfo is None or started.utcoffset() is None:
            raise ValueError("inventory clock must be timezone-aware")
        requested = sorted(str(value) for value in self.profile.scope.subscription_ids)
        targets = {target.resource_id for target in self.profile.clusters}
        completed: list[str] = []
        errors: list[CollectionError] = []
        clusters: dict[str, AzureClusterInventory] = {}
        links: dict[str, set[str]] = {}
        observations: list[datetime | None] = []
        missing_fields: list[str] = []
        retries = 0
        for subscription_id in requested:
            query = inventory_query(targets)
            skip_token = None
            seen_tokens: set[str] = set()
            seen_ids: set[str] = set()
            expected_total: int | None = None
            observed_rows = 0
            try:
                for page_number in range(self.max_pages):
                    for attempt in range(self.max_retries + 1):
                        try:
                            page = self.reader.query(
                                subscription_id=subscription_id,
                                query=query,
                                skip_token=skip_token,
                                page_size=self.page_size,
                            )
                            break
                        except InventoryReadError as error:
                            if (
                                error.code not in {"throttled", "timeout", "unavailable"}
                                or attempt == self.max_retries
                            ):
                                raise
                            delay = error.retry_after_seconds
                            self.sleep(min(30, max(0, delay if delay is not None else 2**attempt)))
                            retries += 1
                    if (
                        not isinstance(page.rows, list)
                        or len(page.rows) > self.page_size
                        or not all(isinstance(row, dict) for row in page.rows)
                    ):
                        raise InventoryReadError("invalid-response")
                    if page.observed_at is not None and (
                        page.observed_at.tzinfo is None
                        or page.observed_at.utcoffset() is None
                        or page.observed_at > self.clock()
                    ):
                        raise InventoryReadError("invalid-response")
                    if page.total_records is not None:
                        if page.total_records < 0 or (
                            expected_total is not None and expected_total != page.total_records
                        ):
                            raise InventoryReadError("invalid-response")
                        expected_total = page.total_records
                    observed_rows += len(page.rows)
                    if expected_total is not None and observed_rows > expected_total:
                        raise InventoryReadError("invalid-response")
                    observations.append(page.observed_at)
                    for row in page.rows:
                        resource_id = row.get("id")
                        if not isinstance(resource_id, str) or resource_id.casefold() in seen_ids:
                            raise InventoryReadError("identity-mismatch")
                        seen_ids.add(resource_id.casefold())
                        resource_type = row.get("type")
                        if not isinstance(resource_type, str):
                            raise InventoryReadError("invalid-response")
                        if resource_type.casefold() == CLUSTER_TYPE:
                            if targets and resource_id not in targets:
                                raise InventoryReadError("identity-mismatch")
                            cluster = _cluster_inventory(row, subscription_id)
                            clusters[resource_id] = cluster
                        elif resource_type.casefold() == MEMBER_TYPE:
                            target = ClusterTarget(
                                resource_id=_required_text(row, "clusterResourceId")
                            )
                            if target.subscription_id not in self.profile.scope.subscription_ids:
                                continue
                            if targets and target.resource_id not in targets:
                                raise InventoryReadError("identity-mismatch")
                            match = re.fullmatch(
                                rf"/subscriptions/{re.escape(subscription_id)}/resourceGroups/[^/]+/providers/"
                                r"Microsoft.ContainerService/fleets/[^/]+/members/[^/]+",
                                resource_id,
                                flags=re.IGNORECASE,
                            )
                            if match is None or row.get("subscriptionId") != subscription_id:
                                raise InventoryReadError("identity-mismatch")
                            fleet_id = re.split(r"/members/", resource_id, flags=re.IGNORECASE)[0]
                            links.setdefault(target.resource_id, set()).add(fleet_id)
                        else:
                            raise InventoryReadError("invalid-response")
                    if page.skip_token is None:
                        if page.truncated or (
                            expected_total is not None and observed_rows != expected_total
                        ):
                            raise InventoryReadError("invalid-response")
                        break
                    if not page.skip_token or page.skip_token in seen_tokens:
                        raise InventoryReadError("invalid-response")
                    seen_tokens.add(page.skip_token)
                    skip_token = page.skip_token
                    if page_number == self.max_pages - 1:
                        raise InventoryReadError("invalid-response")
                expected = {
                    target
                    for target in targets
                    if ClusterTarget(resource_id=target).subscription_id == UUID(subscription_id)
                }
                if not expected <= clusters.keys():
                    raise InventoryReadError("invalid-response")
                completed.append(subscription_id)
            except InventoryReadError as error:
                errors.append(CollectionError(scope=subscription_id, code=error.code))
                missing_fields.extend(
                    f"{subscription_id}:{field}" for field in error.missing_fields
                )
            except (ValidationError, TypeError, KeyError) as error:
                del error
                errors.append(CollectionError(scope=subscription_id, code="invalid-response"))
        ended = self.clock()
        if ended.tzinfo is None or ended.utcoffset() is None or ended < started:
            raise ValueError("inventory completion clock is invalid")
        for resource_id, cluster in clusters.items():
            if resource_id in links:
                cluster.fleet_ids = sorted(links[resource_id])
        status = (
            CollectionStatus.COMPLETE
            if not errors
            else CollectionStatus.PARTIAL
            if completed or clusters
            else CollectionStatus.FAILED
        )
        observed_at = None
        if observations and all(value is not None for value in observations):
            observed_at = min(value for value in observations if value is not None)
        result = CollectorResult(
            collector="azure-inventory",
            status=status,
            requested_scope=requested,
            completed_scope=completed,
            started_at=started,
            completed_at=ended,
            source_observed_at=observed_at,
            pagination_complete=not errors,
            retry_count=retries,
            errors=errors,
            missing_fields=sorted(set(missing_fields)),
        )
        return AzureInventorySnapshot(
            tenant_id=str(self.profile.scope.tenant_id),
            generated_at=ended,
            collection=result,
            clusters=sorted(clusters.values(), key=lambda cluster: cluster.resource_id),
        )
