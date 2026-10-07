// SSE consumer for POST endpoints with a JSON body.
//
// The browser-native EventSource only supports GET with no body, but the
// translate endpoint is a POST that takes { raw_text, source_lang }. So we
// use fetch() with a streaming reader and parse the text/event-stream frames
// ("data: {...}\n\n") ourselves, yielding each parsed JSON payload.

export interface StreamSseOptions {
  url: string;
  body: unknown;
  signal?: AbortSignal;
  /** Extra request headers (e.g. the X-LLM-Api-Key BYO-key header). */
  headers?: Record<string, string>;
  /** Called once with the raw HTTP Response before streaming begins. */
  onResponse?: (res: Response) => void;
}

/**
 * POST a JSON body and stream back parsed SSE event payloads as an async
 * iterator. Each yielded value is a parsed `data:` JSON object of type T.
 *
 * Throws if the response is not ok or not an event stream (so the caller can
 * surface a connection error without losing user input).
 */
export async function* streamSse<T>({
  url,
  body,
  signal,
  headers,
  onResponse,
}: StreamSseOptions): AsyncGenerator<T, void, unknown> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...headers,
    },
    body: JSON.stringify(body),
    signal,
  });

  onResponse?.(res);

  if (!res.ok) {
    // Try to surface a useful message from a JSON error body (e.g. 404/422).
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      /* non-JSON body; keep the generic message */
    }
    throw new Error(detail);
  }

  if (!res.body) {
    throw new Error("Streaming is not supported in this environment.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line. Normalise CRLF first.
      let sep: number;
      // eslint-disable-next-line no-cond-assign
      while ((sep = indexOfFrameBoundary(buffer)) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep).replace(/^(\r?\n){1,2}/, "");

        const payload = parseDataFrame(frame);
        if (payload !== undefined) {
          yield payload as T;
        }
      }
    }

    // Flush any trailing frame without a terminating blank line.
    const tail = parseDataFrame(buffer);
    if (tail !== undefined) {
      yield tail as T;
    }
  } finally {
    reader.releaseLock();
  }
}

/** Finds the index of the next frame boundary (blank line), or -1. */
function indexOfFrameBoundary(buf: string): number {
  const lf = buf.indexOf("\n\n");
  const crlf = buf.indexOf("\r\n\r\n");
  if (lf === -1) return crlf;
  if (crlf === -1) return lf;
  return Math.min(lf, crlf);
}

/**
 * Parse a single SSE frame into its JSON data payload. A frame may contain
 * multiple `data:` lines (concatenated per spec) and comment/`event:` lines
 * we ignore. Returns undefined when the frame carries no data.
 */
function parseDataFrame(frame: string): unknown | undefined {
  const dataLines: string[] = [];
  for (const rawLine of frame.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }
  if (dataLines.length === 0) return undefined;

  const data = dataLines.join("\n");
  try {
    return JSON.parse(data);
  } catch {
    // A non-JSON data line; return it raw so callers can decide what to do.
    return data;
  }
}
