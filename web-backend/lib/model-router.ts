import { config } from "./system-config";
export async function runModel(input: string): Promise<{ text: string; model: string }> {
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST", headers: { Authorization: `Bearer ${config.openAiKey()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: config.openAiModel(), input, store: false, max_output_tokens: 1200 }),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error("MODEL_PROVIDER_REQUEST_FAILED");
  const data: unknown = await response.json();
  if (!data || typeof data !== "object") throw new Error("MODEL_PROVIDER_RESPONSE_INVALID");
  const obj = data as { status?: string; model?: string; output?: Array<{type?: string; content?: Array<{type?: string; text?: string}>}> };
  if (obj.status !== "completed" || !obj.model) throw new Error("MODEL_PROVIDER_RESPONSE_INCOMPLETE");
  const text = (obj.output ?? []).flatMap(x => x.type === "message" ? (x.content ?? []).filter(c => c.type === "output_text").map(c => c.text ?? "") : []).join("\n").trim();
  if (!text) throw new Error("MODEL_PROVIDER_EMPTY_OUTPUT");
  return { text, model: obj.model };
}
