"""
Формы приложения vocabulary.
ModelForm автоматически создаёт форму из модели.
"""

from django import forms
from .models import Word, Collection


class WordForm(forms.ModelForm):
    """Форма добавления и редактирования слова."""

    class Meta:
        model = Word
        fields = ['word', 'translation', 'transcription',
                  'part_of_speech', 'example_sentence', 'collection']
        widgets = {
            # widgets позволяют задать HTML-атрибуты для каждого поля
            'word': forms.TextInput(attrs={
                'placeholder': 'Enter word (e.g. ephemeral)',
                'class': 'form-input',
            }),
            'translation': forms.TextInput(attrs={
                'placeholder': 'Translation',
                'class': 'form-input',
                'id': 'id_translation',  # нужен для JS автоперевода
            }),
            'transcription': forms.TextInput(attrs={
                'placeholder': '/ɪˈfem(ə)r(ə)l/ (optional)',
                'class': 'form-input',
            }),
            'part_of_speech': forms.Select(attrs={
                'class': 'form-select',
            }),
            'example_sentence': forms.Textarea(attrs={
                'placeholder': 'Example sentence (optional)',
                'class': 'form-textarea',
                'rows': 3,
            }),
            'collection': forms.Select(attrs={
                'class': 'form-select',
            }),
        }

    def clean_word(self):
        """
        Валидация поля word.
        clean_<fieldname> — специальный метод Django для валидации конкретного поля.
        """
        word = self.cleaned_data.get('word', '').strip()
        if not word:
            raise forms.ValidationError('Word cannot be empty.')
        if len(word) < 2:
            raise forms.ValidationError('Word must be at least 2 characters.')
        return word

    def clean_translation(self):
        """Валидация перевода."""
        translation = self.cleaned_data.get('translation', '').strip()
        if not translation:
            raise forms.ValidationError('Translation is required.')
        return translation


class CollectionForm(forms.ModelForm):
    """Форма создания и редактирования коллекции."""

    class Meta:
        model = Collection
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Collection name (e.g. Business English)',
                'class': 'form-input',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Short description (optional)',
                'class': 'form-textarea',
                'rows': 3,
            }),
        }

    def clean_name(self):
        """Валидация имени коллекции."""
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Collection name cannot be empty.')
        if len(name) < 2:
            raise forms.ValidationError('Name must be at least 2 characters.')
        return name