import pytest

from tests.actions.lua_stub_helpers import load_env, lua_stub

pytestmark = pytest.mark.no_factorio
SCORE_SERVERS = {
    "agent": "tools/agent/score/server.lua",
    "admin": "tools/admin/score/server.lua",
}

SCORE_STUB = """
storage={actions={},harvested_items={},crafted_items={}}
item_counts={["iron-ore"]=10}
game={
  surfaces={[1]={}},
  forces={player={
    name="player",
    get_item_production_statistics=function()
      return {input_counts=item_counts,output_counts={}}
    end,
    get_fluid_production_statistics=function()
      return {input_counts={},output_counts={}}
    end,
  }},
  players={},
}
prototypes={item={},fluid={},recipe={},entity={}}
util={product_amount=function(product) return product.amount or 1 end}
table_size=function(value) return #value end
"""


def score_runtime(name, plates=10):
    lua = lua_stub(SCORE_STUB)
    lua.execute(f"item_counts['iron-ore']={plates}")
    load_env(lua, SCORE_SERVERS[name])
    return lua


@pytest.mark.parametrize("name", ["agent", "admin"])
def test_score_baseline_is_episode_scoped_and_survives_reload(name):
    lua = score_runtime(name)
    assert lua.eval("storage.initial_score") is None
    assert lua.eval("storage.score_episode_baseline") is None

    assert lua.eval("storage.actions.score().player") == 0
    baseline = lua.eval("storage.initial_score.player")
    assert baseline == 31
    assert lua.eval("storage.score_episode_baseline") is True

    if name == "agent":
        assert lua.eval("storage.initial_harvested_value") == 0
        assert lua.eval("storage.initial_crafted_net_value") == 0

    lua.execute("item_counts['iron-ore']=25")
    assert lua.eval("storage.actions.score().player") == 77 - baseline

    load_env(lua, SCORE_SERVERS[name])
    lua.execute("item_counts['iron-ore']=40")
    assert lua.eval("storage.score_episode_baseline") is True
    assert lua.eval("storage.initial_score.player") == baseline
    assert lua.eval("storage.actions.score().player") == 124 - baseline

    lua.execute("storage.score_episode_baseline=nil; storage.initial_score=nil")
    assert lua.eval("storage.actions.score().player") == 0


RESET_STUB = """
storage={
  actions={},
  alerts={stale=true},
  elapsed_ticks=99,
  harvested_items={["iron-ore"]=3},
  crafted_items={{crafted_count=1}},
  manual_production_events={{tick=1}},
  harvest_queues={[1]={}},
  harvest_last_products={[1]="iron-ore"},
  native_crafting={[1]={counts={}}},
  crafting_queue={{}},
  walking_queues={[1]={}},
  paths={[1]="path"},
  path_requests={[1]={}},
  entity_handles={[5]={}},
  public_waits={[1]={status="pending"}},
  public_status_monitor={sequence=9,entities={[1]={}}},
  semantic_events={{type="under_attack"}},
  semantic_craft_sequence=7,
  camera={zoom=1},
  clearance_entities={[1]={{valid=false}}},
  fast=true,
  debug={rendering=false},
  initial_score={player=10},
  initial_harvested_value=1,
  initial_crafted_net_value=2,
  score_episode_baseline=true,
  objective_telemetry={deaths={{tick=1}},death_count=2,respawn_count=1,
    last_respawn_tick=5,resource_depletions={{tick=2}},last_death_tick_by_agent={[1]=1}},
  customer={delivered_total={["iron-ore"]=7},manual_delivered_total={["iron-ore"]=1},
    manual_pending={[1]={}},delta_log={{start_tick=0}},delta_index={[0]=true},
    tamper_events={{tick=1}},tamper_reported={[1]=true},retained_contents={[1]={}},
    active_products={["iron-ore"]={limit=10,accepted=2}},mode="designated",epoch_tick=4},
}
reset_stats_called=false
storage.actions.reset_production_stats=function() reset_stats_called=true end
storage.actions.regenerate_resources=function() end
storage.actions.clear_walking_queue=function() end
storage.actions.clear_entities=function() end
storage.actions.set_inventory=function() end
character={valid=true,teleport=function() end,
  force={technologies={["automation-science-pack"]={researched=false}},reset=function() end}}
storage.agent_characters={[1]=character}
game={reset_game_state=function() end,forces={player={}},players={}}
helpers={json_to_table=function() return {} end,table_to_json=function() return "{}" end}
"""


LOAD_STUB = """
storage={}
game={tick=0}
defines={events={on_tick=1},direction={north=0,northeast=2,east=4,southeast=6,
    south=8,southwest=10,west=12,northwest=14},
    inventory={rocket_silo_rocket=1,rocket_silo_input=2,rocket_silo_output=3,
        rocket_silo_modules=4,fuel=5,burnt_result=6,
        assembling_machine_input=7,chest=8,furnace_source=9}}
script={on_event=function() end,on_nth_tick=function() end}
"""


def test_load_preserves_episode_state_and_initialises_fresh_games():
    lua = lua_stub(LOAD_STUB)
    load_env(lua, "mods/initialise.lua")
    assert lua.eval("next(storage.manual_production_events)") is None
    assert lua.eval("next(storage.entity_handles)") is None

    lua.execute("""
        storage.manual_production_events={{tick=7}}
        storage.entity_handles={[3]={valid=true}}
    """)
    load_env(lua, "mods/initialise.lua")
    assert lua.eval("storage.manual_production_events[1].tick") == 7
    assert lua.eval("storage.entity_handles[3] ~= nil") is True

    lua.execute("storage.crafting_queue={{remaining_ticks=5}}")
    load_env(lua, "mods/utils.lua")
    assert lua.eval("storage.crafting_queue[1].remaining_ticks") == 5
    assert lua.eval("storage.utils.round(0.5)") == 1

    lua.execute("storage.alerts={stale=true}")
    load_env(lua, "mods/alerts.lua")
    assert lua.eval("storage.alerts.stale") is True

    lua.execute("storage.alerts=nil")
    load_env(lua, "mods/alerts.lua")
    assert lua.eval("storage.alerts") is not None
    assert lua.eval("next(storage.alerts)") is None


def reset_runtime():
    return lua_stub(RESET_STUB, "tools/admin/reset/server.lua")


def test_reset_clears_episode_state():
    lua = reset_runtime()
    lua.execute("storage.actions.reset('[]', true, false, true)")
    assert lua.eval("reset_stats_called") is True
    assert lua.eval("storage.elapsed_ticks") == 0
    assert lua.eval("storage.fast") is True
    assert lua.eval("storage.debug.rendering") is False
    cleared = (
        "storage.alerts.stale",
        "next(storage.manual_production_events)",
        "next(storage.crafting_queue)",
        "next(storage.native_crafting)",
        "next(storage.harvest_queues)",
        "next(storage.harvest_last_products)",
        "next(storage.walking_queues)",
        "next(storage.paths)",
        "next(storage.path_requests)",
        "next(storage.entity_handles)",
        "next(storage.public_waits)",
        "storage.public_status_monitor",
        "next(storage.semantic_events)",
        "storage.semantic_craft_sequence",
        "storage.camera",
        "next(storage.clearance_entities)",
        "storage.initial_score",
        "storage.initial_harvested_value",
        "storage.initial_crafted_net_value",
        "storage.score_episode_baseline",
        "next(storage.objective_telemetry.deaths)",
        "next(storage.objective_telemetry.resource_depletions)",
        "storage.objective_telemetry.last_death_tick_by_agent[1]",
        "storage.objective_telemetry.last_respawn_tick",
        "next(storage.customer.delivered_total)",
        "next(storage.customer.manual_delivered_total)",
        "next(storage.customer.manual_pending)",
        "next(storage.customer.delta_log)",
        "next(storage.customer.delta_index)",
        "next(storage.customer.tamper_events)",
        "storage.customer.tamper_reported[1]",
        "next(storage.customer.retained_contents)",
        "next(storage.customer.active_products)",
        "storage.customer.last_error",
    )
    for expression in cleared:
        assert lua.eval(expression) is None, expression
    assert lua.eval("storage.objective_telemetry.death_count") == 0
    assert lua.eval("storage.objective_telemetry.respawn_count") == 0


def test_reset_without_entity_clear_keeps_clearance_tracking():
    lua = reset_runtime()
    lua.execute("storage.actions.reset('[]', true, false, false)")
    assert lua.eval("storage.clearance_entities[1] ~= nil") is True
    assert lua.eval("next(storage.customer.delivered_total)") is None


DEPOT_STUB = """
storage={actions={}}
nth_calls=0
nth_handlers={}
script={on_nth_tick=function(tick, handler)
  nth_calls=nth_calls+1
  nth_handlers[tick]=handler
end}
game={tick=1000,surfaces={},forces={player={}}}
defines={inventory={chest=1}}
"""


def depot_runtime():
    return lua_stub(DEPOT_STUB, "tools/admin/customer_depot/server.lua")


def test_depot_drain_handler_registers_on_every_load_once():
    lua = depot_runtime()
    assert lua.eval("nth_calls") == 1
    assert lua.eval("nth_handlers[6] ~= nil") is True

    lua.execute("nth_calls=0; nth_handlers={}")
    load_env(lua, "tools/admin/customer_depot/server.lua")
    assert lua.eval("nth_calls") == 0

    lua.execute("fle_depot_drain_handler_installed=nil; nth_calls=0; nth_handlers={}")
    load_env(lua, "tools/admin/customer_depot/server.lua")
    assert lua.eval("nth_calls") == 1
    lua.execute("nth_handlers[6]({tick=1000})")


def test_configure_clears_delivery_telemetry():
    lua = depot_runtime()
    lua.execute(
        """
        storage.customer.delivered_total={["iron-ore"]=5}
        storage.customer.manual_delivered_total={["iron-ore"]=1}
        storage.customer.delta_log={{start_tick=0,items={["iron-ore"]=5}}}
        storage.customer.delta_index={[0]=true}
        storage.customer.tamper_events={{tick=1,unit_number=2,reason="gone"}}
        storage.customer.tamper_reported={[2]=true}
        storage.customer.last_error="boom"
        result=storage.actions.customer_depot(
            1, "configure", {{name="iron-ore",limit=10}}, 0, 0, false)
        """
    )
    assert lua.eval("result.mode") == "designated"
    for expression in (
        "next(storage.customer.delivered_total)",
        "next(storage.customer.manual_delivered_total)",
        "next(storage.customer.delta_log)",
        "next(storage.customer.delta_index)",
        "next(storage.customer.tamper_events)",
        "storage.customer.tamper_reported[2]",
        "storage.customer.last_error",
    ):
        assert lua.eval(expression) is None, expression
    assert lua.eval("storage.customer.active_products['iron-ore'].accepted") == 0
    assert lua.eval("storage.customer.active_products['iron-ore'].limit") == 10
