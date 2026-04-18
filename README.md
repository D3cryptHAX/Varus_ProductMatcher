# Varus Product Matcher

Система для автоматичного підбору товарів із магазину **Varus** на основі списку покупок.
Використовує **LLM (GitHub Models / OpenAI API)** для нормалізації продуктів і підбору найкращих відповідників.

---

## Основні можливості

* Парсинг списку покупок з текстового файлу
* Нормалізація продуктів через LLM (назва, кількість, одиниці)
* Web scraping сайту Varus
* ШІ-підбір найбільш релевантного товару
* Розрахунок оптимальної кількості упаковок
* Запис результатів у CSV

---

## Архітектура

Проєкт складається з кількох ключових компонентів:

### 1. `ProductParser`

* Використовує LLM для розбору рядка продукту
* Вхід: `"Молоко 2 л"`
* Вихід:

```json
{
  "name": "молоко",
  "quantity": 2,
  "unit": "л"
}
```

---

### 2. `VarusScraper`

* Виконує пошук товарів на сайті Varus
* Використовує `httpx` + `BeautifulSoup`
* Повертає список знайдених товарів

---

### 3. `VarusProductMatcher`

* Аналізує знайдені товари
* Визначає:

  * найкращий match
  * посилання
  * розмір упаковки

---

### 4. Розрахунок кількості

```python
ceil(required_quantity / item_capacity)
```

---

## Структура проєкту

```
.
├── main.py
├── products.txt       # Вхідний файл
├── result.csv         # Результат
├── .env               # Токени
└── README.md
```

---

## Встановлення

### 1. Клонування репозиторію

```bash
git clone https://github.com/D3cryptHAX/Varus_ProductMatcher
cd Varus_ProductMatcher
```

---

### 2. Встановлення залежностей

```bash
pip install -r requirements.txt
```

Або вручну:

```bash
pip install httpx beautifulsoup4 python-dotenv openai pydantic
```

---

### 3. Налаштування `.env`

Створіть файл `.env`:

```env
GITHUB_TOKEN=ваш_токен
INPUT_FILE=products.txt
OUTPUT_FILE=result.csv
```

---

## Створення токена GitHub Models
Перейдіть на сторінку **GitHub Models**.
Зі списку моделей оберіть **OpenAI GPT-4o mini**.
Натисніть **Use this model**.
Оберіть **Create personal access token**, згенеруйте токен і скопіюйте його.

---

## Формат вхідних даних

Файл `products.txt`:

```
молоко, 2 л.
яйця курячі, 10 шт.
цукор, 1 кг.
```

---

## Запуск

```bash
python main.py
```

---

## Формат результату (CSV)

| Продукт    | Товар             | Кількість | Посилання |
| ---------- | ----------------- | --------- | --------- |
| молоко, 2 л | Молоко Яготинське | 2         | URL       |
| яйця, 10 шт | Яйця курячі       | 1         | URL       |

---

## Використані технології

* **Python**
* **httpx** — HTTP клієнт
* **BeautifulSoup** — парсинг HTML
* **OpenAI / GitHub Models API**
* **Pydantic** — валідація даних
* **dotenv** — конфігурація

---

## Обмеження

* Залежність від доступності сайту Varus
* Можливі неточності LLM
* Обмеження API (rate limits)
