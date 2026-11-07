/** Load an entire selector catalog. A failed tail page must reject the whole load. */
export async function listPages<T>(
  fetchPage: (page: number, pageSize: number) => Promise<T[]>,
  signal?: AbortSignal,
  pageSize = 200,
): Promise<T[]> {
  const items: T[] = []
  for (let page = 1; ; page++) {
    signal?.throwIfAborted()
    const batch = await fetchPage(page, pageSize)
    signal?.throwIfAborted()
    items.push(...batch)
    if (batch.length < pageSize) return items
  }
}
