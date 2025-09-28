#!/bin/bash

# Manus AI Startup Script
echo "🚀 Starting Manus AI (Local Browser Mode)..."

# Start backend API server in background
echo "🔧 Starting FastAPI backend server..."
source .venv/bin/activate
python api_server.py &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

# Check if backend started successfully
# if ! curl -s http://localhost:8000/health > /dev/null; then
#     echo "❌ Backend server failed to start"
#     kill $BACKEND_PID 2>/dev/null
#     exit 1
# fi



echo "✅ Backend server running on http://localhost:8000"

# Start frontend in background
echo "🎨 Starting Next.js frontend..."
cd manus-ai-clone
bun run dev &
FRONTEND_PID=$!

# Wait a moment for frontend to start
sleep 5

echo "✅ Frontend server running on http://localhost:3000"
echo ""
echo "🎉 Manus AI (Local Browser Mode) is now running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend API: http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Your Chrome browser will open automatically for automation tasks."
echo "Press Ctrl+C to stop all servers"

# Wait for Ctrl+C
trap "echo '🛑 Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
