from fle.env.game_types import Resource


def test_production_stats(instance):
    instance.namespace.move_to(instance.namespace.nearest(Resource.IronOre))
    instance.namespace.harvest_resource(
        instance.namespace.nearest(Resource.IronOre), quantity=10
    )

    result = instance.namespace._get_production_stats()

    # Harvested resources are tracked in the 'harvested' key
    assert result["harvested"]["iron-ore"] == 10

    # Harvest more to verify stats accumulate
    instance.namespace.harvest_resource(
        instance.namespace.nearest(Resource.IronOre), quantity=5
    )
    result = instance.namespace._get_production_stats()

    # Stats should accumulate (10 + 5 = 15)
    assert result["harvested"]["iron-ore"] == 15
