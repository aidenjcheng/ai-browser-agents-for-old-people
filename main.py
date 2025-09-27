from browser_use import Agent, Browser, ChatOpenAI, ChatGoogle
from dotenv import load_dotenv
import asyncio


load_dotenv()

# Connect to your existing Chrome browser
browser = Browser(
    cdp_url="http://localhost:9222",
    executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    user_data_dir='~/Library/Application Support/Google/Chrome',
    profile_directory='Default',
)

agent = Agent(
    task='Visit https://duckduckgo.com and search for "browser-use founders", then go to google translate then translate the results to mandarin and return the results and press the listen button',
    browser=browser,
    llm=ChatOpenAI(model='gpt-4.1-mini'),
    # llm = ChatGoogle(model="gemini-flash-latest"),
)

async def main():
    await agent.run()
if __name__ == "__main__":
    asyncio.run(main())