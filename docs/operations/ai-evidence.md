# Optional AI Summary Handoff

[Documentation home](../README.md) | [Saved artifact comparison](history.md) | [Security and privacy](../security-and-privacy.md)

Use this offline preview to prepare pseudonymous deterministic finding summaries for a separately approved AI explanation workflow. It exports only rule/version, finding-or-blocked state, original severity/confidence and opaque blocker digests. It does not call a model, provide write tools, approve changes or draft executable configuration.

The default summary contract is intentionally summary-only. Raw measurements, evidence values, titles/summaries, resource and Namespace names, UIDs, owner/contact text, source references, paths, metadata bodies, proposed values, actions and cost observations are withheld. Blocker digests preserve identity but do not reveal the original reason text. The summary package cannot explain metric causes or establish healthy workloads, source authenticity, safe settings or savings. The separate measurement opt-in below does not change this default. Keep the original protected reports for human review.

## Export A Package

From the repository root after installation/activation, create a fresh fictional artifact directory. This saved example exits `3` because its evidence is partial; that does not prevent summary export:

```powershell
aks-fleet-advisor assess --fragments examples/fixtures/history-assessment.json --config examples/pool-assessment-config.yaml --as-of 2026-10-29T12:00:00Z --format json --artifacts .local/ai-example
aks-fleet-advisor ai export --assessment .local/ai-example/assessment.json --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T12:00:00Z --allow-ai-export --output .local/ai-summary.json
```

The export exits `0` and writes [ai-evidence-package.schema.json](../../schemas/ai-evidence-package.schema.json). Input/output paths must be new where required; an existing output is never overwritten. `--allow-ai-export` is required before source artifact reads and authorizes local summary-file creation only. It is not permission to upload the file, use an AI provider, broaden collection or change a cluster. Obtain separate customer approval for any external audience or model.

Repeat `--assessment` for up to 16 original one-cluster bundles sharing the explicitly supplied tenant. Each needs the original manifest, fragments, snapshot, locked configuration, assessment and report files. Exact tenant/input/snapshot/configuration integrity and deterministic replay are validated before export. Missing fingerprints, edited or consistently rehashed findings, duplicate runs, foreign tenants, invalid clocks and excess budgets fail closed; no history store or input copies are created.

Scope, resource and record digests are pseudonyms, not anonymization or encryption. Dictionary guessing and correlation remain possible; rule/state/timing patterns can disclose environment details. Store packages and drafts under approved access, encryption, residency, retention and audience controls. Hashes establish consistency, not authenticity or authorization.

## Separately Opt In To Resource Measurements

Default `ai export --allow-ai-export` remains summary-only. A second explicit `--allow-ai-measurements` flag selects the separate [resource evidence package](../../schemas/ai-resource-evidence-package.schema.json), containing the unchanged summary plus at most 512 closed measurement records. Both consent flags are required. This permits local file creation only, not provider disclosure, source access, additional collection or change approval.

Using the original fictional bundle above and a fresh output path:

```text
aks-fleet-advisor ai export --assessment .local/ai-example/assessment.json --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T12:00:00Z --allow-ai-export --allow-ai-measurements --output .local/ai-resource-evidence.json
```

The exact allowlist is CPU request and CPU P95 usage in mCPU, plus memory request and memory P99 working-set usage in MiB. Current implementation admits only exactly bound Pod/container observations, not name-only telemetry, multi-Pod totals or replica-envelope reinterpretations. Each record is `observed` with its original value and quality, or `withheld` with null value and closed machine reason codes. The fictional imported bundle intentionally lacks execution provenance, so its values remain withheld even where the ordinary report contains numerical summaries. Missing or unsupported evidence is not replaced with zero, a current request, a whole-window substitute or a proposed safe value.

Observed records require original locked replay, matching Namespace/Pod/workload/container identities, a supported original source profile, the installed query expression rendered with the characterized label mapping, matching asset and adapter versions, an executed complete scoped receipt, original window/step/sample/coverage/clocks and sample-tail checks, and equality with the original normalized statistic. Requests additionally require constant original extrema. Unrecorded custom label mappings are withheld rather than inferred. Partial, stale, low-coverage, ambiguous or differently bound evidence cannot become an observed value. Independent dimensions can remain observed beside withheld records.

Quality retains explicit `qualified_at` at the original assessment time, source/metric/sample clocks, UTC window, step seconds, sample count, coverage, query/adapter versions and opaque source/profile/query/receipt/observation bindings. Export does not refresh or requalify source quality at the export clock. Package lifetime retains the summary's existing bounds; it does not attest current metric freshness. Names, raw UIDs/resource IDs, owner/SLO/report prose, arbitrary metadata, financial evidence, raw expressions/source references, proposal values and executable fields are excluded. Digests remain correlatable protected data, not anonymization or source authenticity.

SDK `export_ai_measurements` creates the package; `validate_ai_measurements` revalidates the closed shape, expiry and byte budget and regenerates the exact package from original bundles. Schema validation or consistent copied hashes alone are not admission. Existing explanation/checklist validators continue to accept their original summary package, not the richer wrapper. Broader measurement-backed drafting, policy values and provider use require separate contracts and approval; no model is invoked here.

## Validate An Explanation Draft

A separately approved producer can return [ai-explanation-draft.schema.json](../../schemas/ai-explanation-draft.schema.json): the exact package digest and clocks, declared provider/model/revision provenance, and claims containing an unchanged summary fact, its record/digest citation and free-form interpretation. Provider metadata is a declaration, not proof a model ran. Do not put credentials, raw telemetry, executable configuration, tool calls, metric values or resource proposals into the draft.

Validate the retained draft against the original artifact bundles and package:

```powershell
aks-fleet-advisor ai validate-explanation --assessment .local/ai-example/assessment.json --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T12:00:00Z --package .local/ai-summary.json --draft .local/ai-draft.json
```

The draft must already exist in approved storage. The shared verifier generates a labelled synthetic draft to test this handoff without a model. The CLI regenerates the entire package from verified original artifacts at its export clock before checking the draft at the supplied current clock. Editing a package and resealing its digests cannot change the admitted facts. Wrong/missing/substituted citations, changed structured facts, duplicate citations, unsupported fields and future/expired lifetimes are rejected with exit `2`; errors omit input values.

A valid draft exits `0` and prints [ai-explanation.schema.json](../../schemas/ai-explanation.schema.json) with the only possible state, `unverified_interpretation`. Copied structured facts and citations match the package; free-form prose is not semantically proven by that check. It can still contain false claims or malicious instructions. Treat all interpretation as inert, unapproved text, never executable markup, commands, approval or a replacement for deterministic report fields. Human review and separate adversarial model evaluation remain required.

## Clocks And Bounds

Exports require an explicit aware UTC evaluation time. `--ttl-seconds` is 60..3600, default 3600; package expiry is capped by every original report's configured maximum evidence age. Report evaluation/window/status are retained independently. Export time never refreshes underlying inventory or metric quality, and a current report can still contain explicit blocked/stale-source findings. For fictional replay, use the shown historical clock; never use it to qualify stale customer data as current.

Admission requires package generation at or before the current clock, current time strictly before expiry, and draft generation/expiry within the package lifetime. Expiry equality is rejected. Input bounds are 32 MiB per original artifact bundle, 128 MiB combined input payload, 16 bundles, 128 summary records, 256 KiB for the formatted package including its newline, and 64 KiB for a draft. Budget excess fails rather than truncating findings. Links/junctions are rejected. An empty summary record list does not mean healthy or resolved; a draft still needs an actual cited record.

## Validate A Non-Executable Checklist

Use the separate checklist contract when a producer proposes which human reviews to perform next. The existing summary export stays unchanged: no additional measurements, controller bodies, owner prose or financial data are released. A checklist cannot establish measurement causes, encode a scaling policy or prescribe safe values from summary records.

First prepare a caller-controlled [review intent](../../schemas/ai-review-intent.schema.json) containing the exact canonical package digest, one admitted assessment scope ID and an objective: `investigate-resource-settings`, `investigate-controller-interactions` or `review-missing-evidence`. SDK callers compute the digest with `content_digest`; filenames and display names are not scope bindings. This intent is a declaration, not authentication or change approval.

A producer's [checklist draft](../../schemas/ai-checklist-draft.schema.json) contains the intent digest, a normal copied-fact explanation draft and 3..32 closed steps. Step kinds are `confirm_scope`, `inspect_source_gaps`, `review_controller_interactions`, `define_test_and_abort_criteria`, `verify_rollback_prerequisites` and `retain_no_change_option`. Test/abort, rollback and no-change review steps are mandatory. Every step cites an unchanged selected fact; duplicates, foreign/substituted citations, cross-scope facts, changed intent and extra fields are rejected. There are no step command, script, patch, target-value, approval or application fields. Step names request review; they do not supply test thresholds or a verified rollback plan.

With an existing package, intent and checklist draft in protected storage, validate against the original bundles:

```text
aks-fleet-advisor ai validate-checklist --assessment .local/ai-example/assessment.json --tenant 00000000-0000-0000-0000-000000000000 --as-of 2026-10-29T12:00:00Z --package .local/ai-summary.json --intent .local/ai-intent.json --draft .local/ai-checklist-draft.json
```

The command regenerates the package from verified originals and reuses the explanation fact/citation/clock gates. Intent files are bounded to 4 KiB and entire checklist drafts to 64 KiB; the nested explanation remains within the same package lifetime. Invalid inputs exit `2` with redacted errors. Success exits `0` and returns [ai-checklist.schema.json](../../schemas/ai-checklist.schema.json) with state `unverified_checklist`. Neither success nor the required step names prove plan feasibility, source authenticity, semantic truth, independent review, approval or execution. Free-form interpretation stays inert and may still be false or malicious.

The shared source/installed-wheel verifier constructs a labelled synthetic checklist; it invokes no model. The separately consented measurement export above does not expand checklist fields. Actual policy values and provider-backed evaluation remain separate pending work. The original detached workload-context hypothesis/check contract remains unchanged.

## Remaining Preview Boundaries

The existing detached workload-context advisory/hypothesis contract remains separate and unchanged. These commands do not automatically export its owner objectives, HPA/VPA/request facts or experiment plans, and no provider SDK, identity acquisition, endpoint, agent tool or automatic application path is supplied.

Provider/model/tool selection, customer data-release approval and adversarial faithfulness evaluation are required before model-backed acceptance. Evidence beyond the four opted-in measurements, controller/owner data and original blocker prose needs separately reviewed allowlists and identity/clock semantics. Financial context and prior evidence/runtime blockers are not bypassed by this preview.

### Local Copilot Reviewer

The repository supplies [Fleet Evidence Reviewer](../../.github/agents/fleet-evidence-reviewer.agent.md) as an optional workspace Copilot agent pinned to `GPT-6.1 Sol (copilot)`, without tools, filesystem access or subagents. Invoke it only with an explicitly approved summary package, selected exact facts/citation digests, response schema, generation/expiry clocks and declared provenance. Use the space-free declared model reference `gpt-6.1-sol` in draft provenance; the agent picker display name is not a valid provenance identifier. No fallback model is configured. An unavailable model must be reported, not silently replaced.

The agent returns a JSON draft for the existing deterministic validator; it does not read original assessments or admit its own response. The parent must use `ai validate-explanation` or `ai validate-experiment` against protected originals, and a human must separately assess faithfulness. Missing required input produces a JSON refusal, not an admitted draft. Keep actual customer data out of evaluation by default: the initial rehearsal uses synthetic pseudonymous summaries only, not the supplied demo-cluster data or Monitoring Reader token. The CLI still makes no model calls. Azure Foundry support remains a separate future provider choice, not a credential or deployment prerequisite for the local Copilot workflow.

## Non-Executable Experiment Review

After exporting a summary package, prepare an `AIExperimentIntent` that binds its digest and one admitted `scope_id`, the existing review objective, one resource dimension (`cpu_request`, `memory_request`, `memory_limit`, `replica_floor`, `controller_configuration` or `evidence_only`) and a controller category (`none`, `hpa`, `vpa`, `keda`, `nap` or `fixed`). These are caller-selected review boundaries, not values chosen by a model or evidence that a controller exists. The existing detached advisory contract and default summaries are unchanged.

An `AIExperimentDraft` contains that intent digest, the same dimension/controller, an ordinary cited explanation, an untrusted hypothesis, closed alternatives including retaining the current configuration, closed unresolved prerequisites and cited baseline/canary/observe/abort/rollback/no-change checks. Every selected explanation fact must be cited by a check, and every check must cite an exact selected fact. The validator regenerates the summary package from original replay-verified artifacts; altered originals, foreign facts, changed intent, missing stages, duplicate checks, future/expired evidence and excess bytes are rejected.

```text
aks-fleet-advisor ai validate-experiment --assessment approved-artifacts/assessment.json --tenant <tenant-id> --as-of <utc-time> --package summary.json --intent experiment-intent.json --draft experiment-draft.json
```

The centrally generated [intent](../../schemas/ai-experiment-intent.schema.json), [draft](../../schemas/ai-experiment-draft.schema.json) and [result](../../schemas/ai-experiment.schema.json) schemas define the closed fields. The only accepted state is `unverified_experiment`, with `execution_authority` fixed to `none`. There are no command, script, YAML, patch, numeric-target, approval or application fields. Structurally valid prose can still be false, malicious or contain instructions: treat it as inert unverified text and never execute it. The checks do not establish that a canary, SLO threshold, rollback or safe value is valid. Separate owners must define and approve those details through existing delivery tools. This command calls no model and does not permit provider disclosure, including disclosure of the separately consented measurement package.
