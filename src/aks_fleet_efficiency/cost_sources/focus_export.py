from __future__ import annotations

import csv
from decimal import Decimal, localcontext
from hashlib import sha256
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aks_fleet_efficiency.artifacts import MAXIMUM_INPUT_BYTES, read_model
from aks_fleet_efficiency.cost import (
    CostExportFile,
    CostExportProvenance,
    CostImport,
    CostPeriod,
    CostResourceBinding,
    Currency,
    Money,
    Text,
)
from aks_fleet_efficiency.cost_sources.base import ProjectionModel
from aks_fleet_efficiency.cost_sources.focus import FocusProjection, FocusRow, project_focus
from aks_fleet_efficiency.models import UtcDatetime

FOCUS_COLUMNS = {
    "SubAccountId": "sub_account_id",
    "ResourceId": "resource_id",
    "ChargePeriodStart": "charge_period_start",
    "ChargePeriodEnd": "charge_period_end",
    "EffectiveCost": "effective_cost",
    "BillingCurrency": "billing_currency",
    "ServiceCategory": "service_category",
    "ChargeCategory": "charge_category",
    "PricingCategory": "pricing_category",
    "ChargeClass": "charge_class",
    "CommitmentDiscountCategory": "commitment_discount_category",
    "CommitmentDiscountId": "commitment_discount_id",
    "CommitmentDiscountStatus": "commitment_discount_status",
    "CommitmentDiscountType": "commitment_discount_type",
}


class FocusExportReview(ProjectionModel):
    tenant_id: UUID
    subscription_ids: list[UUID] = Field(min_length=1, max_length=1000)
    period: CostPeriod
    source_reference: Text
    source_observed_at: UtcDatetime
    expected_totals: dict[Currency, Money] = Field(min_length=1, max_length=100)
    bindings: list[CostResourceBinding] = Field(default_factory=list, max_length=100_000)


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True, frozen=True)


class _ExportConfig(_ManifestModel):
    data_version: Literal["1.2-preview"] = Field(alias="dataVersion")
    type: Literal["FocusCost"]


class _DeliveryConfig(_ManifestModel):
    file_format: Literal["Csv"] = Field(alias="fileFormat")
    compression_mode: Literal["None"] = Field(alias="compressionMode")


class _Blob(_ManifestModel):
    blob_name: Text = Field(alias="blobName")
    byte_count: int = Field(alias="byteCount", ge=0, strict=True)
    row_count: int = Field(alias="dataRowCount", ge=0, le=100_000, strict=True)


class _RunInfo(_ManifestModel):
    run_id: Text = Field(alias="runId")


class _Manifest(_ManifestModel):
    manifest_version: Literal["2024-04-01"] = Field(alias="manifestVersion")
    byte_count: int = Field(alias="byteCount", ge=0, le=MAXIMUM_INPUT_BYTES, strict=True)
    blob_count: int = Field(alias="blobCount", ge=1, le=100, strict=True)
    row_count: int = Field(alias="dataRowCount", ge=0, le=100_000, strict=True)
    export_config: _ExportConfig = Field(alias="exportConfig")
    delivery_config: _DeliveryConfig = Field(alias="deliveryConfig")
    run_info: _RunInfo = Field(alias="runInfo")
    blobs: list[_Blob] = Field(min_length=1, max_length=100)


def _read_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(MAXIMUM_INPUT_BYTES + 1)
    if len(data) > MAXIMUM_INPUT_BYTES:
        raise ValueError("FOCUS input exceeds the byte limit")
    return data


def _read_part(path: Path, blob: _Blob) -> tuple[list[FocusRow], CostExportFile]:
    data = _read_bytes(path)
    if len(data) != blob.byte_count:
        raise ValueError("FOCUS partition byte count does not match the manifest")
    digest = sha256(data).hexdigest()
    partition = sha256(blob.blob_name.encode()).hexdigest()
    reader = csv.reader(StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    header = next(reader, [])
    if (
        len(header) > 256
        or len({name.casefold() for name in header}) != len(header)
        or not FOCUS_COLUMNS.keys() <= set(header)
    ):
        raise ValueError("FOCUS columns are missing or ambiguous")
    selected = {field: header.index(column) for column, field in FOCUS_COLUMNS.items()}
    rows = []
    for ordinal, values in enumerate(reader, start=1):
        if (
            ordinal > blob.row_count
            or len(values) != len(header)
            or any(len(value) > 65536 or "\0" in value for value in values)
        ):
            raise ValueError("FOCUS record exceeds the supported shape or bounds")
        rows.append(
            FocusRow.model_validate(
                {field: values[index] or None for field, index in selected.items()}
                | {"charge_id": f"sha256:{partition}:{digest}:{ordinal}"}
            )
        )
    if len(rows) != blob.row_count:
        raise ValueError("FOCUS partition row count does not match the manifest")
    return rows, CostExportFile(
        partition_sha256=partition, sha256=digest, byte_count=len(data), row_count=len(rows)
    )


def convert_focus_export(manifest: Path, parts: list[Path], review: Path) -> CostImport:
    """Convert explicit local parts only; manifest paths and references are never followed."""
    try:
        manifest_bytes = _read_bytes(manifest)
        source = _Manifest.model_validate_json(manifest_bytes)
        controls = read_model(review, FocusExportReview)
        by_name = {part.name: part for part in parts}
        blobs = {PurePosixPath(blob.blob_name).name: blob for blob in source.blobs}
        if (
            len(parts) != len(by_name)
            or len({part.resolve() for part in parts}) != len(parts)
            or len(blobs) != len(source.blobs)
            or source.blob_count != len(blobs)
            or set(by_name) != set(blobs)
            or sum(blob.byte_count for blob in source.blobs) != source.byte_count
            or sum(blob.row_count for blob in source.blobs) != source.row_count
        ):
            raise ValueError("FOCUS requires all distinct manifest partitions and matching counts")
        rows: list[FocusRow] = []
        files: list[CostExportFile] = []
        for name in sorted(blobs):
            partition, receipt = _read_part(by_name[name], blobs[name])
            rows.extend(partition)
            files.append(receipt)
        totals: dict[str, Decimal] = {}
        with localcontext() as context:
            context.prec = 50
            for row in rows:
                totals[row.billing_currency] = (
                    totals.get(row.billing_currency, Decimal(0)) + row.effective_cost
                )
        if totals != controls.expected_totals:
            raise ValueError("FOCUS effective-cost totals do not match the independent review")
        projection = FocusProjection(
            schema_version="finops-focus-projection-v1",
            producer_version=source.export_config.data_version,
            tenant_id=controls.tenant_id,
            subscription_ids=controls.subscription_ids,
            period=controls.period,
            source_reference=controls.source_reference,
            source_observed_at=controls.source_observed_at,
            export_complete=True,
            rows=rows,
            bindings=controls.bindings,
        )
        ledger = project_focus("finops-focus", projection.model_dump())
        provenance = CostExportProvenance(
            manifest_sha256=sha256(manifest_bytes).hexdigest(),
            run_id_sha256=sha256(source.run_info.run_id.encode()).hexdigest(),
            files=files,
            effective_cost_totals=totals,
        )
        return CostImport.model_validate(ledger.model_dump() | {"export_provenance": provenance})
    except OSError, ValueError, csv.Error:
        raise ValueError(
            "Invalid or unsupported FOCUS export, partitions, or review controls; "
            "financial input and local paths are not echoed."
        ) from None
