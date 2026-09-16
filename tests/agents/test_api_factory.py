import asyncio

import pytest

from fle.agents.llm.api_factory import APIFactory

pytestmark = pytest.mark.no_factorio


def test_client_cache_reuses_and_closes_rotated_clients():
    factory = APIFactory("deepseek-chat")
    config = {"base_url": "https://example.invalid/v1"}

    async def scenario():
        first = await factory._get_client(config, "key-1")
        assert await factory._get_client(config, "key-1") is first

        second = await factory._get_client(config, "key-2")
        assert second is not first
        assert first.is_closed()
        assert not second.is_closed()

        await second.close()
        third = await factory._get_client(config, "key-2")
        assert third is not second
        assert not third.is_closed()
        await third.close()

    asyncio.run(scenario())
