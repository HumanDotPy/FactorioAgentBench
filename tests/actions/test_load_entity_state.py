import pytest

from tests.actions.lua_stub_helpers import lua_stub

pytestmark = pytest.mark.no_factorio


def runtime():
    return lua_stub(
        """
        storage={actions={},agent_characters={}}
        prototypes={item={['iron-plate']={name='iron-plate',stack_size=100}}}
        helpers={json_to_table=function() return stored_data end}
        game={forces={player={}}}
        stored_data={}
        lines={}
        function make_line()
            local line={inserted={},accept=0}
            line.insert_at=function(position,stack)
                if line.accept<=0 then return false end
                line.accept=line.accept-1
                table.insert(line.inserted,{position=position,name=stack.name,count=stack.count})
                return true
            end
            return line
        end
        surface={
            find_entities_filtered=function() return {} end,
            create_entity=function(params)
                return {valid=true,name=params.name,type='transport-belt',
                    unit_number=1,position=params.position,
                    get_transport_line=function(index)
                        lines[index]=lines[index] or make_line()
                        return lines[index]
                    end}
            end,
        }
        storage.agent_characters[1]={surface=surface}
        """,
        "tools/admin/load_entity_state/server.lua",
    )


def load_belt(lua, count, accept):
    lua.execute(
        "stored_data={{name='\"transport-belt\"',type='\"transport-belt\"',"
        "entity_number=1,position={x=0,y=0},direction=0,"
        "transport_lines={['1']={['\"iron-plate\"']="
        + str(count)
        + "}}}}\n"
        + "lines[1]=make_line()\n"
        + "lines[1].accept="
        + str(accept)
        + "\n"
        + "result=storage.actions.load_entity_state(1,'[]')"
    )


def test_partial_belt_insert_reports_leftovers_and_advances_per_item():
    lua = runtime()
    load_belt(lua, 4, 3)
    assert lua.eval("result.restored") is True
    assert lua.eval("#result.leftover") == 1
    assert lua.eval("result.leftover[1].name") == "iron-plate"
    assert lua.eval("result.leftover[1].count") == 1
    assert lua.eval("result.leftover[1].line") == 1
    assert lua.eval("result.leftover[1].entity_id") == 1
    assert lua.eval("#lines[1].inserted") == 3
    assert lua.eval("lines[1].inserted[1].position") == 0
    assert lua.eval("lines[1].inserted[2].position") == 0.25
    assert lua.eval("lines[1].inserted[3].position") == 0.5


def test_complete_belt_insert_returns_true():
    lua = runtime()
    load_belt(lua, 2, 10)
    assert lua.eval("result") is True
    assert lua.eval("#lines[1].inserted") == 2
    assert lua.eval("lines[1].inserted[2].position") == 0.5
