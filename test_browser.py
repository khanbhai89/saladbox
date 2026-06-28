import asyncio

from saladbox.tools.browser import BrowserTool


async def main():
    b = BrowserTool()
    res1 = await b.execute("google_search", value="cat video")
    print("SEARCH RESULTS:", res1[:200])

    res2 = await b.execute("navigate", value="https://www.youtube.com/watch?v=cbP2N1BQdYc")
    print("NAVIGATE RESULT:", res2[:200])

asyncio.run(main())
