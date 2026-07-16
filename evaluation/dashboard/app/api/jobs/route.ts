import { NextResponse } from "next/server";
import { listJobs, startJob } from "@/lib/jobs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({ jobs: await listJobs() });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      commandId?: unknown;
      args?: unknown;
    };
    const job = await startJob(body.commandId, body.args);
    return NextResponse.json({ job }, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: (error as Error).message },
      { status: 400 },
    );
  }
}
