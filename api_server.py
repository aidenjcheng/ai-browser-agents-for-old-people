"""
FastAPI server for Local Browser-Use automation
"""

import os
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager
import uuid
from browser_use import Agent, ChatOpenAI
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from browser_use import Browser

load_dotenv()

# Task tracking (similar to what was in LocalBrowserAutomation)
active_tasks: Dict[str, Dict[str, Any]] = {}

# Single browser instance - use browser_use's default launching with Chrome executable
browser = Browser(
    cdp_url="http://localhost:9222",
    executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    user_data_dir='~/Library/Application Support/Google/Chrome',
    profile_directory='Default',
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

        # Create a new agent for this task using the single browser and ChatGoogle
        task_agent = Agent(
            task=task_request.task,
            browser=browser,
            llm=ChatOpenAI(model='gpt-4.1-mini'),
        )

        # Store task info
        active_tasks[task_id] = {
            "id": task_id,
            "status": "running",
            "task": task_request.task,
            "started_at": datetime.utcnow().isoformat(),
        }

        # Run task in background
        background_tasks.add_task(run_task_async, task_id, task_agent)

        return {
            "id": task_id,
            "status": "running",
            "task": task_request.task,
            "message": "Task started successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_task_async(task_id: str, task_agent):
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
        # Note: We don't clean up the shared browser instance
        pass


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
