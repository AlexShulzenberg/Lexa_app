"""
Модели базы данных для приложения Lexa.
Каждый класс = одна таблица в БД.
"""

from django.db import models
from django.utils import timezone


class Collection(models.Model):
    """
    Коллекция слов — это папка/тема (например 'Бизнес', 'Фильмы').
    Создаётся раньше Word, потому что Word ссылается на Collection.
    """

    objects = models.Manager()  # ← явно объявляем для Pylint

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def word_count(self):
        """Сколько слов в коллекции."""
        return self.word_set.count()

    def mastery_percent(self):
        """Средний процент изученности слов в коллекции."""
        words = self.word_set.all()
        if not words:
            return 0
        total = sum(w.mastery_level for w in words)
        return round(total / words.count())

    class Meta:
        ordering = ['name']


class Word(models.Model):
    """
    Главная модель — одно слово.
    Содержит само слово, перевод, пример и уровень изученности.
    """

    objects = models.Manager()  # ← явно объявляем для Pylint

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

    def __str__(self):
        return f"{self.word} — {self.translation}"

    def mastery_label(self):
        """Человекочитаемый уровень для шаблонов."""
        if self.mastery_level < 30:
            return 'New'
        if self.mastery_level < 60:
            return 'Learning'
        if self.mastery_level < 90:
            return 'Familiar'
        return 'Mastered'

    def mastery_color(self):
        """CSS-класс для цветовой индикации уровня."""
        if self.mastery_level < 30:
            return 'mastery-new'
        if self.mastery_level < 60:
            return 'mastery-learning'
        if self.mastery_level < 90:
            return 'mastery-familiar'
        return 'mastery-mastered'

    class Meta:
        ordering = ['-created_at']


class LessonSession(models.Model):
    """
    Одна сессия обучения. Создаётся каждый раз когда пользователь
    нажимает Start lesson и завершает урок.
    """

    objects = models.Manager()  # ← явно объявляем для Pylint

    date = models.DateField(default=timezone.now)
    words_new = models.IntegerField(default=0)
    words_reviewed = models.IntegerField(default=0)
    duration_seconds = models.IntegerField(default=0)
    words_studied = models.ManyToManyField(Word, blank=True)

    def __str__(self):
        return f"Lesson {self.date} — {self.words_new + self.words_reviewed} words"

    class Meta:
        ordering = ['-date']


class DailyStreak(models.Model):
    """
    Один день занятий. Streak = количество подряд идущих дат в этой таблице.
    """

    objects = models.Manager()  # ← явно объявляем для Pylint

    date = models.DateField(unique=True)

    def __str__(self):
        return str(self.date)

    @classmethod
    def get_current_streak(cls):
        """
        Считает текущий streak: сколько дней подряд были занятия.
        """
        today = timezone.now().date()
        streak = 0
        current_date = today

        while cls.objects.filter(date=current_date).exists():
            streak += 1
            current_date -= timezone.timedelta(days=1)

        return streak

    class Meta:
        ordering = ['-date']