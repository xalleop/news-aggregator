#!/usr/bin/env python3
"""
Новостной агрегатор на основе RSS-фидов
Версия без API - генерирует структурированные данные для ручного анализа
"""

import feedparser
import yaml
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
import pytz

class NewsAggregator:
    """Агрегатор новостей из RSS с фильтрацией и группировкой"""
    
    def __init__(self, feeds_config: str, criteria_config: str):
        self.feeds_config = self.load_config(feeds_config)
        self.criteria = self.load_config(criteria_config)
        
        # Создаем директорию для отчетов
        Path("reports").mkdir(exist_ok=True)
    
    def load_config(self, config_path: str) -> dict:
        """Загрузка YAML конфигурации"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            print(f"✓ Конфигурация загружена: {config_path}")
            return config
        except FileNotFoundError:
            print(f"✗ Файл не найден: {config_path}")
            raise
        except yaml.YAMLError as e:
            print(f"✗ Ошибка парсинга YAML: {e}")
            raise
    
    def get_enabled_feeds(self) -> Dict[str, dict]:
        """Получение всех активных RSS-фидов"""
        feeds = {}
        
        for category in ['general_news', 'tech_news', 'ai_and_regulation']:
            if category in self.feeds_config:
                for name, data in self.feeds_config[category].items():
                    if data.get('enabled', True):
                        feeds[name] = {
                            'url': data['url'],
                            'tags': data.get('tags', []),
                            'category': category
                        }
        
        return feeds
    
    def fetch_rss_feed(self, source_name: str, feed_url: str, hours_back: int) -> List[dict]:
        """Получение новостей из одного RSS-фида"""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        articles = []
        
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries:
                # Парсим дату публикации
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        pub_date = datetime(*entry.updated_parsed[:6])
                    else:
                        pub_date = datetime.now()
                except:
                    pub_date = datetime.now()
                
                # Фильтруем по времени
                if pub_date > cutoff_time:
                    articles.append({
                        'title': entry.title,
                        'url': entry.link,
                        'source': source_name,
                        'published': pub_date.isoformat(),
                        'description': entry.get('summary', entry.get('description', ''))
                    })
            
            return articles
            
        except Exception as e:
            print(f"✗ {source_name:30} → Ошибка: {str(e)[:50]}")
            return []
    
    def fetch_all_news(self, hours_back: int = None) -> List[dict]:
        """Сбор новостей из всех активных фидов"""
        if hours_back is None:
            hours_back = self.feeds_config.get('filters', {}).get('hours_back', 24)
        
        all_articles = []
        feeds = self.get_enabled_feeds()
        
        print(f"\n{'─'*70}")
        print(f"Сбор новостей из {len(feeds)} источников")
        print(f"Период: последние {hours_back} часов")
        print(f"{'─'*70}\n")
        
        for source_name, feed_data in feeds.items():
            articles = self.fetch_rss_feed(source_name, feed_data['url'], hours_back)
            
            if articles:
                # Добавляем теги к каждой статье
                for article in articles:
                    article['tags'] = feed_data.get('tags', [])
                    article['category'] = feed_data.get('category', 'unknown')
                
                all_articles.extend(articles)
                print(f"✓ {source_name:30} → {len(articles):3} статей")
            else:
                print(f"✗ {source_name:30} →   0 статей")
        
        # Удаляем дубликаты по URL
        unique_articles = {a['url']: a for a in all_articles}.values()
        
        print(f"\n{'─'*70}")
        print(f"Всего собрано: {len(all_articles)} статей")
        print(f"Уникальных: {len(unique_articles)} статей")
        print(f"{'─'*70}\n")
        
        return list(unique_articles)
    
    def fetch_google_news(self, hours_back: int) -> List[dict]:
        """Дополнительный поиск через Google News RSS"""
        google_config = self.feeds_config.get('google_news', {})
        
        if not google_config.get('enabled', False):
            return []
        
        topics = google_config.get('topics', [])
        if not topics:
            return []
        
        google_news_base = 'https://news.google.com/rss/search?q={}&hl=ru&gl=RU&ceid=RU:ru'
        articles = []
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        print(f"{'─'*70}")
        print(f"Дополнительный поиск: Google News")
        print(f"{'─'*70}\n")
        
        for topic in topics:
            try:
                url = google_news_base.format(topic)
                feed = feedparser.parse(url)
                count = 0
                
                for entry in feed.entries[:20]:  # Максимум 20 на тему
                    try:
                        pub_date = datetime(*entry.published_parsed[:6])
                    except:
                        pub_date = datetime.now()
                    
                    if pub_date > cutoff_time:
                        articles.append({
                            'title': entry.title,
                            'url': entry.link,
                            'source': 'Google News',
                            'published': pub_date.isoformat(),
                            'description': entry.get('summary', ''),
                            'tags': ['google_news'],
                            'category': 'google_news',
                            'search_topic': topic
                        })
                        count += 1
                
                print(f"✓ '{topic}' → {count} статей")
                
            except Exception as e:
                print(f"✗ '{topic}' → Ошибка: {str(e)[:50]}")
        
        print(f"\nGoogle News: {len(articles)} статей\n")
        return articles
    
    def filter_by_keywords(self, articles: List[dict]) -> List[dict]:
        """Фильтрация по ключевым словам"""
        filters = self.feeds_config.get('filters', {})
        keywords = filters.get('keywords', [])
        exclude_keywords = filters.get('exclude_keywords', [])
        
        if not keywords:
            print("Фильтрация отключена (нет ключевых слов)\n")
            # Даже без фильтрации добавляем пустые matched_keywords
            for article in articles:
                article['matched_keywords'] = []
            return articles
        
        filtered = []
        
        for article in articles:
            text = f"{article['title']} {article['description']}".lower()
            
            # Проверяем исключения
            if exclude_keywords and any(kw.lower() in text for kw in exclude_keywords):
                continue
            
            # Проверяем включения
            if any(kw.lower() in text for kw in keywords):
                # Сохраняем, какие ключевые слова найдены
                article['matched_keywords'] = [
                    kw for kw in keywords if kw.lower() in text
                ]
                filtered.append(article)
        
        print(f"Фильтрация: {len(filtered)} из {len(articles)} статей соответствуют критериям\n")
        return filtered
    
    def group_articles(self, articles: List[dict]) -> Dict[str, List[dict]]:
        """Группировка статей по источникам и категориям"""
        groups = {
            'by_source': defaultdict(list),
            'by_category': defaultdict(list),
            'by_keyword': defaultdict(list)
        }
        
        for article in articles:
            groups['by_source'][article['source']].append(article)
            groups['by_category'][article.get('category', 'unknown')].append(article)
            
            # Группируем по ключевым словам
            for keyword in article.get('matched_keywords', []):
                groups['by_keyword'][keyword].append(article)
        
        return groups
    
    def generate_text_report(self, articles: List[dict], groups: dict) -> str:
        """Генерация человеко-читаемого текстового отчета"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        timestamp = datetime.now(moscow_tz)
        
        report = f"""
{'='*70}
НОВОСТНОЙ ДАЙДЖЕСТ
{'='*70}
Дата формирования: {timestamp.strftime('%d.%m.%Y %H:%M')}
Всего статей: {len(articles)}
Источников: {len(groups['by_source'])}
{'='*70}

"""
        
        # Статистика по источникам
        report += f"\n{'─'*70}\n"
        report += "СТАТИСТИКА ПО ИСТОЧНИКАМ\n"
        report += f"{'─'*70}\n\n"
        
        for source, source_articles in sorted(
            groups['by_source'].items(),
            key=lambda x: len(x[1]),
            reverse=True
        ):
            report += f"  • {source:30} → {len(source_articles):3} статей\n"
        
        # Группировка по ключевым словам (топ-темы)
        if groups['by_keyword']:
            report += f"\n\n{'─'*70}\n"
            report += "ТОП ТЕМЫ (по упоминаниям ключевых слов)\n"
            report += f"{'─'*70}\n\n"
            
            for keyword, kw_articles in sorted(
                groups['by_keyword'].items(),
                key=lambda x: len(x[1]),
                reverse=True
            )[:10]:  # Топ-10 тем
                report += f"  📌 {keyword} → {len(kw_articles)} статей\n"
        
        # Все статьи по источникам
        report += f"\n\n{'='*70}\n"
        report += "ВСЕ СТАТЬИ (группировка по источникам)\n"
        report += f"{'='*70}\n"
        
        for source, source_articles in sorted(groups['by_source'].items()):
            report += f"\n{'─'*70}\n"
            report += f"📰 {source.upper()} ({len(source_articles)} статей)\n"
            report += f"{'─'*70}\n\n"
            
            for i, article in enumerate(sorted(
                source_articles,
                key=lambda x: x['published'],
                reverse=True
            ), 1):
                pub_time = datetime.fromisoformat(article['published'])
                report += f"{i}. {article['title']}\n"
                report += f"   🔗 {article['url']}\n"
                report += f"   📅 {pub_time.strftime('%d.%m.%Y %H:%M')}\n"
                
                if article.get('matched_keywords'):
                    report += f"   🏷️  Темы: {', '.join(article['matched_keywords'])}\n"
                
                if article['description']:
                    desc = article['description'][:200].replace('\n', ' ')
                    report += f"   📝 {desc}...\n"
                
                report += "\n"
        
        # Инструкция для анализа
        report += f"\n{'='*70}\n"
        report += "СЛЕДУЮЩИЙ ШАГ: АНАЛИЗ\n"
        report += f"{'='*70}\n\n"
        report += "Для кластеризации и оценки значимости:\n\n"
        report += "1. Загрузите файл raw_articles_latest.json в чат с Claude\n"
        report += "2. Загрузите файл criteria.yaml для контекста\n"
        report += "3. Попросите Claude:\n"
        report += '   "Проанализируй эти новости используя критерии из criteria.yaml.\n'
        report += '    Сгруппируй по темам, оцени значимость каждой темы, создай отчет."\n\n'
        report += "4. Claude создаст структурированный отчет с оценками\n"
        report += "5. Сохраните результат как analyzed_digest_[дата].txt\n\n"
        
        return report
    
    def save_reports(self, articles: List[dict], groups: dict):
        """Сохранение всех отчетов"""
        # Используем московское время для имен файлов
        moscow_tz = pytz.timezone('Europe/Moscow')
        timestamp = datetime.now(moscow_tz).strftime('%Y-%m-%d_%H-%M')
        
        # 1. Сохраняем сырые данные в JSON
        json_path = f"reports/raw_articles_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': timestamp,
                'total_articles': len(articles),
                'articles': articles,
                'groups': {
                    'by_source': {k: len(v) for k, v in groups['by_source'].items()},
                    'by_category': {k: len(v) for k, v in groups['by_category'].items()},
                    'by_keyword': {k: len(v) for k, v in groups['by_keyword'].items()}
                }
            }, f, ensure_ascii=False, indent=2)
        
        # 2. Генерируем и сохраняем текстовый отчет
        text_report = self.generate_text_report(articles, groups)
        txt_path = f"reports/raw_digest_{timestamp}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        # 3. Обновляем latest.txt
        with open("reports/latest.txt", 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        # 4. Создаем краткий JSON для быстрого просмотра
        summary_path = f"reports/summary_{timestamp}.json"
        
        # Готовим данные для summary
        if groups['by_keyword']:
            top_items = sorted(
                [(k, len(v)) for k, v in groups['by_keyword'].items()],
                key=lambda x: x[1],
                reverse=True
            )[:20]
        else:
            # Если нет ключевых слов, показываем топ источников
            top_items = sorted(
                [(k, len(v)) for k, v in groups['by_source'].items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        
        summary_data = {
            'timestamp': timestamp,
            'total_articles': len(articles),
            'sources': {k: len(v) for k, v in groups['by_source'].items()},
            'top_keywords': top_items,
            'recent_headlines': [
                {
                    'title': a['title'],
                    'source': a['source'],
                    'url': a['url'],
                    'published': a['published']
                }
                for a in sorted(
                    articles,
                    key=lambda x: x['published'],
                    reverse=True
                )[:10]
            ]
        }
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        # 5. ВАЖНО: Создаем копии с фиксированными именами для веб-страницы
        shutil.copy(summary_path, "reports/summary_latest.json")
        shutil.copy(json_path, "reports/raw_articles_latest.json")
        
        print(f"{'='*70}")
        print(f"✓ Отчеты сохранены:")
        print(f"  • Данные (JSON):    {json_path}")
        print(f"  • Отчет (текст):    {txt_path}")
        print(f"  • Сводка (JSON):    {summary_path}")
        print(f"  • Последний отчет:  reports/latest.txt")
        print(f"  • Для веб:          reports/summary_latest.json")
        print(f"  • Для веб:          reports/raw_articles_latest.json")
        print(f"{'='*70}\n")
        
        return json_path, txt_path
    
    def run(self):
        """Главный метод агрегатора"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        print(f"\n{'='*70}")
        print(f"ЗАПУСК НОВОСТНОГО АГРЕГАТОРА")
        print(f"{'='*70}")
        print(f"Время (МСК): {datetime.now(moscow_tz).strftime('%d.%m.%Y %H:%M:%S')}\n")
    
        # Собираем из RSS
        hours_back = self.feeds_config.get('filters', {}).get('hours_back', 24)
        rss_articles = self.fetch_all_news(hours_back)
        
        # Добавляем из Google News
        google_articles = self.fetch_google_news(hours_back)
        all_articles = rss_articles + google_articles
        
        # Фильтруем
        filtered_articles = self.filter_by_keywords(all_articles)
        
        if not filtered_articles:
            print("✗ Нет статей после фильтрации\n")
            return
        
        # Группируем
        groups = self.group_articles(filtered_articles)
        
        # Сохраняем
        json_path, txt_path = self.save_reports(filtered_articles, groups)
        
        print("\nГотово! Следующие шаги:")
        print("1. Просмотрите reports/latest.txt для быстрого ознакомления")
        print(f"2. Загрузите reports/raw_articles_latest.json в Claude для анализа")
        print("3. Используйте criteria.yaml как reference для оценки\n")


def main():
    """Точка входа"""
    aggregator = NewsAggregator(
        feeds_config='feeds.yaml',
        criteria_config='criteria.yaml'
    )
    aggregator.run()


if __name__ == "__main__":
    main()
