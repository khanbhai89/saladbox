import asyncio
from saladbox.tools.browser import BrowserTool

async def test():
    tool = BrowserTool()
    res = await tool.execute("navigate", value="https://example.com")
    print(res)

asyncio.run(test())
