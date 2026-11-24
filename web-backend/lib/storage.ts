import { Pool } from "pg";
import { config } from "./system-config";

let pool: Pool | undefined;
let schemaReady: Promise<void> | undefined;
function db(): Pool {
  if (!pool) pool = new Pool({ connectionString: config.databaseUrl(), ssl: { rejectUnauthorized: true }, max: 3 });
  return pool;
}
async function ensureSchema(): Promise<void> {
  if (!schemaReady) schemaReady = db().query(`
    CREATE TABLE IF NOT EXISTS omega_workflows (
      id text PRIMARY KEY, status text NOT NULL CHECK (status IN ('PENDING','RUNNING','APPROVED','REJECTED','CANCELLED','COMPLETED','FAILED')),
      payload jsonb NOT NULL, result jsonb, created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS omega_callbacks (
      token_hash text PRIMARY KEY, workflow_id text NOT NULL REFERENCES omega_workflows(id),
      consumed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    );
  `).then(() => undefined).catch((error) => { schemaReady = undefined; throw error; });
  return schemaReady;
}
export async function createWorkflow(id: string, payload: unknown, callbackTokenHash: string) {
  await ensureSchema();
  const client = await db().connect();
  try {
    await client.query("BEGIN");
    await client.query("INSERT INTO omega_workflows(id,status,payload) VALUES($1,'PENDING',$2::jsonb)", [id, JSON.stringify(payload)]);
    await client.query("INSERT INTO omega_callbacks(token_hash,workflow_id) VALUES($1,$2)", [callbackTokenHash, id]);
    await client.query("COMMIT");
  } catch (e) { await client.query("ROLLBACK"); throw e; }
  finally { client.release(); }
}
export async function transitionWorkflow(id: string, from: string[], to: string, result?: unknown) {
  await ensureSchema();
  const q = await db().query(
    "UPDATE omega_workflows SET status=$3,result=COALESCE($4::jsonb,result),updated_at=now() WHERE id=$1 AND status=ANY($2::text[]) RETURNING id,status",
    [id, from, to, result === undefined ? null : JSON.stringify(result)]
  );
  return q.rows[0] ?? null;
}
export async function consumeCallback(tokenHash: string, body: unknown) {
  await ensureSchema();
  const client = await db().connect();
  try {
    await client.query("BEGIN");
    const row = await client.query("SELECT workflow_id,consumed_at FROM omega_callbacks WHERE token_hash=$1 FOR UPDATE", [tokenHash]);
    if (!row.rows[0] || row.rows[0].consumed_at) { await client.query("ROLLBACK"); return null; }
    await client.query("UPDATE omega_callbacks SET consumed_at=now() WHERE token_hash=$1", [tokenHash]);
    const result = await client.query("UPDATE omega_workflows SET status='COMPLETED',result=$2::jsonb,updated_at=now() WHERE id=$1 AND status IN ('RUNNING','APPROVED') RETURNING id,status", [row.rows[0].workflow_id, JSON.stringify(body)]);
    await client.query("COMMIT");
    return result.rows[0] ?? null;
  } catch (e) { await client.query("ROLLBACK"); throw e; }
  finally { client.release(); }
}
