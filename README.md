# Manus AI - Local Browser Automation

A comprehensive browser automation system using local Browser-Use with a modern web interface for controlling browser tasks.

## Features

- 🖥️ **Local Browser Control**: Uses your existing Chrome browser for automation
- 🎨 **Modern Next.js Frontend**: Beautiful UI with real-time task monitoring
- ⚡ **FastAPI Backend**: High-performance API server with async support
- 📊 **Real-time Task Monitoring**: Live status updates and task control
- 🤖 **AI-Powered Automation**: Uses OpenAI or Google Gemini for intelligent browsing
- 🔗 **Cross-Platform**: Works on macOS, Windows, and Linux
- 📋 **Task History**: Complete task tracking with URLs visited and actions taken
- 🎯 **Vision-Enabled**: Screenshots and visual analysis capabilities

## Architecture

```
┌─────────────────┐    HTTP     ┌─────────────────┐    CDP     ┌─────────────────┐
│   Next.js       │ ──────────► │   FastAPI       │ ─────────► │   Chrome        │
│   Frontend      │             │   Server        │            │   Browser       │
│   (React)       │ ◄────────── │   (Python)      │ ◄────────── │   (Local)      │
└─────────────────┘   Polling   └─────────────────┘   Browser   └─────────────────┘
         │                       │                        │
         │                       │                        │
         ▼                       ▼                        ▼
    Real-time UI         Task Management           AI-Powered Browsing
    Updates              Background Tasks           Vision & Actions
```

## Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **Chrome browser** installed on your system
- **API Key** from OpenAI or Google Gemini

### 2. Get an LLM API Key

Choose one of the following:

**OpenAI:**
- Visit [OpenAI Platform](https://platform.openai.com/api-keys)
- Create a new API key
- Add to `.env`: `OPENAI_API_KEY=your_key_here`

**Google Gemini (Free):**
- Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
- Create a new API key
- Add to `.env`: `GOOGLE_API_KEY=your_key_here`

### 3. Setup

```bash
# Clone or download the project
# Set up Python virtual environment
python -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Set up environment variables
cp env.example .env
# Edit .env and add your API key (OPENAI_API_KEY or GOOGLE_API_KEY)

# Install Node.js dependencies for the frontend
cd manus-ai-clone
bun install
cd ..
```

### 4. Run Everything

```bash
# Start both backend and frontend servers
./start.sh
```

This will automatically:
- Start the Python FastAPI backend on `http://localhost:8000`
- Start the Next.js frontend on `http://localhost:3000`

Open [http://localhost:3000](http://localhost:3000) in your browser to use Manus AI.

### Manual Startup (Alternative)

If you prefer to run services separately:

```bash
# Terminal 1: Backend
source .venv/bin/activate
python api_server.py

# Terminal 2: Frontend
cd manus-ai-clone
bun run dev
```

## API Endpoints

### System Status
- `GET /health` - Health check
- `GET /api/status` - Get system status (browser, LLM, active tasks)

### Task Management
- `POST /api/tasks` - Run a new browser automation task
- `GET /api/tasks/{task_id}` - Get task details and status
- `PUT /api/tasks/{task_id}/pause` - Pause a running task (UI only)
- `PUT /api/tasks/{task_id}/resume` - Resume a paused task (UI only)
- `PUT /api/tasks/{task_id}/stop` - Stop a running task (UI only)
- `GET /api/tasks` - List all tasks (completed and active)

### Browser Control
- `POST /api/browser/initialize` - Initialize the browser
- `POST /api/browser/cleanup` - Clean up browser resources

## Usage Examples

### Basic Task Execution

```python
from main import run_browser_task
import asyncio

# Run a task directly
result = await run_browser_task("Go to duckduckgo.com and search for 'Browser Use'")
print(f"Task completed: {result}")
```

### Frontend Integration

```typescript
// Run a task from the frontend
const response = await fetch('/api/tasks', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    task: 'Search for latest AI news on Google'
  })
});

const task = await response.json();
console.log(`Task started: ${task.id}`);

// Poll for status updates
const checkStatus = async () => {
  const statusRes = await fetch(`/api/tasks/${task.id}`);
  const status = await statusRes.json();

  if (status.status === 'finished') {
    console.log('Task completed:', status.output);
    console.log('URLs visited:', status.urls_visited);
    console.log('Actions taken:', status.actions);
  } else if (status.status === 'failed') {
    console.log('Task failed:', status.error);
  }
  // Continue polling...
};
```

### Direct Browser Automation

```python
from main import LocalBrowserAutomation

automation = LocalBrowserAutomation()

# Initialize browser and LLM
await automation.initialize_browser()
await automation.initialize_llm()

# Run a custom task
result = await automation.run_task(
    "Visit GitHub and find the most starred Python repository",
    "custom-task-123"
)

print(f"Result: {result['output']}")
print(f"URLs visited: {result['urls_visited']}")
```

## Configuration

### Environment Variables

```bash
# Required: Choose ONE LLM provider
OPENAI_API_KEY=your_openai_api_key
# OR
GOOGLE_API_KEY=your_google_gemini_api_key

# Optional: FastAPI Server Configuration
PORT=8000

# Optional: Browser configuration
# BROWSER_HEADLESS=false  # Set to true to run headless
# BROWSER_WINDOW_WIDTH=1200
# BROWSER_WINDOW_HEIGHT=800

# Optional: Disable telemetry
# ANONYMIZED_TELEMETRY=false
```

### Platform-Specific Browser Paths

The system automatically detects your platform and configures Chrome paths:

**macOS:**
- Executable: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- User Data: `~/Library/Application Support/Google/Chrome`

**Windows:**
- Executable: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- User Data: `%LOCALAPPDATA%\Google\Chrome\User Data`

**Linux:**
- Executable: `/usr/bin/google-chrome`
- User Data: `~/.config/google-chrome`

## Development

### Running Tests

```bash
# Backend tests
python -m pytest

# Frontend tests
cd manus-ai-clone && npm test
```

### Code Structure

```
├── main.py                 # Simplified browser automation (MVP)
├── api_server.py          # FastAPI server using main.py browser setup
├── requirements.txt        # Python dependencies (browser-use only)
├── env.example            # Environment configuration template
├── start.sh               # Automated startup script for both services
├── manus-ai-clone/         # Next.js frontend
│   ├── app/               # Next.js app router
│   ├── components/        # React components (calls Python API)
│   └── ...
└── README.md
```

## Cost

Local browser automation costs only include your LLM API usage:

**OpenAI GPT-4.1-mini:**
- ~$0.15 per 1M input tokens
- ~$0.60 per 1M output tokens

**Google Gemini Flash (Free tier available):**
- Free tier: 15 requests/minute, 1M tokens/month
- Paid: $0.15 per 1M tokens (after free tier)

**No additional Browser-Use costs** - you only pay for LLM usage.

## Support

- 📖 [Browser-Use Documentation](https://docs.browser-use.com)
- 💬 [Discord Community](https://link.browser-use.com/discord)
- 🐛 [GitHub Issues](https://github.com/browser-use/browser-use/issues)

## License

This project integrates with Browser-Use Cloud API. See individual component licenses for details.
