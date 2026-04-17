import { SUPABASE_URL, SUPABASE_ANON_KEY } from './config.js';

const { createClient } = window.supabase;
export const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
