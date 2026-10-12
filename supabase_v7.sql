-- ════════════════════════════════════════════════════════════════════════
-- Tickets Maison — V7 : électroménager Home Connect (Bosch, Siemens, Neff, Gaggenau)
-- À exécuter UNE FOIS dans Supabase › SQL Editor › New query › Run
-- (sans risque si relancé). L'avertissement « Potential issue detected » est normal.
-- ════════════════════════════════════════════════════════════════════════

-- Connexion Home Connect d'une maison : saisie dans l'app, utilisée par le watchdog
create table if not exists public.homeconnect (
    house_id          uuid primary key references public.houses(id) on delete cascade,
    client_id         text not null,
    client_secret     text not null default '',
    -- login_requested → awaiting_user (code affiché dans l'app) → connected / error
    status            text not null default 'login_requested',
    user_code         text,
    verification_uri  text,
    code_expires_at   timestamptz,
    refresh_token     text,
    error             text,
    updated_at        timestamptz not null default now()
);

-- Appareils Home Connect de la maison (écrits par le watchdog)
create table if not exists public.appliances (
    house_id        uuid not null references public.houses(id) on delete cascade,
    ha_id           text not null,                       -- identifiant Home Connect de l'appareil
    name            text not null default '',
    brand           text,
    type            text,                                -- Dishwasher, Oven, FridgeFreezer…
    connected       boolean not null default true,
    alerts          jsonb not null default '[]'::jsonb,  -- alertes en cours : [{"key": "...", "label": "..."}]
    open_ticket_id  uuid references public.tickets(id) on delete set null,
    updated_at      timestamptz not null default now(),
    primary key (house_id, ha_id)
);

alter table public.homeconnect enable row level security;
alter table public.appliances  enable row level security;
drop policy if exists "famille_homeconnect" on public.homeconnect;
drop policy if exists "famille_appliances"  on public.appliances;
create policy "famille_homeconnect" on public.homeconnect for all to anon using (true) with check (true);
create policy "famille_appliances"  on public.appliances  for all to anon using (true) with check (true);
grant select, insert, update, delete on public.homeconnect, public.appliances to anon;

notify pgrst, 'reload schema';
