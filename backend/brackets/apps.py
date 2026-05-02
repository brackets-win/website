from django.apps import AppConfig


class BracketsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'brackets'
    # Must match ForeignKey string prefixes across models ('bracket.*')
    label = 'bracket'
