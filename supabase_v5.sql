-- Tickets Maison — v5 : résumé pour Home Assistant
-- À coller dans Supabase › SQL Editor › New query › Run (une seule fois, sans risque si relancé)
--
-- Home Assistant appelle cette fonction toutes les minutes avec l'ID de la maison
-- et reçoit un résumé : compteurs par statut, urgences, appareils hors ligne,
-- dernier ticket et liste des tickets ouverts.

create or replace function public.ha_summary(p_house uuid)
returns json
language sql stable security definer set search_path = public as $$
    with open_t as (
        select t.*, coalesce(t.priority, t.requested_priority, 'normal') as eff_priority
        from tickets t
        where t.house_id = p_house and t.status <> 'resolved'
    ),
    dev as (
        select * from monitored_devices where house_id = p_house and enabled
    )
    select json_build_object(
        'house',          (select name from houses where id = p_house),
        'open',           (select count(*) from open_t),
        'sent',           (select count(*) from open_t where status = 'sent'),
        'in_progress',    (select count(*) from open_t where status = 'inProgress'),
        'waiting_user',   (select count(*) from open_t where status = 'waitingUser'),
        'urgent',         (select count(*) from open_t where eff_priority = 'urgent'),
        'to_validate',    (select count(*) from open_t where priority is null and requested_priority <> 'normal'),
        'resolved_today', (select count(*) from tickets
                            where house_id = p_house and status = 'resolved'
                              and resolved_at >= date_trunc('day', now() at time zone 'Europe/Paris') at time zone 'Europe/Paris'),
        'resolved_7d',    (select count(*) from tickets
                            where house_id = p_house and status = 'resolved'
                              and resolved_at >= now() - interval '7 days'),
        'devices',        (select count(*) from dev),
        'devices_down',   (select count(*) from dev where status = 'down'),
        'devices_down_names', (select coalesce(string_agg(name, ', ' order by name), '')
                               from dev where status = 'down'),
        'last_ticket',    (select json_build_object(
                               'number', '#' || upper(left(id::text, 4)),
                               'title', problem, 'zone', theme, 'status', status,
                               'author', author, 'created_at', created_at)
                           from tickets where house_id = p_house
                           order by created_at desc limit 1),
        'tickets',        (select coalesce(json_agg(x order by x.rank, x.created_at desc), '[]'::json) from (
                               select id, '#' || upper(left(id::text, 4)) as number, details,
                                      problem as title, theme as zone, status,
                                      case status when 'sent' then 'Envoyé'
                                                  when 'inProgress' then 'En cours'
                                                  when 'waitingUser' then 'Attente réponse'
                                                  else status end as status_label,
                                      eff_priority as priority, author, created_at, updated_at,
                                      case eff_priority when 'urgent' then 0 when 'normal' then 1 else 2 end as rank
                               from open_t
                               order by rank, created_at desc
                               limit 50) x),
        'updated_at',     now()
    );
$$;

grant execute on function public.ha_summary(uuid) to anon;
