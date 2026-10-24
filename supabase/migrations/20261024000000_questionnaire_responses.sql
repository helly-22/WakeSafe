-- WakeSafe: questionnaire responses, one row per (signed-in user, profile).
-- Health information: Row Level Security is mandatory. There is NO anonymous or
-- public access; every policy requires auth.uid() to own the row.

create table if not exists public.questionnaire_responses (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
  profile_id     text not null check (char_length(profile_id) between 1 and 64),
  answers        jsonb not null,
  complete       boolean not null default false,
  schema_version integer not null default 1,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (user_id, profile_id)
);

comment on table public.questionnaire_responses is
  'WakeSafe screening questionnaire answers. Screening aid only, not a diagnosis.';

-- Keep updated_at current and created_at immutable on every update (including upserts).
create or replace function public.questionnaire_responses_touch()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  if tg_op = 'UPDATE' then
    new.created_at := old.created_at;
    new.user_id := old.user_id;
  end if;
  return new;
end;
$$;

drop trigger if exists questionnaire_responses_touch on public.questionnaire_responses;
create trigger questionnaire_responses_touch
  before insert or update on public.questionnaire_responses
  for each row execute function public.questionnaire_responses_touch();

alter table public.questionnaire_responses enable row level security;
alter table public.questionnaire_responses force row level security;

-- Anonymous users get nothing.
revoke all on public.questionnaire_responses from anon;
grant select, insert, update, delete on public.questionnaire_responses to authenticated;

create policy "Owners read their questionnaire responses"
  on public.questionnaire_responses for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "Owners insert their questionnaire responses"
  on public.questionnaire_responses for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Owners update their questionnaire responses"
  on public.questionnaire_responses for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Owners delete their questionnaire responses"
  on public.questionnaire_responses for delete to authenticated
  using ((select auth.uid()) = user_id);
