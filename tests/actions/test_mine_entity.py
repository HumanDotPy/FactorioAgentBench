from pathlib import Path
from unittest.mock import Mock

import pytest
from lupa.lua54 import LuaRuntime

from fle.env.entities import Position
from fle.env.tools.agent.mine_entity.client import MineEntity

pytestmark = pytest.mark.no_factorio


def runtime():
    lua = LuaRuntime()
    lua.execute("""
        storage={actions={},agent_characters={},utils={},fast=true,
            elapsed_ticks=0,harvested_items={},manual_production_events={}}
        game={tick=777,surfaces={}}
        defines={inventory={character_main=1}}

        found={}
        inserted={}
        flow={}

        function make_force(name)
            return {name=name,get_item_production_statistics=function(surface)
                return {on_flow=function(product,amount)
                    flow[#flow+1]={name=product,amount=amount}
                end}
            end}
        end

        function make_entity(props)
            local e=props
            e.valid=true
            e.mined=false
            e.destroyed=false
            e.mine=function(options)
                e.mined=true
                e.mine_options=options
                e.valid=false
            end
            e.destroy=function()
                e.destroyed=true
                e.valid=false
            end
            e.can_be_destroyed=function() return e.destroyable~=false end
            return e
        end

        insert_blocked={}
        inventory={can_insert=function(stack) return not insert_blocked[stack.name] end}
        surface={find_entities_filtered=function(query) return found end}
        player={
            position={x=0,y=0},
            resource_reach_distance=2.5,
            force=make_force('player'),
            surface=surface,
            get_main_inventory=function() return inventory end,
            insert=function(stack)
                if insert_blocked[stack.name] then return 0 end
                inserted[#inserted+1]={name=stack.name,count=stack.count}
                return stack.count
            end,
        }
        storage.agent_characters[1]=player
        game.surfaces[1]=surface
    """)
    lua.execute(
        (
            Path(__file__).parents[2] / "fle/env/tools/agent/mine_entity/server.lua"
        ).read_text()
    )
    return lua


def test_tree_with_products_is_mined_and_counted():
    lua = runtime()
    lua.execute("""
        tree=make_entity({
            name='tree-01', type='tree', position={x=0.5,y=0}, force='neutral',
            minable=true,
            prototype={mineable_properties={mining_time=0.5,
                products={{name='wood',amount=2}}}},
        })
        found[1]=tree
        result=storage.actions.mine_entity(1,0,0,'tree-01')
        assert(result.removed==true)
        assert(result.name=='tree-01')
        assert(result.position.x==0.5 and result.position.y==0)
        assert(result.items.wood==2)
        assert(tree.mined)
        assert(tree.destroyed==false)
        assert(tree.mine_options.ignore_minable==false)
        assert(tree.mine_options.raise_destroyed==true)
        assert(#inserted==1 and inserted[1].name=='wood' and inserted[1].count==2)
        assert(storage.elapsed_ticks==30)
        assert(flow[1].name=='wood' and flow[1].amount==2)
        assert(storage.harvested_items.wood==2)
        assert(storage.manual_production_events[1].tick==777)
        assert(storage.manual_production_events[1].kind=='harvested')
        assert(storage.manual_production_events[1].outputs.wood==2)
    """)


def test_rock_with_products_is_mined_and_counted():
    lua = runtime()
    lua.execute("""
        rock=make_entity({
            name='big-rock', type='simple-entity', position={x=1,y=1},
            force='neutral', minable=true,
            prototype={mineable_properties={mining_time=0.75,
                products={{name='stone',amount=20}}}},
        })
        found[1]=rock
        result=storage.actions.mine_entity(1,1,1,'big-rock')
        assert(result.name=='big-rock')
        assert(result.items.stone==20)
        assert(rock.mined)
        assert(#inserted==1 and inserted[1].name=='stone' and inserted[1].count==20)
        assert(storage.elapsed_ticks==45)
        assert(flow[1].name=='stone' and flow[1].amount==20)
    """)


def test_stump_without_products_is_destroyed():
    lua = runtime()
    lua.execute("""
        stump=make_entity({
            name='tree-01-stump', type='corpse', position={x=0,y=0},
            force='neutral', minable=false,
        })
        found[1]=stump
        result=storage.actions.mine_entity(1,0,0,'tree-01-stump')
        assert(result.removed==true)
        assert(result.name=='tree-01-stump')
        assert(stump.destroyed and not stump.mined)
        assert(next(result.items)==nil)
        assert(storage.elapsed_ticks==0)
        assert(#inserted==0)
    """)


def test_minable_corpse_without_products_is_destroyed():
    lua = runtime()
    lua.execute("""
        corpse=make_entity({
            name='dead-tree-desert', type='corpse', position={x=0,y=0},
            force='neutral', minable=true,
            prototype={mineable_properties={mining_time=0.5,products={}}},
        })
        found[1]=corpse
        result=storage.actions.mine_entity(1,0,0,'dead-tree-desert')
        assert(result.removed==true)
        assert(corpse.destroyed and not corpse.mined)
        assert(next(result.items)==nil)
    """)


def test_missing_target_returns_actionable_error():
    lua = runtime()
    lua.execute("""
        ok,message=pcall(function()
            return storage.actions.mine_entity(1,5,5,'tree-01')
        end)
        assert(ok==false)
        assert(string.find(message,'Nothing neutral to mine',1,true)~=nil)
        assert(string.find(message,'5.0, 5.0',1,true)~=nil)
    """)


def test_out_of_reach_target_returns_actionable_error():
    lua = runtime()
    lua.execute("""
        tree=make_entity({
            name='tree-01', type='tree', position={x=10,y=0}, force='neutral',
            minable=true,
            prototype={mineable_properties={mining_time=0.5,
                products={{name='wood',amount=2}}}},
        })
        found[1]=tree
        ok,message=pcall(function()
            return storage.actions.mine_entity(1,10,0,'tree-01')
        end)
        assert(ok==false)
        assert(string.find(message,'beyond your 2.5 tile reach',1,true)~=nil)
        assert(not tree.mined and not tree.destroyed)
    """)


def test_non_neutral_entity_is_refused():
    lua = runtime()
    lua.execute("""
        corpse=make_entity({
            name='character-corpse', type='corpse', position={x=0,y=0},
            force='player', minable=true,
            prototype={mineable_properties={mining_time=0.5,
                products={{name='iron-plate',amount=5}}}},
        })
        found[1]=corpse
        ok,message=pcall(function()
            return storage.actions.mine_entity(1,0,0,'character-corpse')
        end)
        assert(ok==false)
        assert(string.find(message,'non-neutral',1,true)~=nil)
        assert(not corpse.mined and not corpse.destroyed)
    """)


def test_full_inventory_refuses_mining():
    lua = runtime()
    lua.execute("""
        insert_blocked.wood=true
        tree=make_entity({
            name='tree-01', type='tree', position={x=0,y=0}, force='neutral',
            minable=true,
            prototype={mineable_properties={mining_time=0.5,
                products={{name='wood',amount=2}}}},
        })
        found[1]=tree
        ok,message=pcall(function()
            return storage.actions.mine_entity(1,0,0,'tree-01')
        end)
        assert(ok==false)
        assert(string.find(message,'Inventory is full',1,true)~=nil)
        assert(not tree.mined)
        assert(storage.elapsed_ticks==0)
    """)


def test_named_entity_is_preferred_over_closer_neutral():
    lua = runtime()
    lua.execute("""
        rock=make_entity({
            name='big-rock', type='simple-entity', position={x=0.4,y=0},
            force='neutral', minable=true,
            prototype={mineable_properties={mining_time=0.75,
                products={{name='stone',amount=20}}}},
        })
        tree=make_entity({
            name='tree-01', type='tree', position={x=1.2,y=0}, force='neutral',
            minable=true,
            prototype={mineable_properties={mining_time=0.5,
                products={{name='wood',amount=2}}}},
        })
        found[1]=rock
        found[2]=tree
        result=storage.actions.mine_entity(1,0,0,'tree-01')
        assert(result.name=='tree-01')
        assert(result.items.wood==2)
        assert(tree.mined and not rock.mined)
    """)


def test_client_resolves_fresh_entity_and_passes_arguments():
    tool = MineEntity.__new__(MineEntity)
    tool.player_index = 1
    tool.execute = Mock(
        return_value=(
            {
                "name": "tree-01",
                "position": {"x": 0.5, "y": 0.0},
                "items": {"wood": 2},
                "removed": True,
            },
            0,
        )
    )
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.game_state.instance.get_elapsed_ticks.return_value = 0
    tool.name = "mine_entity"
    fresh = Mock()
    fresh.name = "tree-01"
    fresh.position = Position(x=0.5, y=0.0)
    tool.game_state.resolve_entity.return_value = fresh
    stale = Mock()
    stale.id = 9

    result = tool(stale)

    tool.game_state.resolve_entity.assert_called_once_with(stale)
    tool.execute.assert_called_once_with(1, 0.5, 0.0, "tree-01")
    assert result["items"] == {"wood": 2}


def test_client_accepts_position_and_passes_no_name():
    tool = MineEntity.__new__(MineEntity)
    tool.player_index = 1
    tool.execute = Mock(
        return_value=(
            {
                "name": "big-rock",
                "position": {"x": 1, "y": 1},
                "items": {"stone": 20},
                "removed": True,
            },
            0,
        )
    )
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.game_state.instance.get_elapsed_ticks.return_value = 0
    tool.name = "mine_entity"

    result = tool(Position(x=1, y=1))

    tool.game_state.resolve_entity.assert_not_called()
    tool.execute.assert_called_once_with(1, 1, 1, None)
    assert result["removed"] is True


def test_client_raises_on_server_error():
    tool = MineEntity.__new__(MineEntity)
    tool.player_index = 1
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    tool.game_state.instance.get_elapsed_ticks.return_value = 0
    tool.name = "mine_entity"
    entity = Mock()
    entity.id = None
    entity.name = "tree-01"
    entity.position = Position(x=0, y=0)

    tool.execute = Mock(
        return_value=("server.lua:100: Nothing neutral to mine at (0.0, 0.0)", 0)
    )
    with pytest.raises(Exception, match="Could not mine entity at"):
        tool(entity)

    tool.execute = Mock(return_value=({"error": "Player not found"}, 0))
    with pytest.raises(Exception, match="Player not found"):
        tool(entity)


def test_client_rejects_non_entity_target():
    tool = MineEntity.__new__(MineEntity)
    tool.game_state = Mock()
    tool.game_state._program_runtime = None
    with pytest.raises(TypeError, match="Entity or Position"):
        tool((1, 2))
