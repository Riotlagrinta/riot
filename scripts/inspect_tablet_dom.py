import asyncio
import subprocess
from playwright.async_api import async_playwright

adb = r"C:\Users\LENOVO\AppData\Local\Android\Sdk\platform-tools\adb.exe"

async def inspect():
    subprocess.run([adb, "-s", "G001KT0511960C98", "forward", "tcp:9223", "localabstract:chrome_devtools_remote"], check=True)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "dashboard" in pg.url or "kelvix" in pg.url:
                page = pg
                break
        if not page:
            page = ctx.pages[0]
        
        print("Page URL:", page.url)
        print("Page Title:", await page.title())
        buttons = await page.locator("button").all_inner_texts()
        print("Buttons found:", buttons)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
