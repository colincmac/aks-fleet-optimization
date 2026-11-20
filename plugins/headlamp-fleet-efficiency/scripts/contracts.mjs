import { createGenerator } from 'ts-json-schema-generator';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stringify } from 'yaml';
import { compileFromFile } from 'json-schema-to-typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
for (const name of ['operator-catalog', 'operator-inspection']) {
  const content = await compileFromFile(resolve(root, `../../schemas/${name}.schema.json`), {
    unreachableDefinitions: true,
    customName: (schema) =>
      schema.title
        ? `${name === 'operator-catalog' ? 'Catalog' : 'Inspection'}${schema.title}`
        : undefined,
  });
  const path = resolve(root, `src/models/${name}.generated.ts`);
  if (process.argv.includes('--check')) {
    if (readFileSync(path, 'utf8').replace(/\r\n/g, '\n') !== content)
      throw new Error(`Contract drift: ${name}`);
  } else {
    writeFileSync(path, content);
  }
}
const advisorTypesPath = resolve(root, 'src/models/advisor.generated.ts');
const advisorTypes = await compileFromFile(
  resolve(root, '../../schemas/analysis-report.schema.json'),
  { unreachableDefinitions: true }
);
if (process.argv.includes('--check')) {
  if (readFileSync(advisorTypesPath, 'utf8').replace(/\r\n/g, '\n') !== advisorTypes)
    throw new Error('Contract drift: src/models/advisor.generated.ts');
} else {
  writeFileSync(advisorTypesPath, advisorTypes);
}
const schema = createGenerator({
  path: resolve(root, 'src/models/review.ts'),
  tsconfig: resolve(root, 'tsconfig.json'),
  type: 'OptimizationRecommendation',
  skipTypeCheck: true,
  additionalProperties: false,
}).createSchema('OptimizationRecommendation');
const vpaSchema = createGenerator({
  path: resolve(root, 'src/models/review.ts'),
  tsconfig: resolve(root, 'tsconfig.json'),
  type: 'VpaRecord',
  skipTypeCheck: true,
  additionalProperties: true,
}).createSchema('VpaRecord');
function structural(node) {
  if (node.$ref) return structural(schema.definitions[node.$ref.replace('#/definitions/', '')]);
  if (node.anyOf) {
    const variants = node.anyOf.filter((item) => item.type !== 'null');
    if (variants.length === 1)
      return {
        ...structural(variants[0]),
        ...(variants.length < node.anyOf.length ? { nullable: true } : {}),
      };
    return { 'x-kubernetes-preserve-unknown-fields': true };
  }
  if (!node.type && !node.enum && !node.const)
    return { 'x-kubernetes-preserve-unknown-fields': true };
  const result = {};
  for (const [key, value] of Object.entries(node)) {
    if (
      [
        'type',
        'enum',
        'required',
        'minimum',
        'maximum',
        'minLength',
        'maxLength',
        'minItems',
        'maxItems',
      ].includes(key)
    )
      result[key] = value;
    if (key === 'const') {
      result.type = typeof value;
      result.enum = [value];
    }
    if (key === 'items') result.items = structural(value);
    if (key === 'properties')
      result.properties = Object.fromEntries(
        Object.entries(value).map(([name, child]) => [name, structural(child)])
      );
    if (key === 'additionalProperties' && typeof value === 'object') {
      if (Object.keys(value).length) result.additionalProperties = structural(value);
      else result['x-kubernetes-preserve-unknown-fields'] = true;
    }
  }
  return result;
}
const openAPI = structural(schema);
openAPI.properties.metadata = { type: 'object' };
openAPI.required = ['spec'];
const crd = {
  apiVersion: 'apiextensions.k8s.io/v1',
  kind: 'CustomResourceDefinition',
  metadata: { name: 'optimizationrecommendations.optimization.aks.io' },
  spec: {
    group: 'optimization.aks.io',
    scope: 'Namespaced',
    names: {
      plural: 'optimizationrecommendations',
      singular: 'optimizationrecommendation',
      kind: 'OptimizationRecommendation',
      shortNames: ['optrec'],
    },
    versions: [
      {
        name: 'v1alpha1',
        served: true,
        storage: true,
        subresources: { status: {} },
        additionalPrinterColumns: [
          { name: 'Phase', type: 'string', jsonPath: '.status.phase' },
          { name: 'Source', type: 'string', jsonPath: '.spec.source' },
          { name: 'Workload', type: 'string', jsonPath: '.spec.target.name' },
        ],
        schema: { openAPIV3Schema: openAPI },
      },
    ],
  },
};
const artifacts = [
  ['src/models/review.schema.json', JSON.stringify(schema, null, 2) + '\n'],
  ['src/models/vpa.schema.json', JSON.stringify(vpaSchema, null, 2) + '\n'],
  [
    '../../deploy/headlamp/recommendation-crd.yaml',
    '# Generated from the review envelope. Run npm run generate:contracts.\n' + stringify(crd),
  ],
];
for (const [relative, content] of artifacts) {
  const path = resolve(root, relative);
  if (process.argv.includes('--check')) {
    if (readFileSync(path, 'utf8').replace(/\r\n/g, '\n') !== content)
      throw new Error(`Contract drift: ${relative}`);
  } else {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
}
console.log(
  process.argv.includes('--check')
    ? 'Finding types, review/VPA schemas and CRD match.'
    : 'Generated finding types, review/VPA schemas and CRD.'
);
