-- ════════════════════════════════════════════════════════════════════════
-- Tickets Maison — V6 : entités Home Assistant remontées dans l'app
-- À exécuter UNE FOIS dans Supabase › SQL Editor › New query › Run
-- (sans risque si relancé). L'avertissement « Potential issue detected » est normal.
-- ════════════════════════════════════════════════════════════════════════

-- Une ligne par entité choisie dans Home Assistant (écrite par l'intégration Tickets Maison)
create table if not exists public.ha_entities (
    house_id       uuid not null references public.houses(id) on delete cascade,
    entity_id      text not null,                -- ex. sensor.temperature_salon
    name           text not null default '',
    state          text not null default '',     -- valeur brute (on, off, 21.5, unavailable…)
    unit           text,                         -- °C, %, W…
    device_class   text,                         -- temperature, door, battery…
    available      boolean not null default true,
    last_changed   timestamptz,
    open_ticket_id uuid references public.tickets(id) on delete set null,
    updated_at     timestamptz not null default now(),
    primary key (house_id, entity_id)
);

alter table public.ha_entities enable row level security;
drop policy if exists "famille_ha_entities" on public.ha_entities;
create policy "famille_ha_entities" on public.ha_entities for all to anon using (true) with check (true);
grant select, insert, update, delete on public.ha_entities to anon;

notify pgrst, 'reload schema';
