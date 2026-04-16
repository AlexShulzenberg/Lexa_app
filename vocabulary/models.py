"""
Модели базы данных для приложения Lexa.
Каждый класс = одна таблица в БД.
"""

from django.db import models
from django.utils import timezone


class Collection(models.Model):
    """Коллекция слов — папка/тема (например 'Бизнес', 'Фильмы')."""

    objects = models.Manager()

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # ← явно указываем возвращаемый тип
        return str(self.name)  # ← str() убирает E0307

    def word_count(self) -> int:
        """Сколько слов в коллекции."""
        return self.word_set.count()  # pylint: disable=no-member

    def mastery_percent(self) -> int:
        """Средний процент изученности слов в коллекции."""
        words = self.word_set.all()  # pylint: disable=no-member
        if not words:
            return 0
        total = sum(w.mastery_level for w in words)
        return round(total / words.count())

    class Meta:
        """Мета-настройки модели Collection."""

        ordering = ['name']


class Word(models.Model):
    """Главная модель — одно французское слово с переводом и статистикой."""

    objects = models.Manager()

    PART_OF_SPEECH_CHOICES = [
        ('n', 'noun'),
        ('v', 'verb'),
        ('adj', 'adjective'),
        ('adv', 'adverb'),
        ('phrase', 'phrase'),
        ('other', 'other'),
    ]

    word = models.CharField(max_length=200)
    translation = models.CharField(max_length=200)
    transcription = models.CharField(max_length=200, blank=True, default='')
    part_of_speech = models.CharField(
        max_length=10,
        choices=PART_OF_SPEECH_CHOICES,
        default='other'
    )
    example_sentence = models.TextField(blank=True, default='')
    mastery_level = models.IntegerField(default=0)
    collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_reviewed = models.DateTimeField(null=True, blank=True)
    queue_order = models.IntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.word} — {self.translation}"

    def mastery_label(self) -> str:
        """Человекочитаемый уровень для шаблонов."""
        if self.mastery_level < 30:
            return 'New'
        if self.mastery_level < 60:
            return 'Learning'
        if self.mastery_level < 90:
            return 'Familiar'
        return 'Mastered'

    def mastery_color(self) -> str:
        """CSS-класс для цветовой индикации уровня."""
        if self.mastery_level < 30:
            return 'mastery-new'
        if self.mastery_level < 60:
            return 'mastery-learning'
        if self.mastery_level < 90:
            return 'mastery-familiar'
        return 'mastery-mastered'

    class Meta:
        """Мета-настройки модели Word."""

        ordering = ['-created_at']


class LessonSession(models.Model):
    """Одна сессия обучения — создаётся при завершении урока."""

    objects = models.Manager()

    date = models.DateField(default=timezone.now)
    words_new = models.IntegerField(default=0)
    words_reviewed = models.IntegerField(default=0)
    duration_seconds = models.IntegerField(default=0)
    words_studied = models.ManyToManyField(Word, blank=True)

    def __str__(self) -> str:
        return f"Lesson {self.date} — {self.words_new + self.words_reviewed} words"

    class Meta:
        """Мета-настройки модели LessonSession."""

        ordering = ['-date']


class DailyStreak(models.Model):
    """Один день занятий для подсчёта streak."""

    objects = models.Manager()

    date = models.DateField(unique=True)

    def __str__(self) -> str:
        return str(self.date)

    @classmethod
    def get_current_streak(cls) -> int:
        """Считает текущий streak: сколько дней подряд были занятия."""
        today = timezone.now().date()
        streak = 0
        current_date = today

        while cls.objects.filter(date=current_date).exists():
            streak += 1
            current_date -= timezone.timedelta(days=1)

        return streak

    class Meta:
        """Мета-настройки модели DailyStreak."""

        ordering = ['-date']
