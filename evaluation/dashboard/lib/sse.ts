import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";

const encoder = new TextEncoder();

function nearestExistingDirectory(filePath: string): string {
  let current = path.dirname(filePath);
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) return process.cwd();
    current = parent;
  }
  return current;
}

export function createTailStream(
  filePath: string,
  signal: AbortSignal,
  initialBytes = 256 * 1024,
): ReadableStream<Uint8Array> {
  let position = 0;
  let closed = false;
  let reading = false;
  let watcher: fs.FSWatcher | null = null;
  let poller: NodeJS.Timeout | null = null;
  let heartbeat: NodeJS.Timeout | null = null;
  const decoder = new TextDecoder("utf-8");

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: string, payload: unknown) => {
        if (closed) return;
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`),
        );
      };

      const close = () => {
        if (closed) return;
        closed = true;
        watcher?.close();
        if (poller) clearInterval(poller);
        if (heartbeat) clearInterval(heartbeat);
        try {
          controller.close();
        } catch {
          // The browser can close the stream first.
        }
      };

      const readNewBytes = async (initial = false) => {
        if (closed || reading) return;
        reading = true;
        try {
          const stat = await fsp.stat(filePath);
          if (!stat.isFile()) return;
          if (initial) {
            position = Math.max(0, stat.size - initialBytes);
          } else if (stat.size < position) {
            position = 0;
            send("reset", { path: filePath });
          }
          if (stat.size <= position) return;

          const handle = await fsp.open(filePath, "r");
          try {
            while (position < stat.size) {
              const length = Math.min(64 * 1024, stat.size - position);
              const buffer = Buffer.allocUnsafe(length);
              const { bytesRead } = await handle.read(buffer, 0, length, position);
              if (!bytesRead) break;
              position += bytesRead;
              const chunk = decoder.decode(buffer.subarray(0, bytesRead), {
                stream: true,
              });
              if (chunk) send("chunk", { chunk, offset: position });
            }
          } finally {
            await handle.close();
          }
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
            send("error", { message: (error as Error).message });
          }
        } finally {
          reading = false;
        }
      };

      send("ready", { exists: fs.existsSync(filePath) });
      await readNewBytes(true);

      try {
        watcher = fs.watch(nearestExistingDirectory(filePath), () => {
          void readNewBytes();
        });
      } catch {
        watcher = null;
      }
      poller = setInterval(() => void readNewBytes(), 1000);
      heartbeat = setInterval(() => send("ping", { at: Date.now() }), 15_000);
      signal.addEventListener("abort", close, { once: true });
    },
    cancel() {
      closed = true;
      watcher?.close();
      if (poller) clearInterval(poller);
      if (heartbeat) clearInterval(heartbeat);
    },
  });
}

export const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
};
