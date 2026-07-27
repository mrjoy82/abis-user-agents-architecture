from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import httpx
import json
import asyncio

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "gemma4:31b-cloud"

@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connected")
    
    try:
        while True:
            message = await websocket.receive_text()
            print(f"Received: {message[:80]}...")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    OLLAMA_URL,
                    json={"model": MODEL, "prompt": message, "stream": True}
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    await websocket.send_text(data["response"])
                            except json.JSONDecodeError:
                                pass
            
            await websocket.send_text("\n---DONE---\n")
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        print("WebSocket closed")

@app.get("/")
async def root():
    return {"message": "ATA Prototype. Visit /static/index.html"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7884)
