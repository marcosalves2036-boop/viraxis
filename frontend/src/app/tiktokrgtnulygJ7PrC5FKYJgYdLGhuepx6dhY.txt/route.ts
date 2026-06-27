import { NextResponse } from 'next/server';

export async function GET() {
  return new NextResponse('tiktok-developers-site-verification=rgtnulygJ7PrC5FKYJgYdLGhuepx6dhY', {
    status: 200,
    headers: {
      'Content-Type': 'text/plain',
    },
  });
}
