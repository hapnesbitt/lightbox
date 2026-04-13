#!/bin/bash
# claude_vid.sh — LightBox Stack Manager
# Manages the Next.js frontend Docker container for LightBox (vid.arc-codex.com)
#
# Usage:
#   ./claude_vid.sh start      Start the frontend container
#   ./claude_vid.sh stop       Stop the frontend container
#   ./claude_vid.sh restart    Restart the frontend container
#   ./claude_vid.sh status     Show container + port status
#   ./claude_vid.sh build      Rebuild the Docker image and restart
#   ./claude_vid.sh logs       Tail the frontend logs
#   ./claude_vid.sh checkup    Health check

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================
STACK_ROOT="/mnt/data/claude_vid"
FRONTEND_DIR="$STACK_ROOT/frontend"
LOG_DIR="$STACK_ROOT/logs"
COMPOSE_FILE="$STACK_ROOT/docker-compose.yml"

CONTAINER_NAME="claude-vid-frontend"
IMAGE_NAME="claude-vid-frontend:latest"
FRONTEND_PORT=3005
FLASK_PORT=5102

mkdir -p "$LOG_DIR"

# ==============================================================================
# HELPERS
# ==============================================================================
is_running() {
    docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" -q 2>/dev/null | grep -q .
}

free_port() {
    local port="$1"
    local pids
    pids=$(lsof -t -i:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "  Freeing port $port (pids: $pids)..."
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
        pids=$(lsof -t -i:"$port" 2>/dev/null || true)
        [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

check_flask() {
    if ! curl -sf "http://localhost:$FLASK_PORT/" -o /dev/null --max-time 3; then
        echo "  ⚠️  Flask backend not responding on port $FLASK_PORT — Next.js will start but won't serve data"
    else
        echo "  ✅ Flask backend OK (port $FLASK_PORT)"
    fi
}

# ==============================================================================
# COMMANDS
# ==============================================================================

cmd_start() {
    echo "🚀 Starting LightBox frontend..."

    check_flask
    free_port "$FRONTEND_PORT"

    docker compose -f "$COMPOSE_FILE" up -d --no-deps frontend >> "$LOG_DIR/frontend.log" 2>&1
    sleep 4

    if is_running; then
        echo "  ✅ Frontend running → http://localhost:$FRONTEND_PORT"
        echo "  📋 Logs: $LOG_DIR/frontend.log"
    else
        echo "  ❌ Container failed to start — check logs:"
        docker compose -f "$COMPOSE_FILE" logs --tail=30 frontend
        exit 1
    fi
}

cmd_stop() {
    echo "🛑 Stopping LightBox frontend..."
    docker compose -f "$COMPOSE_FILE" stop frontend >> "$LOG_DIR/frontend.log" 2>&1 || true
    echo "  ✅ Frontend stopped"
}

cmd_restart() {
    cmd_stop
    sleep 2
    cmd_start
}

cmd_build() {
    echo "🔨 Building LightBox frontend Docker image..."

    if is_running; then
        echo "  Stopping running container first..."
        docker compose -f "$COMPOSE_FILE" stop frontend >> "$LOG_DIR/frontend.log" 2>&1 || true
    fi

    docker compose -f "$COMPOSE_FILE" build --no-cache frontend 2>&1 | tee -a "$LOG_DIR/frontend.log"
    echo "  ✅ Build complete"

    cmd_start
}

cmd_status() {
    echo "═══════════════════════════════════════"
    echo " LightBox Stack Status"
    echo "═══════════════════════════════════════"

    # Frontend
    if is_running; then
        local cid
        cid=$(docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" -q)
        echo "  ✅ frontend    running  (container: $CONTAINER_NAME, port $FRONTEND_PORT)"
    else
        echo "  ❌ frontend    stopped"
    fi

    # Flask backend
    if curl -sf "http://localhost:$FLASK_PORT/" -o /dev/null --max-time 2 2>/dev/null; then
        echo "  ✅ flask       running  (native, port $FLASK_PORT)"
    else
        echo "  ❌ flask       not responding (port $FLASK_PORT)"
    fi

    # Port check
    echo ""
    echo "  Ports:"
    for port in $FRONTEND_PORT $FLASK_PORT; do
        local pid
        pid=$(lsof -t -i:"$port" 2>/dev/null | head -1 || true)
        if [ -n "$pid" ]; then
            local pname
            pname=$(ps -p "$pid" -o comm= 2>/dev/null || echo "?")
            echo "    :$port  ← $pname (pid $pid)"
        else
            echo "    :$port  ← not bound"
        fi
    done
    echo "═══════════════════════════════════════"
}

cmd_logs() {
    echo "📋 Frontend logs (Ctrl+C to stop)..."
    docker compose -f "$COMPOSE_FILE" logs -f frontend
}

cmd_checkup() {
    echo "🩺 LightBox health check..."

    local ok=true

    # Docker image
    if docker image inspect "$IMAGE_NAME" > /dev/null 2>&1; then
        echo "  ✅ Docker image: $IMAGE_NAME"
    else
        echo "  ⚠️  Docker image not built — run: ./claude_vid.sh build"
        ok=false
    fi

    # Container running
    if is_running; then
        echo "  ✅ Container running"
    else
        echo "  ❌ Container not running"
        ok=false
    fi

    # Frontend HTTP
    if curl -sf "http://localhost:$FRONTEND_PORT/" -o /dev/null --max-time 5; then
        echo "  ✅ Frontend HTTP OK (port $FRONTEND_PORT)"
    else
        echo "  ❌ Frontend HTTP not responding (port $FRONTEND_PORT)"
        ok=false
    fi

    # Flask
    if curl -sf "http://localhost:$FLASK_PORT/" -o /dev/null --max-time 5; then
        echo "  ✅ Flask backend OK (port $FLASK_PORT)"
    else
        echo "  ❌ Flask not responding (port $FLASK_PORT)"
        ok=false
    fi

    if $ok; then
        echo "  🟢 All systems nominal"
    else
        echo "  🔴 Issues detected — check logs: ./claude_vid.sh logs"
    fi
}

# ==============================================================================
# DISPATCH
# ==============================================================================
case "${1:-}" in
    start)   cmd_start   ;;
    stop)    cmd_stop    ;;
    restart) cmd_restart ;;
    build)   cmd_build   ;;
    status)  cmd_status  ;;
    logs)    cmd_logs    ;;
    checkup) cmd_checkup ;;
    *)
        echo "Usage: $0 {start|stop|restart|build|status|logs|checkup}"
        exit 1
        ;;
esac
