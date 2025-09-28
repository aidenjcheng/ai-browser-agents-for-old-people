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

load_dotenv()

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

# Single browser instance - let browser_use launch Chrome automatically
browser = Browser(
    executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless=False,  # Set to False to see the browser
)


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
        browser_initialized=browser is not None,
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

        # Create a new agent for this task using the single browser and ChatGoogle
        task_agent = Agent(
            task=enhanced_task,
            browser=browser,
            llm=ChatOpenAI(model='gpt-4.1-mini'),
        )

        # Store task info (use original task, not enhanced)
        active_tasks[task_id] = {
            "id": task_id,
            "status": "running",
            "task": task_request.task,  # Original task for display
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

        # Clean up log data after some time (optional)
        async def cleanup_logs():
            await asyncio.sleep(300)  # Keep logs for 5 minutes
            task_logs.pop(task_id, None)
            log_listeners.pop(task_id, None)

        asyncio.create_task(cleanup_logs())


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