# Supabase (planned, not connected)

Questionnaire answers are currently saved with a **demo-only local adapter**
(`frontend/src/services/questionnaire/store.ts`, browser localStorage, synthetic
demo profiles only). Nothing is sent to Supabase today.

## What exists
- `migrations/20261024000000_questionnaire_responses.sql`: the table, timestamps,
  and Row Level Security. Every row belongs to `auth.uid()`; anonymous users have
  no access. There are no public read or write policies.
- `frontend/src/services/questionnaire/supabaseStore.ts`: a typed adapter that
  calls the table with the **signed-in user's** token. It is not wired into the app.

## What is needed to enable cloud persistence
1. A Supabase project, and the migration applied (`supabase db push` or the SQL editor).
2. `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `frontend/.env.local`
   (placeholders in `frontend/.env.example`). The anon key is public by design;
   RLS is what protects the data.
3. **Supabase Auth in the app** (sign-in, session handling) so the adapter gets a
   real access token. Without a signed-in user, RLS rejects every request.
4. Switch `getQuestionnaireStore()` to `SupabaseStore` for signed-in users.
5. A team decision on storing health answers at all (the contract says no
   unnecessary server-side persistence), plus a privacy notice and a delete action.

Never put the **service-role key** in frontend code or any `VITE_*` variable.
