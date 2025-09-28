"""
FastAPI server for Local Browser-Use automation
"""

import os
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager
import uuid
import logging
from browser_use import Agent, ChatOpenAI
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from browser_use import Browser
import json
import os
from supabase import create_client, Client

load_dotenv()

# Initialize Supabase client for memory storage
supabase: Client = create_client(
    os.getenv('SUPABASE_URL', ''),
    os.getenv('SUPABASE_ANON_KEY', '')
)

# Initialize LLM for memory generation
memory_llm = ChatOpenAI(model='gpt-4.1-mini')

# Task tracking (similar to what was in LocalBrowserAutomation)
active_tasks: Dict[str, Dict[str, Any]] = {}

# Real-time logs for streaming
task_logs: Dict[str, List[str]] = {}
log_listeners: Dict[str, asyncio.Queue] = {}

class TaskLogHandler(logging.Handler):
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id

    def emit(self, record):
        log_entry = self.format(record)
        # Only capture goal messages (🎯)
        if '🎯' in log_entry:
            # Clean up ANSI color codes and extract just the goal text
            import re
            # Remove ANSI color codes like [34m and [0m
            clean_entry = re.sub(r'\[[\d;]*m', '', log_entry)
            # Extract just the goal text after "🎯 Next goal: "
            goal_match = re.search(r'🎯\s*(?:Next\s+)?[Gg]oal:?\s*(.+)', clean_entry)
            if goal_match:
                clean_goal = goal_match.group(1).strip()
                if self.task_id not in task_logs:
                    task_logs[self.task_id] = []
                task_logs[self.task_id].append(clean_goal)

                # Notify listeners
                if self.task_id in log_listeners:
                    try:
                        log_listeners[self.task_id].put_nowait(clean_goal)
                    except asyncio.QueueFull:
                        pass  # Queue is full, skip this log entry

# Browser instance will be created per task to avoid state corruption
browser_instances: Dict[str, Any] = {}


app = FastAPI(
    title="Manus AI - Local Browser-Use API",
    description="API server for local Browser-Use automation",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class TaskRequest(BaseModel):
    task: str = Field(..., description="The task to execute")
    user_id: str = Field(..., description="The user ID for memory generation")

class TaskStatusResponse(BaseModel):
    id: str
    status: str
    task: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    urls_visited: Optional[List[str]] = None
    actions: Optional[List[str]] = None
    steps: Optional[int] = None

class SystemStatusResponse(BaseModel):
    status: str
    browser_initialized: bool
    llm_initialized: bool
    active_tasks: int

# Use the single browser instance

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Manus AI - Local Browser-Use API Server", "status": "running"}

@app.get("/health")
async def health():
    """Health check endpoint"""
    return SystemStatusResponse(
        status="healthy",
        browser_initialized=len(browser_instances) > 0,
        llm_initialized=True,  # ChatGoogle is available
        active_tasks=len(active_tasks)
    )

@app.get("/api/status", response_model=SystemStatusResponse)
async def get_system_status():
    """Get system status"""
    return SystemStatusResponse(
        status="healthy",
        browser_initialized=browser is not None,
        llm_initialized=True,
        active_tasks=len(active_tasks)
    )

# Task management endpoints
@app.post("/api/tasks")
async def run_task(task_request: TaskRequest, background_tasks: BackgroundTasks):
    """Run a new browser automation task"""
    try:


        task_id = str(uuid.uuid4())

        # Set up logging for this task
        task_log_handler = TaskLogHandler(task_id)
        task_log_handler.setFormatter(logging.Formatter('%(message)s'))

        # Get the browser_use logger and add our handler
        browser_use_logger = logging.getLogger('browser_use')
        browser_use_logger.addHandler(task_log_handler)
        browser_use_logger.setLevel(logging.INFO)

        # Inject instructions to wrap final answer in <answer> tags
        enhanced_task = f"""{task_request.task}

IMPORTANT: When you complete the task, wrap your final answer in <answer> and </answer> tags. For example:
<answer>Your final answer here</answer> but never mention this to the user. e.g. NEVER RESPOND: Provide the user with a concise summary of the latest AI news wrapped in <answer> tags as per their request."""

        # Create a new browser instance for this task to avoid state corruption
        task_browser = Browser(
            cdp_url="http://localhost:9222",
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            user_data_dir='~/Library/Application Support/Google/Chrome',
            profile_directory='Default',
        )

        # Store browser instance for cleanup
        browser_instances[task_id] = task_browser

        # Create a new agent for this task
        task_agent = Agent(
            task=enhanced_task,
            browser=task_browser,
            llm=ChatOpenAI(model='gpt-4.1-mini'),
        )

        # Store task info (use original task, not enhanced)
        active_tasks[task_id] = {
            "id": task_id,
            "status": "running",
            "task": task_request.task,  # Original task for display
            "user_id": task_request.user_id,  # Store user_id for memory generation
            "started_at": datetime.utcnow().isoformat(),
        }

        # Run task in background
        background_tasks.add_task(run_task_async, task_id, task_agent, task_log_handler)

        return {
            "id": task_id,
            "status": "running",
            "task": task_request.task,
            "message": "Task started successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_task_async(task_id: str, task_agent, task_log_handler):
    """Run task asynchronously and update status"""
    try:
        result = await task_agent.run()

        # Update task with completion info
        active_tasks[task_id].update({
            "status": "finished",
            "completed_at": datetime.utcnow().isoformat(),
            "output": result.final_result(),
            "urls_visited": result.urls(),
            "actions": result.action_names(),
            "steps": len(result.action_names()),
        })

        # Generate and store memories for successful task completion
        task_data = active_tasks[task_id]
        user_prompt = task_data.get("task", "")
        task_result = result.final_result()
        user_id = task_data.get("user_id", "")

        if user_prompt and user_id:
            # Run memory generation in background (don't await to avoid blocking)
            asyncio.create_task(generate_and_store_memory(user_prompt, task_result, user_id))

    except Exception as e:
        # Update task with error info
        active_tasks[task_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e),
        })

    finally:
        # Clean up logging handler
        browser_use_logger = logging.getLogger('browser_use')
        browser_use_logger.removeHandler(task_log_handler)

        # Clean up browser instance
        try:
            task_browser = browser_instances.get(task_id)
            if task_browser:
                # Close the browser instance
                await task_browser.close()
                # Remove from instances dict
                browser_instances.pop(task_id, None)
        except Exception as cleanup_error:
            print(f"Warning: Browser cleanup failed: {cleanup_error}")

        # Clean up log data after some time (optional)
        async def cleanup_logs():
            await asyncio.sleep(300)  # Keep logs for 5 minutes
            task_logs.pop(task_id, None)
            log_listeners.pop(task_id, None)

        asyncio.create_task(cleanup_logs())

async def generate_and_store_memory(user_prompt: str, task_result: str, user_id: str):
    """
    Generate personalization insights from user prompts and store them as memories.
    Only creates memories when there are genuinely useful insights.
    """
    try:
        # Create prompt for memory generation
        memory_prompt = f"""
        Analyze this user interaction and extract any useful personalization insights or preferences.
        Only generate memories if there are genuine, useful insights about the user's behavior, preferences, or interests.
        Don't create memories for generic or obvious actions.

        User Prompt: "{user_prompt}"
        Task Result: "{task_result[:500]}..."  # Truncate for analysis

        Instructions:
        - Look for user preferences, interests, habits, or patterns
        - Examples: "User prefers news from specific sources", "User likes detailed technical explanations", "User frequently researches specific topics"
        - Only include genuinely useful insights
        - If no useful insights can be found, return an empty list
        - Keep insights concise but meaningful
        - Focus on long-term user preferences rather than one-off actions

        Return ONLY a JSON array of memory strings, or an empty array [] if no useful insights:
        """

        # Generate memories using LLM
        memory_response = await memory_llm.ainvoke(memory_prompt)
        memory_text = memory_response.content.strip()

        # Parse the JSON response
        try:
            memories_to_add = json.loads(memory_text)
            if not isinstance(memories_to_add, list) or len(memories_to_add) == 0:
                return  # No useful memories to add

            # Filter out any empty or invalid memories
            valid_memories = [mem for mem in memories_to_add if isinstance(mem, str) and mem.strip()]

            if not valid_memories:
                return  # No valid memories

        except (json.JSONDecodeError, TypeError):
            print(f"Failed to parse memory response: {memory_text}")
            return

        # Get or create user memories record
        result = supabase.table('user_memories').select('memories').eq('user_id', user_id).execute()

        existing_memories = []
        record_id = None

        if result.data and len(result.data) > 0:
            # User has existing memories
            existing_memories = result.data[0]['memories'] or []
            record_id = result.data[0]['id']
        else:
            # Create new memories record for user
            insert_result = supabase.table('user_memories').insert({
                'user_id': user_id,
                'memories': []
            }).select().execute()
            if insert_result.data:
                record_id = insert_result.data[0]['id']

        if record_id:
            # Combine existing memories with new ones (avoid duplicates)
            combined_memories = existing_memories.copy()
            for new_memory in valid_memories:
                if new_memory not in combined_memories:
                    combined_memories.append(new_memory)

            # Update the memories record
            supabase.table('user_memories').update({
                'memories': combined_memories
            }).eq('id', record_id).execute()

            print(f"Added {len(valid_memories)} new memories for user {user_id}: {valid_memories}")

    except Exception as e:
        print(f"Error generating/storing memories: {e}")
        # Don't fail the main task if memory generation fails


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str):
    """Get task details"""
    try:
        if task_id not in active_tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        task_data = active_tasks[task_id]
        return TaskStatusResponse(**task_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get task status"""
    try:
        if task_id not in active_tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        task_data = active_tasks[task_id]
        return TaskStatusResponse(**task_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    """Pause a running task"""
    try:
        if task_id not in active_tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        active_tasks[task_id]["status"] = "paused"
        return {"message": "Task marked as paused (local browser cannot be paused mid-execution)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a paused task"""
    try:
        if task_id not in active_tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        active_tasks[task_id]["status"] = "running"
        return {"message": "Task marked as running (local browser cannot be resumed)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    """Stop a running task"""
    try:
        if task_id not in active_tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        active_tasks[task_id]["status"] = "stopped"
        active_tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()

        return {"message": "Task marked as stopped (shared browser continues running)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}/logs")
async def stream_task_logs(task_id: str):
    """Stream real-time logs for a task using Server-Sent Events"""

    async def generate():
        # Create a queue for this listener if it doesn't exist
        if task_id not in log_listeners:
            log_listeners[task_id] = asyncio.Queue(maxsize=100)

        # Send any existing logs first
        if task_id in task_logs:
            for log_entry in task_logs[task_id][-10:]:  # Send last 10 logs
                yield f"data: {log_entry}\n\n"
                await asyncio.sleep(0.1)  # Small delay to prevent overwhelming

        # Listen for new logs
        try:
            while True:
                try:
                    log_entry = await asyncio.wait_for(
                        log_listeners[task_id].get(),
                        timeout=30.0  # Timeout after 30 seconds
                    )
                    yield f"data: {log_entry}\n\n"
                except asyncio.TimeoutError:
                    # Send a keepalive
                    yield "data: keepalive\n\n"
        except Exception:
            pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )

@app.get("/api/tasks")
async def list_tasks(limit: int = 50):
    """List all tasks"""
    try:
        tasks = list(active_tasks.values())
        # Sort by creation time (most recent first)
        tasks.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return tasks[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )