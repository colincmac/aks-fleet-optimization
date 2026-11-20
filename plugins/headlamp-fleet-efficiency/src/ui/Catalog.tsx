import catalogData from '../../../../examples/operator-catalog.json';
import type { CatalogOperatorCard as OperatorCard } from '../models/operator-catalog.generated';
import type { OptimizationRecommendation } from '../models/review';
import { parseOperatorCatalog } from '../api/contracts';
import { Badge, Notice, Section } from './primitives';

const catalog = parseOperatorCatalog(catalogData);

function CardContent({ card }: { card: OperatorCard }) {
  const pack = card.manifest;
  return (
    <>
      <p>{pack.purpose}</p>
      <p>
        Pack version {pack.version} · {pack.evidence_kind} · {pack.family}
      </p>
      <p>Baseline: {pack.baseline_summary}</p>
      <p>Guarded: {pack.guarded_summary}</p>
      <details className="fe-disclosure">
        <summary>Parameters, limitations and owner prerequisites</summary>
        {Object.entries(card.parameter_guidance).map(([name, guidance]) => (
          <p key={name}>
            {name}: default {card.manifest.parameters.review_ratio} {guidance.unit};{' '}
            {guidance.bounds}. {guidance.implication}
          </p>
        ))}
        {!Object.keys(card.parameter_guidance).length && (
          <p>No ratio control; owner bounds are separate.</p>
        )}
        <h3>Limitations</h3>
        <ul>
          {pack.limitations.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
        <h3>Prerequisites</h3>
        <ul>
          {pack.prerequisites.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
        <h3>Validation and rollback</h3>
        <ul>
          {[...pack.validation, ...pack.rollback].map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
      </details>
      <details className="fe-disclosure">
        <summary>Query templates (not executable; export with approved source/scope)</summary>
        {!card.provenance.queries.length && <p>Inventory-only: no PromQL or metric endpoint.</p>}
        {card.provenance.queries.map((query) => (
          <div key={query.id}>
            <h3>
              {query.id} v{query.version} · {query.unit}
            </h3>
            <pre>{query.expression}</pre>
          </div>
        ))}
      </details>
      <details className="fe-disclosure">
        <summary>Pack/query digest and synthetic baseline example</summary>
        <pre>{card.provenance.digest}</pre>
        <pre>{JSON.stringify(card.synthetic_example, null, 2)}</pre>
        <p>Example selection only, not a healthy result or owner approval.</p>
      </details>
    </>
  );
}

export function OperatorCatalogPanel() {
  return (
    <>
      <h1>Recommendation catalog</h1>
      <Notice>{catalog.guarded_notice}</Notice>
      <p>
        Packaged catalog, not imported assessment evidence. No endpoint requests or UI calculations.
      </p>
      <details className="fe-disclosure">
        <summary>Glossary</summary>
        <dl>
          {Object.entries(catalog.glossary).map(([term, definition]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{definition}</dd>
            </div>
          ))}
        </dl>
      </details>
      {catalog.cards.map((card) => (
        <Section key={card.manifest.id} title={`${card.manifest.id}: ${card.manifest.title}`}>
          <CardContent card={card} />
        </Section>
      ))}
    </>
  );
}

export function PackInspectionPanel({ record }: { record: OptimizationRecommendation }) {
  const inspection = record.spec.inspection;
  return (
    <Section title="Pack, queries & capability gaps" label="ORIGINAL ASSESSMENT CONTRACT">
      {!inspection ? (
        <Notice>
          Pack inspection was not supplied. Original query/policy provenance is unknown; the
          packaged catalog is not a substitute.
        </Notice>
      ) : (
        <>
          <Badge>{inspection.mode}</Badge>
          <CardContent card={inspection.card} />
          <h3>Effective review parameters</h3>
          <pre>{JSON.stringify(inspection.card.provenance.parameters, null, 2)}</pre>
          <h3>Source capability gaps</h3>
          {!inspection.capabilities.length && (
            <Notice>No metric capability evidence supplied. Unknown is not healthy.</Notice>
          )}
          {inspection.capabilities.map((capability, index) => (
            <div key={index}>
              <p>
                {capability.source}: {capability.status} · profile {capability.source_profile.id} v
                {capability.source_profile.version}
              </p>
              <p>Observed: {capability.observed_at}</p>
              <ul>
                {capability.checks.map((check) => (
                  <li key={check.code}>
                    {check.code}: {check.status} · {check.reason_codes.join(', ')}
                  </li>
                ))}
              </ul>
              <p>{capability.notice}</p>
            </div>
          ))}
          <h3>Resolved source-bound queries</h3>
          {!inspection.resolved_queries?.length && (
            <p>Not supplied; templates above are not executable exports.</p>
          )}
          {inspection.resolved_queries?.map((query, index) => (
            <div key={index}>
              <p>
                {query.metric} v{query.version} · {query.source} · {query.step_seconds}s
              </p>
              <pre>{query.expression}</pre>
              <pre>{query.expression_digest}</pre>
            </div>
          ))}
          <Notice>
            Owner policy and configuration-bound checks are shown separately below. Mode and
            capability do not grant approval.
          </Notice>
        </>
      )}
    </Section>
  );
}
