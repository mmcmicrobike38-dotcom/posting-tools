export type JobHandler<T> = (progress: (message: string) => void) => Promise<T>;

export class SimpleJobQueue {
  private running = 0;
  private readonly waiting: Array<() => void> = [];

  constructor(private readonly concurrency: number) {}

  async run<T>(handler: JobHandler<T>, progress: (message: string) => void = () => undefined): Promise<T> {
    await this.acquire();
    try {
      return await handler(progress);
    } finally {
      this.release();
    }
  }

  private async acquire(): Promise<void> {
    if (this.running < this.concurrency) {
      this.running += 1;
      return;
    }
    await new Promise<void>((resolve) => this.waiting.push(resolve));
    this.running += 1;
  }

  private release(): void {
    this.running -= 1;
    const next = this.waiting.shift();
    if (next) next();
  }
}
