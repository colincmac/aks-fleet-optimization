import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import findingSchema from '../../../../schemas/analysis-report.schema.json';
import catalogSchema from '../../../../schemas/operator-catalog.schema.json';
import inspectionSchema from '../../../../schemas/operator-inspection.schema.json';
import type { CatalogOperatorCatalog as OperatorCatalog } from '../models/operator-catalog.generated';
import type { InspectionOperatorInspection as OperatorInspection } from '../models/operator-inspection.generated';
import reviewSchema from '../models/review.schema.json';
import vpaSchema from '../models/vpa.schema.json';
import type { OptimizationRecommendation, VpaRecord } from '../models/review';

const ajv = new Ajv({ strict: false, allErrors: false });
addFormats(ajv);
const validateReview = ajv.compile(reviewSchema);
const validateVpa = ajv.compile(vpaSchema);
const validateFinding = ajv.compile({ $defs: findingSchema.$defs, $ref: '#/$defs/Recommendation' });
const validateCatalog = ajv.compile<OperatorCatalog>(catalogSchema);
const validateInspection = ajv.compile<OperatorInspection>(inspectionSchema);

export function parseOperatorCatalog(data: unknown): OperatorCatalog {
  if (!validateCatalog(data)) throw new Error('Unsupported or incomplete operator catalog.');
  return data;
}

export function parseOperatorInspection(data: unknown): OperatorInspection {
  if (!validateInspection(data)) throw new Error('Unsupported or incomplete pack inspection.');
  return data;
}

export function parseRecommendation(data: unknown): OptimizationRecommendation {
  if (!validateReview(data))
    throw new Error(
      'Unsupported or incomplete recommendation record. The governance publisher must supply observed status and the current review contract.'
    );
  const record = data as OptimizationRecommendation;
  if (!validateFinding(record.spec.finding))
    throw new Error('Recommendation finding does not match the advisor schema 1.0.');
  if (
    record.spec.finding.resource_id !== record.spec.target.clusterResourceId ||
    record.spec.finding.namespace !== record.spec.target.namespace ||
    record.spec.finding.workload !== record.spec.target.name
  )
    throw new Error('Finding and governed target identities do not match.');
  const inspection = record.spec.inspection;
  if (inspection) {
    if (
      !validateInspection(inspection) ||
      inspection.card.manifest.id !== record.spec.finding.rule_id ||
      inspection.card.manifest.version !== record.spec.finding.rule_version ||
      inspection.card.provenance.id !== inspection.card.manifest.id ||
      inspection.card.provenance.version !== inspection.card.manifest.version ||
      inspection.capabilities.some(
        (item) =>
          item.pack_id !== record.spec.finding.rule_id ||
          item.mode !== inspection.mode ||
          item.cluster_resource_id !== record.spec.target.clusterResourceId ||
          item.status !==
            (['unsupported', 'unavailable', 'unknown'].find((status) =>
              item.checks.some((check) => check.status === status)
            ) ?? 'available')
      )
    )
      throw new Error('Pack inspection does not match finding version, mode or exact scope.');
    if (
      inspection.mode === 'baseline' &&
      (record.spec.finding.proposed_requests != null ||
        record.spec.finding.proposed_limits != null ||
        record.spec.finding.proposed_replica_floor != null)
    )
      throw new Error('Baseline inspection cannot contain numeric proposals.');
  }
  return record;
}
export function parseVpa(data: unknown): VpaRecord {
  if (!validateVpa(data))
    throw new Error('Unsupported VPA record. Embedded recommendation evidence remains available.');
  return data as VpaRecord;
}

export function parseRecommendationList(
  items: unknown[],
  namespace: string
): OptimizationRecommendation[] {
  const records = items.map(parseRecommendation);
  const names = new Set<string>();
  const uids = new Set<string>();
  for (const record of records) {
    if (record.metadata.namespace !== namespace)
      throw new Error('Recommendation returned outside the configured review namespace.');
    if (names.has(record.metadata.name) || uids.has(record.metadata.uid))
      throw new Error('Duplicate recommendation identity in Kubernetes list.');
    names.add(record.metadata.name);
    uids.add(record.metadata.uid);
  }
  return records;
}
