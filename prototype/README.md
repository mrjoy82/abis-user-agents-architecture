# ATA Prototype

Dirty throwaway code to validate: Can a Docker container on Pi 5 run FastAPI + WebSocket, call an Ollama cloud model, and stream the response back in real-time?

## Build

```bash
cd prototype/ata
sudo docker build -t abis-ata-base .
```

## Run

```bash
sudo docker run -d --name ata-proto --network=host abis-ata-base
```

## Test

Open browser: http://pi-agent:7884/static/index.html

Or test via Python:

```python
import asyncio, websockets

async def test():
    async with websockets.connect('ws://localhost:7884/ws/chat') as ws:
        await ws.send('What is 2+2?')
        response = ''
        while True:
            chunk = await asyncio.wait_for(ws.recv(), timeout=10.0)
            if '---DONE---' in chunk: break
            response += chunk
        print(f'Response: {response}')

asyncio.run(test())
```

## Stop

```bash
sudo docker stop ata-proto && sudo docker rm ata-proto
```

## Known Issues
- Uses `--network=host` (prototype only). Production will use proper Docker networking.
- No auth, no orchestrator, no safety scanning.
- Hardcoded Ollama URL (`127.0.0.1:11434`).
- Single model (`gemma4:31b-cloud`).
