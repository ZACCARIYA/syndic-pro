from django.db import models


class EncryptedTextField(models.TextField):
    """No-op placeholder used by historical migrations.

    Stores clear text; only present so old migrations can import it.
    Replace with a real encrypted field if needed in application code.
    """

    description = "EncryptedTextField (placeholder)"


