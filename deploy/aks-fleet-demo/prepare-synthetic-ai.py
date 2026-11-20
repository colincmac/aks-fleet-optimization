"""Create inert demo drafts from the synthetic summary exported in the runbook."""

import argparse
from pathlib import Path

from pydantic import BaseModel

from aks_fleet_efficiency.advisory import (
    AdvisoryProvenance,
    AIChecklistDraft,
    AIChecklistStep,
    AIEvidencePackage,
    AIExperimentCheck,
    AIExperimentDraft,
    AIExperimentIntent,
    AIExplanationClaim,
    AIExplanationDraft,
    AIReviewIntent,
    EvidenceCitation,
    content_digest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("draft_directory", type=Path)
    args = parser.parse_args()
    with args.package.open("rb") as package_file:
        raw = package_file.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        parser.error("The summary exceeds the advisor's 256 KiB package limit.")
    package = AIEvidencePackage.model_validate_json(raw)
    if not package.records:
        parser.error("Use the runbook's synthetic summary with at least one record.")

    record = package.records[0]
    citation = EvidenceCitation(record_id=record.record_id, record_digest=content_digest(record))
    revision = "0" * 64
    explanation = AIExplanationDraft(
        package_digest=content_digest(package),
        generated_at=package.generated_at,
        expires_at=package.expires_at,
        provenance=AdvisoryProvenance(
            provider="synthetic-not-invoked",
            model="synthetic-not-invoked",
            prompt_revision=revision,
            skill_revision=revision,
            tool_revision=revision,
        ),
        claims=(
            AIExplanationClaim(
                fact=record,
                citation=citation,
                interpretation=(
                    "Demo draft. Review the cited finding and missing evidence with its owner; "
                    "do not infer a cause or change a setting."
                ),
            ),
        ),
    )
    review = AIReviewIntent(
        package_digest=explanation.package_digest,
        scope_id=record.scope_id,
        objective="review-missing-evidence",
    )
    experiment = AIExperimentIntent(
        **review.model_dump(), dimension="evidence_only", controller="none"
    )
    drafts: dict[str, BaseModel] = {
        "explanation": explanation,
        "tampered-explanation": explanation.model_copy(update={"package_digest": "f" * 64}),
        "review-intent": review,
        "checklist": AIChecklistDraft(
            intent_digest=content_digest(review),
            explanation=explanation,
            steps=tuple(
                AIChecklistStep.model_validate({"kind": kind, "citation": citation})
                for kind in (
                    "define_test_and_abort_criteria",
                    "verify_rollback_prerequisites",
                    "retain_no_change_option",
                )
            ),
        ),
        "experiment-intent": experiment,
        "experiment": AIExperimentDraft(
            intent_digest=content_digest(experiment),
            dimension=experiment.dimension,
            controller=experiment.controller,
            explanation=explanation,
            hypothesis="Review missing evidence before considering any change.",
            alternatives=("retain_current_configuration", "collect_missing_evidence"),
            unresolved_prerequisites=("owner_review", "source_completeness"),
            checks=tuple(
                AIExperimentCheck.model_validate({"kind": kind, "citation": citation})
                for kind in ("baseline", "canary", "observe", "abort", "rollback", "no_change")
            ),
        ),
    }
    args.draft_directory.mkdir()
    for name, draft in drafts.items():
        with (args.draft_directory / f"{name}.json").open("x", encoding="utf-8") as output:
            output.write(draft.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
