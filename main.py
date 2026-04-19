import os
import csv
import json
import logging
import time
from typing import Optional
from dotenv import load_dotenv
import httpx
from openai import OpenAI
from pydantic import BaseModel

# Логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Конфігурація
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
INPUT_FILE = os.getenv("INPUT_FILE", "products.txt")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "result.csv")

if not GITHUB_TOKEN or not SERPAPI_KEY:
    logger.error("Відсутні ключі (GITHUB_TOKEN або SERPAPI_KEY) у файлі .env")
    exit(1)

# Клієнт для GitHub Models
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN
)


class VarusItem(BaseModel):
    title: str
    url: str


class MatchResult(BaseModel):
    is_found: bool
    best_match_title: Optional[str] = None
    best_match_url: Optional[str] = None
    item_capacity: Optional[float] = None


class SerpApiVarusSearcher:
    """Використовує SerpApi для отримання результатів пошуку Google."""

    @staticmethod
    def search(query: str) -> list[VarusItem]:
        search_query = f"site:varus.ua {query}"

        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": search_query,
            "google_domain": "google.com.ua",
            "gl": "ua",
            "hl": "uk",
            "api_key": SERPAPI_KEY
        }

        try:
            with httpx.Client() as h_client:
                resp = h_client.get(url, params=params, timeout=15.0)

            if resp.status_code != 200:
                logger.error(f"SerpApi Error: {resp.status_code}")
                return []

            data = resp.json()
            items = []
            results = data.get("organic_results", [])

            for result in results:
                link = result.get("link").split("?")[0]
                title = result.get("title", "").replace(" - Varus", "").replace(" | Varus", "").strip()

                if link and "varus.ua" in link and "/search/" not in link:
                    items.append(VarusItem(title=title, url=link))

            return items
        except Exception as e:
            logger.error(f"Помилка SerpApi: {e}")
            return []


class AIProductMatcher:
    @staticmethod
    def match(requirement: str, found_items: list[VarusItem]) -> Optional[MatchResult]:
        if not found_items:
            return MatchResult(is_found=False)

        items_str = "\n".join([f"- Назва: {it.title} | Посилання: {it.url}" for it in found_items])

        prompt = f"""
        Запит користувача: {requirement}
        Доступні товари на Varus:
        {items_str}

        Твоє завдання:
        1. Пріоритет: Якщо користувач шукає базовий продукт (банани, полуниця), обирай свіжий товар (ваговий), а не в'ялений, сушений чи заморожений.
        2. Суворість: Якщо жоден товар не відповідає суті запиту (наприклад, замість м'яса пропонують приправу), поверни is_found: false.
        3. Очищення: У полі 'best_match_title' пиши чисту назву без зайвих слів 'купити онлайн', 'замовити в супермаркеті'.

        Відповідай ТІЛЬКИ JSON:
        {{
            "is_found": bool,
            "best_match_title": "Назва товару",
            "best_match_url": "URL",
            "item_capacity": float
        }}
        """
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system",
                           "content": "Ти помічник закупника Varus. Завжди намагайся знайти відповідність."},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0
            )
            content = response.choices[0].message.content
            data = json.loads(content)

            return MatchResult(
                is_found=data.get("is_found", False),
                best_match_title=data.get("best_match_title"),
                best_match_url=data.get("best_match_url"),
                item_capacity=data.get("item_capacity")
            )
        except Exception as e:
            logger.error(f"Помилка матчингу: {e}")
            return MatchResult(is_found=False)


def main():
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Файл {INPUT_FILE} не знайдено!")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    results = []
    for line in lines:
        logger.info(f"--- Обробка: {line} ---")

        # Пошук (тільки назва до коми)
        search_query = line.split(',')[0].strip()
        found_items = SerpApiVarusSearcher.search(search_query)

        # AI матчінг
        match = AIProductMatcher.match(line, found_items)

        if match and match.is_found and match.best_match_title:
            results.append({
                "Продукт": line,
                "Товар": match.best_match_title,
                "Посилання": match.best_match_url
            })
            logger.info(f"Успішно знайдено: {match.best_match_title}")
        else:
            results.append({"Продукт": line, "Товар": "Не знайдено", "Посилання": "-"})
            logger.warning(f"Товар для '{line}' не підібрано.")

        time.sleep(0.5)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Продукт", "Товар", "Посилання"])
        writer.writeheader()
        writer.writerows(results)
    logger.info(f"Готово! Результати в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()