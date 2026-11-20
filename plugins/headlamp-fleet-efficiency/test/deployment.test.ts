import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { parse, parseAllDocuments } from 'yaml';
import { parseRecommendation } from '../src/api/contracts';

const deployment = resolve(process.cwd(), '../../deploy/headlamp');
describe('operator deployment boundaries', () => {
  it('grants no Kubernetes writes, workload access, bindings, wildcards or secrets', () => {
    const roles = parseAllDocuments(readFileSync(resolve(deployment, 'rbac.yaml'), 'utf8')).map(
      (document) => document.toJSON()
    );
    expect(roles).toHaveLength(4);
    for (const role of roles) {
      expect(role.kind).toBe('Role');
      expect(role.metadata.namespace).toBe('fleet-efficiency-system');
      for (const rule of role.rules) {
        expect(rule.apiGroups).toEqual(['optimization.aks.io']);
        expect(rule.resources).toEqual(['optimizationrecommendations']);
        expect(
          rule.verbs.some((verb: string) =>
            [
              '*',
              'patch',
              'update',
              'delete',
              'create',
              'impersonate',
              'bind',
              'escalate',
            ].includes(verb)
          )
        ).toBe(false);
      }
    }
  });
  it('disables Helm cluster-admin bindings and unsafe service-account authentication', () => {
    const values = parse(readFileSync(resolve(deployment, 'plugin-values.yaml'), 'utf8'));
    expect(values.clusterRoleBinding.create).toBe(false);
    expect(values.config.unsafeUseServiceAccountToken).toBe(false);
    expect(values.pluginsManager.enabled).toBe(false);
    expect(values.volumeMounts[0].readOnly).toBe(true);
  });
  it('uses a status subresource and valid synthetic review objects', () => {
    const crd = parse(readFileSync(resolve(deployment, 'recommendation-crd.yaml'), 'utf8'));
    expect(crd.spec.versions[0].subresources).toEqual({ status: {} });
    expect(crd.spec.scope).toBe('Namespaced');
    const records = parseAllDocuments(
      readFileSync(resolve(deployment, 'sample-recommendations.yaml'), 'utf8')
    ).map((document) => parseRecommendation(document.toJSON()));
    expect(records).toHaveLength(12);
    expect(records.every((record) => record.spec.finding.estimated_monthly_savings === null)).toBe(
      true
    );
  });
});
