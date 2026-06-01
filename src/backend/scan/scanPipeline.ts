import { DedupedJobQueue } from "../workers/dedupedJobQueue";

export interface ScanItem {
  id: string;
}

export interface ScanSource<TItem extends ScanItem> {
  items(): AsyncIterable<TItem>;
}

export interface ScanIndex<TItem extends ScanItem> {
  isFresh(item: TItem): boolean | Promise<boolean>;
  save(item: TItem): void | Promise<void>;
  flush?(): void | Promise<void>;
}

export interface ScanProcessor<TItem extends ScanItem, TResult> {
  process(item: TItem): Promise<TResult>;
}

export interface ScanPipelineResult<TResult> {
  processed: TResult[];
  skipped: number;
  durationMs: number;
}

export interface ScanPipelineOptions {
  concurrency: number;
  jobKeyPrefix: string;
  maxBufferedJobs?: number;
}

export async function runScanPipeline<TItem extends ScanItem, TResult>(
  source: ScanSource<TItem>,
  index: ScanIndex<TItem>,
  processor: ScanProcessor<TItem, TResult>,
  options: ScanPipelineOptions
): Promise<ScanPipelineResult<TResult>> {
  const started = performance.now();
  const queue = new DedupedJobQueue(options.concurrency);
  const maxBufferedJobs = Math.max(options.concurrency, options.maxBufferedJobs ?? options.concurrency * 4);
  const jobs = new Set<Promise<TResult | null>>();
  const processed: TResult[] = [];
  let skipped = 0;

  const trackJob = (job: Promise<TResult | null>): void => {
    jobs.add(job);
    job
      .then((result) => {
        if (result !== null) processed.push(result);
      }, () => undefined)
      .finally(() => jobs.delete(job));
  };

  const waitForBackpressure = async (): Promise<void> => {
    if (jobs.size < maxBufferedJobs) return;
    await Promise.race(jobs);
  };

  for await (const item of source.items()) {
    await waitForBackpressure();
    trackJob(
      queue.enqueue(
        async () => {
          if (await index.isFresh(item)) {
            skipped += 1;
            return null;
          }
          const result = await processor.process(item);
          await index.save(item);
          return result;
        },
        { key: `${options.jobKeyPrefix}:${item.id}` }
      )
    );
  }

  await Promise.all(jobs);
  await index.flush?.();

  return {
    processed,
    skipped,
    durationMs: performance.now() - started
  };
}
