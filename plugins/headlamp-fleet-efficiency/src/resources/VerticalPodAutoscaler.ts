import { K8s } from '@kinvolk/headlamp-plugin/lib';
import type { VpaRecord } from '../models/review';

export class VerticalPodAutoscaler extends K8s.cluster.KubeObject<
  VpaRecord & K8s.cluster.KubeObjectInterface
> {
  static apiVersion = 'autoscaling.k8s.io/v1';
  static apiName = 'verticalpodautoscalers';
  static kind = 'VerticalPodAutoscaler';
  static isNamespaced = true;
  get spec() {
    return this.jsonData.spec;
  }
  get recommendations() {
    return this.jsonData.status?.recommendation?.containerRecommendations ?? [];
  }
}
