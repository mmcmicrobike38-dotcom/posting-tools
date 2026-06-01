export type QueuedJobHandler<T> = (progress: (message: string) => void) => Promise<T>;

export interface QueuedJobOptions {
  key?: string;
}

interface PendingJob<T> {
  key?: string;
  run: () => Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

export class DedupedJobQueue {
  private running = 0;
  private readonly waiting: PendingJob<any>[] = [];
  private readonly inFlight = new Map<string, Promise<unknown>>();

  constructor(private readonly concurrency: number) {}

  enqueue<T>(
    handler: QueuedJobHandler<T>,
    options: QueuedJobOptions = {},
    progress: (message: string) => void = () => undefined
  ): Promise<T> {
    const jobKey = options.key;
    if (jobKey) {
      const existing = this.inFlight.get(jobKey);
      if (existing) return existing as Promise<T>;
    }

    const promise = new Promise<T>((resolve, reject) => {
      this.waiting.push({
        key: jobKey,
        run: () => handler(progress),
        resolve,
        reject
      });
      this.drain();
    });

    if (jobKey) {
      this.inFlight.set(
        jobKey,
        promise.finally(() => this.inFlight.delete(jobKey))
      );
    }

    return promise;
  }

  get pendingCount(): number {
    return this.waiting.length;
  }

  get activeCount(): number {
    return this.running;
  }

  private drain(): void {
    while (this.running < this.concurrency && this.waiting.length) {
      const job = this.waiting.shift();
      if (!job) return;
      this.running += 1;
      void job
        .run()
        .then(job.resolve, job.reject)
        .finally(() => {
          this.running -= 1;
          this.drain();
        });
    }
  }
}
