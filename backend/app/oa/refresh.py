import asyncio

from app.oa.crawler import refresh_oa_notices


async def main() -> None:
    result = await refresh_oa_notices()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
