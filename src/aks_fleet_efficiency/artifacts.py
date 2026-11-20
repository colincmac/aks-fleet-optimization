from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel

from aks_fleet_efficiency.assessment import AssessmentFragments, OfflineAssessment
from aks_fleet_efficiency.config import AdvisorConfig
from aks_fleet_efficiency.reporting.markdown import render_assessment_markdown

MAXIMUM_INPUT_BYTES = 32 * 1024 * 1024


def read_model[Model: BaseModel](
    path: Path, model: type[Model], *, maximum_bytes: int = MAXIMUM_INPUT_BYTES
) -> Model:
    with path.open("rb") as handle:
        payload = handle.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise ValueError("input exceeds the configured byte limit")
    return model.model_validate_json(payload)


def write_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip("\n") + "\n")


def write_assessment_artifacts(
    directory: Path,
    fragments: AssessmentFragments,
    assessment: OfflineAssessment,
    config: AdvisorConfig,
) -> None:
    directory.mkdir(exist_ok=False)
    locked_config = AdvisorConfig.model_validate(
        config.model_dump()
        | {"pack_locks": {item.id: item.digest for item in assessment.report.pack_provenance}}
    )
    content = {
        "fragments.json": fragments.model_dump_json(indent=2),
        "snapshot.json": assessment.snapshot.model_dump_json(indent=2),
        "analysis-config.json": locked_config.model_dump_json(indent=2),
        "assessment.json": assessment.model_dump_json(indent=2),
        "report.md": render_assessment_markdown(assessment),
    }
    digests = {}
    for name, text in content.items():
        encoded = text.rstrip("\n") + "\n"
        write_exclusive(directory / name, encoded)
        digests[name] = sha256(encoded.encode()).hexdigest()
    write_exclusive(
        directory / "manifest.json",
        json.dumps(
            {
                "schema_version": "1.0",
                "status": assessment.status,
                "input_digest": assessment.input_digest,
                "files": digests,
            },
            indent=2,
            sort_keys=True,
        ),
    )
