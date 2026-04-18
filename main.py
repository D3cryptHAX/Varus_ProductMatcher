import os
import csv
import math
import json
import logging
from typing import Optional
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
INPUT_FILE = os.getenv("INPUT_FILE", "products.txt")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "result.csv")

if not GITHUB_TOKEN:
    logger.error("Не знайдено GITHUB_TOKEN у файлі .env")
    exit(1)

client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=GITHUB_TOKEN
)

MODEL_NAME = "gpt-4o-mini"


class ParsedProduct(BaseModel):
    original_text: str
    name: str
    quantity: float
    unit: str


class VarusItem(BaseModel):
    title: str
    url: str


class MatchResult(BaseModel):
    is_found: bool
    best_match_title: Optional[str] = None
    best_match_url: Optional[str] = None
    item_capacity: Optional[float] = None
    explanation: Optional[str] = None


class ProductParser:
    """Нормалізація через GitHub Models."""

    @staticmethod
    def parse_line(line: str) -> Optional[ParsedProduct]:
        prompt = f"Розпарси рядок продукту: '{line}'. Поверни JSON (name, quantity, unit: шт/гр/кг)."
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Ти — парсер даних. Відповідай суворо в JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return ParsedProduct(
                original_text=line,
                name=data.get("name"),
                quantity=float(data.get("quantity", 0)),
                unit=data.get("unit")
            )
        except Exception as e:
            logger.error(f"Помилка парсингу: {e}")
            return None


class VarusScraper:
    """Пошук на сайті. Модель допоможе уточнити запит."""
    BASE_URL = "https://varus.ua"
    SEARCH_URL = "https://varus.ua/uk/search"

    @classmethod
    def search_products(cls, query: str, limit: int = 5) -> list[VarusItem]:
        try:
            # Спроба базового URL без префікса мови, якщо той видає 404
            url = "https://varus.ua/search/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
            }
            params = {"q": query}
            response = httpx.get(url, params=params, headers=headers, timeout=10.0, follow_redirects=True)

            if response.status_code != 200:
                logger.warning(f"Сайт повернув {response.status_code}. AI використає власну базу.")
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            items = []
            # Селектори
            cards = soup.select(".sf-product-card") or soup.select("article")

            for card in cards[:limit]:
                title_elem = card.select_one(".sf-product-card__title") or card.select_one("h3")
                link_elem = card.select_one("a")

                if title_elem and link_elem:
                    href = link_elem.get("href", "")
                    items.append(VarusItem(
                        title=title_elem.get_text(strip=True),
                        url=cls.BASE_URL + href if href.startswith("/") else href
                    ))
            return items
        except Exception as e:
            logger.error(f"Помилка скрейпінгу: {e}")
            return []


class AIProductMatcher:
    """Вибір релевантного товару за допомогою Search-можливостей моделі."""

    @staticmethod
    def match_and_analyze(requirement: ParsedProduct, found_items: list[VarusItem]) -> Optional[MatchResult]:
        items_str = "\n".join([f"- {i}. {it.title} ({it.url})" for i, it in enumerate(found_items)])

        # Просимо модель використати її знання (Search) для аналізу упаковок
        prompt = f"""
        Потреба: {requirement.name}, {requirement.quantity} {requirement.unit}.
        Знайдені позиції на Varus:
        {items_str if found_items else "Нічого не знайдено в списку."}

        Твоє завдання:
        1. Вибери найбільш підходящий товар.
        2. Використай свої знання про товари Varus (якщо список порожній, спробуй запропонувати посилання самостійно).
        3. Визнач pack_capacity (вага/кількість в одній одиниці товару) в одиницях: {requirement.unit}.

        Поверни JSON: is_found (bool), best_match_title, best_match_url, item_capacity (float).
        """
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "Ти експерт із закупівель Varus. Відповідай у JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return MatchResult(**data)
        except Exception as e:
            logger.error(f"Помилка матчингу: {e}")
            return None


def calculate_optimal_quantity(required: float, item_capacity: float) -> int:
    if not item_capacity or item_capacity <= 0: return 1
    return math.ceil(required / item_capacity)


def main():
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Файл {INPUT_FILE} не знайдено!")
        return

    results = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    for line in lines:
        logger.info(f"Обробка: {line}")
        parsed = ProductParser.parse_line(line)
        if not parsed: continue

        # Пошук
        search_results = VarusScraper.search_products(parsed.name)

        # Аналіз через AI
        match = AIProductMatcher.match_and_analyze(parsed, search_results)

        if match and match.is_found:
            qty = calculate_optimal_quantity(parsed.quantity, match.item_capacity)
            results.append({
                "Продукт": line,
                "Товар": match.best_match_title,
                "Кількість": qty,
                "Посилання": match.best_match_url
            })
            logger.info(f"Результат: {match.best_match_title} x {qty}")
        else:
            results.append({"Продукт": line, "Товар": "Не знайдено", "Кількість": "-", "Посилання": "-"})

    # CSV
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Продукт", "Товар", "Кількість", "Посилання"])
        writer.writeheader()
        writer.writerows(results)
    logger.info("Файл результатів сформовано.")


if __name__ == "__main__":
    main()