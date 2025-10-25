// ✅ /pages/api/fetch_sales_summary_by_code.ts
// （App Router の場合は /app/api/fetch_sales_summary_by_code/route.ts）

import { NextResponse } from 'next/server';
import { getSalesSummaryByCode } from '@/lib/db'; // ← 既存のDB取得関数

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const code = searchParams.get('code');
    const section = searchParams.get('section'); // "company" | "orders" | "products"
    const invoice = searchParams.get('invoice'); // optional
    const limit = Number(searchParams.get('limit') ?? 100); // default 100件

    if (!code) {
      return NextResponse.json({ error: 'Missing code parameter' }, { status: 400 });
    }

    // DBまたはスプレッドシートから顧客情報を取得
    const fullData = await getSalesSummaryByCode(code);

    // ---- 🎯 ここから分割処理 ----
    if (section === 'company') {
      return NextResponse.json({ code, company: fullData.company });
    }

    if (section === 'orders') {
      let orders = fullData.orders ?? [];

      // Invoice番号でフィルタリング（該当する場合のみ）
      if (invoice) {
        orders = orders.filter((o: any) => o.invoice === invoice);
      }

      // limit件で制限
      orders = orders.slice(0, limit);

      return NextResponse.json({ code, orders });
    }

    if (section === 'products') {
      return NextResponse.json({ code, products: fullData.products ?? [] });
    }

    // デフォルト（旧仕様互換）
    return NextResponse.json(fullData);
  } catch (error: any) {
    console.error('API Error:', error);
    return NextResponse.json({ error: error.message ?? 'Internal Server Error' }, { status: 500 });
  }
}
