import { K8s } from '@kinvolk/headlamp-plugin/lib';
import type { OptimizationRecommendation as ReviewRecord } from '../models/review';

export class OptimizationRecommendation extends K8s.cluster.KubeObject<
  ReviewRecord & K8s.cluster.KubeObjectInterface
> {
  static apiVersion = 'optimization.aks.io/v1alpha1';
  static apiName = 'optimizationrecommendations';
  static kind = 'OptimizationRecommendation';
  static isNamespaced = true;
  static get detailsRoute() {
    return '/fleet-efficiency/recommendations/:namespace/:name';
  }
  get spec() {
    return this.jsonData.spec;
  }
  get status() {
    return this.jsonData.status;
  }
}
