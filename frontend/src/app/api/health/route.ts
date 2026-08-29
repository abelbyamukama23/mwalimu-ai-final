import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({ status: "ok", service: "mwalimu-frontend" }, { status: 200 });
}
