export type Change = {id: string | null; aggregate_id: string | null; aggregate_version: string | null};
export function changedResources(events: Change[], cursor: string, versions: Map<string, bigint>): boolean {
  let changed = false;
  for (const event of events) {
    if (!event.id || !event.aggregate_id || !event.aggregate_version || !/^\d{1,18}$/.test(event.id) || !/^\d{1,18}$/.test(event.aggregate_version)) continue;
    if (BigInt(event.id) <= BigInt(cursor)) continue;
    const version = BigInt(event.aggregate_version);
    if (version <= (versions.get(event.aggregate_id) ?? 0n)) continue;
    versions.set(event.aggregate_id, version); changed = true;
  }
  return changed;
}
