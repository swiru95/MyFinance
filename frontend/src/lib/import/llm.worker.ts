// The WebLLM engine in a worker (lib/import/assist.ts, browser mode): the model and the WebGPU work stay off the page's thread.
import { WebWorkerMLCEngineHandler } from "@mlc-ai/web-llm";

const handler = new WebWorkerMLCEngineHandler();
self.onmessage = (msg: MessageEvent) => handler.onmessage(msg);
