import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabasePublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;

if (!supabaseUrl || !supabasePublishableKey) {
  throw new Error("Missing required Supabase public environment variables");
}

export function createClient() {
  return createBrowserClient(supabaseUrl, supabasePublishableKey);
}
