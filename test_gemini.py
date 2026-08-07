import asyncio
import time
from services.llm_service import LLMService


async def main():
    llm = LLMService()

    start = time.perf_counter()

    text = await llm.generate_response_async("Say hello in one short sentence.")

    print(text)
    print(f"Total time: {time.perf_counter()-start:.2f}s")


asyncio.run(main())
