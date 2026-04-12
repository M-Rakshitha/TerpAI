function notImplemented() {
	return new Response('Auth is not configured for this build.', { status: 501 });
}

export async function GET() {
	return notImplemented();
}

export async function POST() {
	return notImplemented();
}