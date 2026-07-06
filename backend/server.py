from pydantic import BaseModel

import main as base
from news_module import generate_news, normalize_category

app = base.app

class CommunityNewsRequest(BaseModel):
    category: str = "Stocks"

@app.get('/community/news/{category}')
async def community_news(category: str):
    return await generate_news(normalize_category(category))

@app.post('/community/news')
async def community_news_post(payload: CommunityNewsRequest):
    return await generate_news(normalize_category(payload.category))
