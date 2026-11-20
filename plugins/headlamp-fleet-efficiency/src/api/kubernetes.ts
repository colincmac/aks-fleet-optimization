import type { JsonRequest } from './provider';

export async function boundedList(
  request: JsonRequest,
  path: string,
  signal?: AbortSignal
): Promise<unknown[]> {
  const items: unknown[] = [];
  let token = '';
  let version: string | undefined;
  const seen = new Set<string>();
  for (let page = 0; page < 20; page++) {
    const params = new URLSearchParams({ limit: '250', ...(token ? { continue: token } : {}) });
    let response: { items?: unknown[]; metadata?: { continue?: string; resourceVersion?: string } };
    try {
      response = (await request(`${path}?${params}`, { method: 'GET', signal })) as typeof response;
    } catch (error) {
      const code =
        error && typeof error === 'object' && 'status' in error ? error.status : undefined;
      throw new Error(
        code === 403
          ? 'Permission denied reading recommendation resources. Check management-namespace RBAC.'
          : code === 404
            ? 'Recommendation API not found. Install the review CRD and confirm its served API version.'
            : 'Kubernetes API read failed. No complete recommendation list is available.'
      );
    }
    if (!Array.isArray(response.items) || !response.metadata?.resourceVersion)
      throw new Error('Incomplete Kubernetes list response.');
    if (version && version !== response.metadata.resourceVersion)
      throw new Error('Kubernetes list changed during pagination. Refresh the view.');
    version = response.metadata.resourceVersion;
    items.push(...response.items);
    if (items.length > 5000)
      throw new Error(
        'Recommendation list exceeds the 5000-object read budget. Narrow the configured namespace.'
      );
    token = response.metadata.continue ?? '';
    if (!token) return items;
    if (seen.has(token)) throw new Error('Kubernetes pagination cursor repeated.');
    seen.add(token);
  }
  throw new Error('Kubernetes pagination budget exceeded; data is incomplete.');
}
