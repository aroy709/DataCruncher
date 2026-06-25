#!/bin/bash
# Start DataCruncher — backend and frontend simultaneously

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend on http://localhost:8000 ..."
cd "$ROOT/backend"
python3 -m uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "DataCruncher is running:"
echo "  Frontend → http://localhost:5173"
echo "  API docs  → http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
