# Headlamp Operator Templates

These are reviewed installation inputs, not an automatic deployment. Do not apply
them to the current kube-context without explicit operator approval.

- `recommendation-crd.yaml`: generated management-cluster review envelope,
  `optimization.aks.io/v1alpha1`, with a backend-owned status subresource.
- `rbac.yaml`: namespace-scoped examples with **no bindings** and no workload or
  status mutations. Custom action verbs require an independently authorized API.
- `plugin-values.yaml`: upstream Helm overlay disabling the chart's default
  cluster-admin binding, unsafe service-account authentication, automatic plugin
  downloads and public ingress. Supply approved OIDC and narrow roles separately.
- `network-policy.yaml`: opt-in, dedicated-pod egress deny baseline. It is not a
  complete network plan; add exact approved API/DNS/identity/backend destinations.
- `sample-recommendations.yaml`: deterministic synthetic records for a fixed
  2026-10-30 clock, not approved actions. Status in a manifest is **not** populated
  by normal create/apply with the status subresource enabled. A test publisher must
  write status using the actual Kubernetes-assigned identity and resourceVersion.
- `sample-vpas.yaml`: optional synthetic VPA objects, not a VPA CRD installation.

## Bundle Mount

After `npm run build` in the plugin package, an operator can create a namespaced
ConfigMap from the built directory and mount it with the values overlay. Confirm
the bundle remains below the ConfigMap size limit, pin the Headlamp chart/image,
and review the exact plugin contents first. No command below contacts a cluster:

```sh
kubectl create configmap headlamp-fleet-efficiency-plugin \
  --namespace headlamp-system \
  --from-file=plugins/headlamp-fleet-efficiency/dist/ \
  --dry-run=client -o yaml
```

The operator must separately persist/install the resulting manifest through the
approved deployment process. Do not use the standalone preview as the plugin.
There is deliberately no GitHub token, backend URL, broad role binding or cluster
credential in these files. Existing Headlamp deployments should merge volume
settings carefully instead of replacing their other plugins or network policy.

## Source References

- https://github.com/kubernetes-sigs/headlamp/blob/main/charts/headlamp/values.yaml
- https://headlamp.dev/docs/latest/development/plugins/building/
- [Plugin configuration and runbook](../../plugins/headlamp-fleet-efficiency/docs/operations.md)