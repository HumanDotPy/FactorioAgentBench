"""Exercise the blueprint workshop on disposable servers; never attach an active run."""

from pathlib import Path
import json
import os
import uuid

from fle.envd.backend import FLEWorker
from fle.envd.models import FactorioTaskSpec
from fle.envd.reference_world import ReferenceWorld, ReferenceWorldPool
from fle.envd.service import EnvironmentService

ROOT = (
    Path(__file__).resolve().parents[1] / ".runtime" / "blueprint-workshop-validation"
)


def validate():
    ROOT.mkdir(parents=True, exist_ok=True)
    os.environ["FLE_LIFECYCLE_DIR"] = str(ROOT / "checkpoints")
    parent = ReferenceWorld(ROOT / "runtime")
    service = None
    report = {"factorio_version": "2.0.77"}
    try:
        parent.start()
        worker = FLEWorker.connect("blueprint-validation", parent.port)
        service = EnvironmentService(
            [worker],
            lease_ttl_seconds=3600,
            reference_worlds=ReferenceWorldPool(ROOT / "reference", 1),
        )
        task = FactorioTaskSpec(
            task_id="blueprint-workshop-validation",
            goal="Test blueprints",
            verifier={"implementation": "objective_engine_v1"},
            holdout_seconds=0,
            provisioning={
                "starting_inventory": {"assembling-machine-2": 2, "transport-belt": 10}
            },
            max_interventions=100,
        )
        lease = service.lease(task)
        lid = lease.lease_id

        def ref(action, **arguments):
            result = service.reference_world(lid, action, arguments, uuid.uuid4().hex)
            assert not result.get("error"), result
            return result

        def program(code):
            result = service.execute(lid, code, request_id=uuid.uuid4().hex)
            assert not result.event.error, result.event.result
            assert "'error':" not in result.event.result, result.event.result
            return result.event.result

        def lua(code):
            result = parent._call(code)
            assert not result.get("error"), result
            return result["result"]

        # Controlled terrain is seeded only in the disposable runtime process.
        lua("""local s=game.surfaces.nauvis
            for _,e in pairs(s.find_entities_filtered{area={{-30,-30},{30,30}}}) do
                if e.type~='character' then e.destroy() end
            end
            local t={}; for x=-30,30 do for y=-30,30 do
                t[#t+1]={name='grass-1',position={x,y}} end end
            s.set_tiles(t); return {}""")
        baseline_tick = worker._read_game_tick()
        ref("create")
        ref(
            "execute",
            code="""
            local a=surface.create_entity{name='assembling-machine-2',position={0.5,0.5},force=force}
            a.set_recipe('iron-gear-wheel'); a.insert{name='iron-plate',count=100}
            local power=surface.create_entity{name='electric-energy-interface',position={8,0},force=force}
            power.electric_buffer_size=100000000;power.power_production=10000000
            surface.create_entity{name='substation',position={5,5},force=force}
            return {recipe=a.get_recipe().name}
        """,
        )
        advanced = ref("run", ticks=600)
        assert advanced["advanced_ticks"] == 600, advanced
        produced = ref(
            "execute",
            code="return force.get_item_production_statistics(surface).get_input_count('iron-gear-wheel')",
        )["result"]
        assert produced > 0, produced
        assert worker._read_game_tick() == baseline_tick
        report["reference_gear_production"] = produced
        report["runtime_clock_isolated"] = True
        ref("capture", name="gear-machine", area=[[-1, -1], [2, 2]])
        assert worker.blueprint_store.get("gear-machine").entity_count == 1
        before = lua("return game.forces.player.technologies.automation.researched")
        program("print(blueprint('place','gear-machine',4,4))")
        ghosts = lua(
            "return game.surfaces.nauvis.count_entities_filtered{type='entity-ghost'}"
        )
        assert ghosts == 1, ghosts
        assert (
            lua(
                "return game.surfaces.nauvis.count_entities_filtered{name='assembling-machine-2'}"
            )
            == 0
        )
        assert before == lua(
            "return game.forces.player.technologies.automation.researched"
        )
        assert "2" in program(
            "print(inspect_inventory()[Prototype.AssemblingMachine2])"
        )
        report["native_ghosts_without_material_or_research_mutation"] = True
        # Checkpoint before construction: both pending plans and library survive.
        checkpoint = service.checkpoint(lid, "blueprint-workshop")
        ref(
            "execute",
            code="surface.find_entity('assembling-machine-2',{0.5,0.5}).destroy(); return true",
        )
        service.release(lid)
        lease = service.lease(
            task.model_copy(update={"checkpoint_id": checkpoint.checkpoint_id})
        )
        lid = lease.lease_id
        assert worker.blueprint_store.get("gear-machine").entity_count == 1
        assert (
            lua(
                "return game.surfaces.nauvis.count_entities_filtered{type='entity-ghost'}"
            )
            == 1
        )
        ref("create")
        assert (
            ref(
                "execute",
                code="return surface.find_entity('assembling-machine-2',{0.5,0.5}).get_recipe().name",
            )["result"]
            == "iron-gear-wheel"
        )
        report["checkpoint_restores_reference_library_and_ghosts"] = True
        program(
            "print(place_entity(Prototype.AssemblingMachine2, position=Position(x=4.5,y=4.5)))"
        )
        assert (
            lua(
                "return game.surfaces.nauvis.find_entity('assembling-machine-2',{4.5,4.5}).get_recipe().name"
            )
            == "iron-gear-wheel"
        )
        assert (
            lua(
                "return game.surfaces.nauvis.count_entities_filtered{type='entity-ghost'}"
            )
            == 0
        )
        report["manual_build_preserves_recipe"] = True
        ref("place", source="gear-machine", position=[15, 0])
        assert (
            ref(
                "execute",
                code="return surface.count_entities_filtered{name='assembling-machine-2'}",
            )["result"]
            == 2
        )
        report["library_reusable_in_reference"] = True
        ref(
            "execute",
            code="""
            local a=surface.find_entity('assembling-machine-2',{0.5,0.5})
            a.get_module_inventory().insert{name='speed-module',count=1}
            surface.set_tiles{{name='stone-path',position={0,0}}}
            local c1=surface.create_entity{name='constant-combinator',position={0.5,-5.5},force=force}
            local c2=surface.create_entity{name='constant-combinator',position={3.5,-5.5},force=force}
            c1.get_wire_connector(defines.wire_connector_id.circuit_red,true).connect_to(
                c2.get_wire_connector(defines.wire_connector_id.circuit_red,true))
            return true
        """,
        )
        ref("capture", name="modules-and-tile", area=[[-1, -1], [2, 2]])
        ref("capture", name="wired-pair", area=[[-1, -7], [5, -4]])
        program("print(blueprint('place','modules-and-tile',-12,-12))")
        program("print(blueprint('place','wired-pair',-15,5,direction=4))")
        assert (
            lua(
                "return game.surfaces.nauvis.count_entities_filtered{type='tile-ghost'}"
            )
            == 1
        )
        # The fixture supplies a real network; only robots may construct these.
        lua("""
            local s=game.surfaces.nauvis
            local r=s.create_entity{name='roboport',position={-5,0},force=force}
            r.insert{name='construction-robot',count=20};r.energy=100000000
            local p=s.create_entity{name='electric-energy-interface',position={-8,4},force=force}
            p.electric_buffer_size=100000000;p.power_production=10000000
            s.create_entity{name='substation',position={-5,4},force=force}
            local c=s.create_entity{name='storage-chest',position={-2.5,0.5},force=force}
            for name,count in pairs({['assembling-machine-2']=1,['speed-module']=1,
                ['stone-brick']=1,['constant-combinator']=2}) do c.insert{name=name,count=count} end
            return true
        """)
        parent.run(3600)
        assert (
            lua(
                "return game.surfaces.nauvis.count_entities_filtered{type={'entity-ghost','tile-ghost'}}"
            )
            == 0
        )
        assert (
            lua(
                "return game.surfaces.nauvis.find_entity('assembling-machine-2',{-11.5,-11.5}).get_module_inventory().get_item_count('speed-module')"
            )
            == 1
        )
        assert lua("return game.surfaces.nauvis.get_tile(-12,-12).name") == "stone-path"
        assert (
            lua("""local c=game.surfaces.nauvis.find_entities_filtered{name='constant-combinator'}[1]
            return #c.get_wire_connector(defines.wire_connector_id.circuit_red,false).connections""")
            == 1
        )
        report["robots_construct_tiles_modules_and_wired_entities"] = True
        built_checkpoint = service.checkpoint(lid, "constructed-blueprints")
        service.release(lid)
        lid = service.lease(
            task.model_copy(update={"checkpoint_id": built_checkpoint.checkpoint_id})
        ).lease_id
        assert (
            lua(
                "return game.surfaces.nauvis.find_entity('assembling-machine-2',{-11.5,-11.5}).get_module_inventory().get_item_count('speed-module')"
            )
            == 1
        )
        assert (
            lua("""local c=game.surfaces.nauvis.find_entities_filtered{name='constant-combinator'}[1]
            local connector=c.get_wire_connector(defines.wire_connector_id.circuit_red,false)
            return connector and #connector.connections or 0""")
            == 1
        )
        assert (
            lua(
                "return game.surfaces.nauvis.find_entity('roboport',{-5,0}).get_item_count('construction-robot')"
            )
            > 0
        )
        report["constructed_modules_wires_and_robots_survive_checkpoint"] = True
        planner = {
            "upgrade_planner": {
                "item": "upgrade-planner",
                "version": 562949958467584,
                "settings": {
                    "mappers": [
                        {
                            "index": 0,
                            "from": {"type": "entity", "name": "assembling-machine-2"},
                            "to": {"type": "entity", "name": "assembling-machine-3"},
                        }
                    ]
                },
            }
        }
        program(f"print(blueprint('import','upgrade-machine',{planner!r}))")
        program("print(blueprint('apply','upgrade-machine',4.5,4.5,radius=2))")
        assert lua(
            "return game.surfaces.nauvis.find_entity('assembling-machine-2',{4.5,4.5}).to_be_upgraded()"
        )
        program(
            "print(blueprint('apply','upgrade-machine',4.5,4.5,radius=2,cancel=True))"
        )
        assert not lua(
            "return game.surfaces.nauvis.find_entity('assembling-machine-2',{4.5,4.5}).to_be_upgraded()"
        )
        report["native_upgrade_planner_marks_and_cancels"] = True
        program(
            "design=blueprint('inspect','gear-machine')\n"
            "book={'blueprint_book':{'item':'blueprint-book','version':562949958467584,'blueprints':[dict(index=4,**design)]}}\n"
            "print(blueprint('import','book',book))\n"
            "print(blueprint('place','book',20,20,book_path=[4]))"
        )
        assert (
            lua(
                "return game.surfaces.nauvis.count_entities_filtered{type='entity-ghost'}"
            )
            == 1
        )
        program("print(blueprint('delete','book'))")
        assert worker.blueprint_store.try_get("book") is None
        report["native_book_import_selection_and_delete"] = True
        planner = {
            "deconstruction_planner": {
                "item": "deconstruction-planner",
                "version": 562949958467584,
                "settings": {
                    "entity_filters": [{"index": 0, "name": "constant-combinator"}]
                },
            }
        }
        program(f"print(blueprint('import','remove-combinators',{planner!r}))")
        program("print(blueprint('apply','remove-combinators',-15,5,radius=10))")
        assert lua(
            "return game.surfaces.nauvis.find_entities_filtered{name='constant-combinator'}[1].to_be_deconstructed(force)"
        )
        program(
            "print(blueprint('apply','remove-combinators',-15,5,radius=10,cancel=True))"
        )
        assert not lua(
            "return game.surfaces.nauvis.find_entities_filtered{name='constant-combinator'}[1].to_be_deconstructed(force)"
        )
        report["native_deconstruction_planner_marks_and_cancels"] = True
        service.release(lid)
        lid = service.lease(task).lease_id
        tiles = {
            "blueprint": {
                "item": "blueprint",
                "version": 562949958467584,
                "tiles": [
                    {"name": "stone-path", "position": {"x": 0, "y": 0}},
                    {"name": "stone-path", "position": {"x": 1, "y": 0}},
                ],
            }
        }
        program(
            f"print(blueprint('import','tiles',{tiles!r}))\nprint(blueprint('place','tiles',10,10))"
        )
        positions_before = lua(
            "local r={}; for _,g in ipairs(game.surfaces.nauvis.find_entities_filtered{type='tile-ghost'}) do r[#r+1]=g.position end;return r"
        )
        assert len(positions_before) == 2
        checkpoint = service.checkpoint(lid, "tiles-only")
        service.release(lid)
        lid = service.lease(
            task.model_copy(update={"checkpoint_id": checkpoint.checkpoint_id})
        ).lease_id
        positions_after = lua(
            "local r={}; for _,g in ipairs(game.surfaces.nauvis.find_entities_filtered{type='tile-ghost'}) do r[#r+1]=g.position end;return r"
        )
        assert sorted(positions_before, key=lambda p: p["x"]) == sorted(
            positions_after, key=lambda p: p["x"]
        )
        report["tile_only_checkpoint_preserves_positions"] = True
        (ROOT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        if service:
            service.close()
        parent.close()


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
