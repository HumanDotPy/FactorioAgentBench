import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio

DEPOT_STUB = """
storage={actions={},agent_characters={}}
script={on_nth_tick=function(tick,handler) nth_handler=handler end}
game={tick=100,forces={player={}},surfaces={}}
defines={inventory={chest=1},build_check_type={manual=7}}
can_place_calls={}
unit_counter=0
surface={}
surface.name="nauvis"
function surface.can_place_entity(params)
    can_place_calls[#can_place_calls+1]={name=params.name,
        build_check_type=params.build_check_type}
    return true
end
function surface.create_entity(params)
    unit_counter=unit_counter+1
    return {valid=true,name=params.name,unit_number=unit_counter,
        position={x=params.position.x,y=params.position.y},
        surface=surface}
end
game.surfaces[1]=surface
game.surfaces["nauvis"]=surface
"""


def runtime():
    return lua_stub(DEPOT_STUB, "tools/admin/customer_depot/server.lua")


def place_one(lua):
    lua.execute("place_result=storage.actions.customer_depot(1,'place',0,0,1,false)")


def test_depot_place_uses_manual_build_check():
    lua = runtime()
    place_one(lua)
    assert lua.eval("place_result.placed") == 1
    assert lua.eval("#can_place_calls") == 1
    assert lua.eval("can_place_calls[1].name") == "steel-chest"
    assert (
        lua.eval(
            "can_place_calls[1].build_check_type == defines.build_check_type.manual"
        )
        is True
    )


def test_depot_rebuild_uses_manual_build_check():
    lua = runtime()
    place_one(lua)
    lua.execute(
        """
        storage.customer.depots[1].valid=false
        nth_handler({tick=200})
        """
    )
    assert lua.eval("storage.customer.last_error") is None
    assert lua.eval("#can_place_calls") == 2
    assert lua.eval("can_place_calls[2].name") == "steel-chest"
    assert (
        lua.eval(
            "can_place_calls[2].build_check_type == defines.build_check_type.manual"
        )
        is True
    )
